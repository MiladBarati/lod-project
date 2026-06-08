import json
import re
import urllib.parse
from typing import Any, Dict, List, Optional

import jsonschema

from .proxy import coerce_type, compile_openapi_paths
from .ref_resolver import RefResolver

try:
    import requests
    import requests.adapters
except ImportError:
    requests = None

try:
    import httpx
except ImportError:
    httpx = None


class LODValidationError(Exception):
    """Exception raised when an HTTP request fails OpenAPI schema validation."""

    def __init__(self, errors: List[Dict[str, Any]]):
        self.errors = errors
        msg = "LOD Request Validation Failed:\n" + "\n".join(
            f"  - [{err['location']}] Parameter '{err['parameter']}': {err['description']}"
            for err in errors
        )
        super().__init__(msg)


class RequestValidator:
    """Core in-process validator that matches and validates HTTP requests against OpenAPI schemas."""

    def __init__(self, spec_data: Dict[str, Any]):
        # Resolve references fully
        self.spec_data = RefResolver(spec_data).resolve_refs_fully(spec_data)
        # Pre-compile paths
        self.compiled_paths = compile_openapi_paths(self.spec_data)

    def validate_request(
        self, method: str, url: str, headers: Dict[str, str], body: bytes
    ) -> None:
        """
        Validates an HTTP request against the OpenAPI spec.
        Raises LODValidationError if validation fails.
        """
        method = method.lower()
        parsed_url = urllib.parse.urlparse(url)
        path_only = parsed_url.path
        query_params_raw = urllib.parse.parse_qs(parsed_url.query)

        # 1. Match Path and Extract Path Parameters
        matched_path = None
        path_params = {}
        for item in self.compiled_paths:
            m = item["pattern"].match(path_only)
            if m:
                matched_path = item
                path_params = m.groupdict()
                break

        if not matched_path:
            errors = [{
                "location": "path",
                "parameter": "url",
                "issue": "endpoint_not_found",
                "description": f"The requested path '{path_only}' does not match any endpoint defined in the OpenAPI specification.",
            }]
            raise LODValidationError(errors)

        # 2. Match Method Operation
        path_item = matched_path["item"]
        operation = path_item.get(method)
        if not operation:
            allowed_methods = [
                m.upper()
                for m in ["get", "post", "put", "delete", "options", "patch"]
                if m in path_item
            ]
            errors = [{
                "location": "path",
                "parameter": "method",
                "issue": "method_not_allowed",
                "description": f"HTTP method '{method.upper()}' is not supported by endpoint '{matched_path['template']}'. Allowed: {', '.join(allowed_methods)}",
            }]
            raise LODValidationError(errors)

        errors = []
        spec_parameters = path_item.get("parameters", []) + operation.get("parameters", [])

        # Validate Parameters (Query, Path, Headers)
        for param in spec_parameters:
            name = param.get("name")
            param_in = param.get("in")
            required = param.get("required", False)
            schema = param.get("schema", {})
            schema_type = schema.get("type")

            # Extract parameter value
            val = None
            if param_in == "path":
                val = path_params.get(name)
            elif param_in == "query":
                if name in query_params_raw:
                    if schema_type == "array":
                        val = query_params_raw[name]
                    else:
                        val = query_params_raw[name][0]
            elif param_in == "header":
                # Header lookup should be case-insensitive
                header_keys = {k.lower(): k for k in headers}
                if name.lower() in header_keys:
                    val = headers[header_keys[name.lower()]]

            # Check presence
            if val is None:
                if required:
                    errors.append({
                        "location": param_in,
                        "parameter": name,
                        "issue": "missing_required_parameter",
                        "description": f"The '{name}' {param_in} parameter is required but was not provided.",
                    })
                continue

            # Coerce values if string
            if param_in in ("path", "query", "header") and isinstance(val, str):
                val = coerce_type(val, schema_type)

            # Validate parameter schema
            try:
                jsonschema.validate(instance=val, schema=schema)
            except jsonschema.ValidationError as e:
                errors.append({
                    "location": param_in,
                    "parameter": name,
                    "issue": "schema_validation_failed",
                    "description": e.message,
                })

        # Validate Request Body
        request_body_spec = operation.get("requestBody")
        if request_body_spec:
            required = request_body_spec.get("required", False)
            if not body:
                if required:
                    errors.append({
                        "location": "body",
                        "parameter": "requestBody",
                        "issue": "missing_request_body",
                        "description": "Request body is required but was not provided.",
                    })
            else:
                content = request_body_spec.get("content", {})
                json_media = content.get("application/json")
                if json_media:
                    body_schema = json_media.get("schema", {})
                    try:
                        parsed_json = json.loads(
                            body.decode("utf-8") if isinstance(body, bytes) else body
                        )
                        validator = jsonschema.Draft7Validator(body_schema)
                        for e in validator.iter_errors(parsed_json):
                            path_list = list(e.path)
                            if e.validator == "required" and len(e.message.split("'")) > 1:
                                path_list.append(e.message.split("'")[1])
                            param_path = ".".join(map(str, path_list)) or "body"
                            errors.append({
                                "location": "body",
                                "parameter": param_path,
                                "issue": "schema_validation_failed",
                                "description": e.message,
                            })
                    except json.JSONDecodeError as e:
                        errors.append({
                            "location": "body",
                            "parameter": "requestBody",
                            "issue": "invalid_json",
                            "description": f"Failed to parse request body as valid JSON: {e}",
                        })

        if errors:
            raise LODValidationError(errors)


if requests is not None:

    class LODRequestsAdapter(requests.adapters.HTTPAdapter):
        """HTTP Adapter for the `requests` library that validates outgoing requests in-process."""

        def __init__(self, spec_data: Dict[str, Any], *args, **kwargs):
            telemetry_endpoint = kwargs.pop("telemetry_endpoint", None)
            telemetry_api_key = kwargs.pop("telemetry_api_key", None)
            telemetry_enabled = kwargs.pop("telemetry_enabled", None)
            super().__init__(*args, **kwargs)
            self.validator = RequestValidator(spec_data)
            from .telemetry import SyncTelemetryReporter
            self.telemetry_reporter = SyncTelemetryReporter(
                endpoint=telemetry_endpoint,
                api_key=telemetry_api_key,
                enabled=telemetry_enabled,
            )

        def send(
            self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None
        ):
            body_bytes = b""
            if request.body:
                if isinstance(request.body, bytes):
                    body_bytes = request.body
                elif isinstance(request.body, str):
                    body_bytes = request.body.encode("utf-8")

            headers_dict = dict(request.headers)

            try:
                self.validator.validate_request(
                    method=request.method,
                    url=request.url,
                    headers=headers_dict,
                    body=body_bytes,
                )
            except LODValidationError as e:
                self.telemetry_reporter.report_validation_error(
                    method=request.method,
                    url=request.url,
                    errors=e.errors,
                )
                raise e

            return super().send(
                request,
                stream=stream,
                timeout=timeout,
                verify=verify,
                cert=cert,
                proxies=proxies,
            )

else:

    class LODRequestsAdapter:

        def __init__(self, *args, **kwargs):
            raise ImportError(
                "The 'requests' package is required to use LODRequestsAdapter. "
                "Install it using 'pip install requests'."
            )


if httpx is not None:

    class LODHTTPXTransport(httpx.BaseTransport):
        """HTTP Transport for the sync `httpx.Client` that validates outgoing requests in-process."""

        def __init__(
            self, spec_data: Dict[str, Any], transport: Optional[httpx.BaseTransport] = None, **kwargs
        ):
            telemetry_endpoint = kwargs.pop("telemetry_endpoint", None)
            telemetry_api_key = kwargs.pop("telemetry_api_key", None)
            telemetry_enabled = kwargs.pop("telemetry_enabled", None)
            self.validator = RequestValidator(spec_data)
            self._transport = transport or httpx.HTTPTransport()
            from .telemetry import SyncTelemetryReporter
            self.telemetry_reporter = SyncTelemetryReporter(
                endpoint=telemetry_endpoint,
                api_key=telemetry_api_key,
                enabled=telemetry_enabled,
            )

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            body = request.read()
            headers_dict = dict(request.headers)

            try:
                self.validator.validate_request(
                    method=request.method,
                    url=str(request.url),
                    headers=headers_dict,
                    body=body,
                )
            except LODValidationError as e:
                self.telemetry_reporter.report_validation_error(
                    method=request.method,
                    url=str(request.url),
                    errors=e.errors,
                )
                raise e

            return self._transport.handle_request(request)

        def close(self):
            self._transport.close()

    class LODHTTPXAsyncTransport(httpx.AsyncBaseTransport):
        """HTTP Transport for the async `httpx.AsyncClient` that validates outgoing requests in-process."""

        def __init__(
            self,
            spec_data: Dict[str, Any],
            transport: Optional[httpx.AsyncBaseTransport] = None,
            **kwargs
        ):
            telemetry_endpoint = kwargs.pop("telemetry_endpoint", None)
            telemetry_api_key = kwargs.pop("telemetry_api_key", None)
            telemetry_enabled = kwargs.pop("telemetry_enabled", None)
            self.validator = RequestValidator(spec_data)
            self._transport = transport or httpx.AsyncHTTPTransport()
            from .telemetry import AsyncTelemetryReporter
            self.telemetry_reporter = AsyncTelemetryReporter(
                endpoint=telemetry_endpoint,
                api_key=telemetry_api_key,
                enabled=telemetry_enabled,
            )

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = request.read()
            headers_dict = dict(request.headers)

            try:
                self.validator.validate_request(
                    method=request.method,
                    url=str(request.url),
                    headers=headers_dict,
                    body=body,
                )
            except LODValidationError as e:
                await self.telemetry_reporter.report_validation_error(
                    method=request.method,
                    url=str(request.url),
                    errors=e.errors,
                )
                raise e

            return await self._transport.handle_async_request(request)

        async def aclose(self):
            await self._transport.aclose()

else:

    class LODHTTPXTransport:

        def __init__(self, *args, **kwargs):
            raise ImportError(
                "The 'httpx' package is required to use LODHTTPXTransport. "
                "Install it using 'pip install httpx'."
            )

    class LODHTTPXAsyncTransport:

        def __init__(self, *args, **kwargs):
            raise ImportError(
                "The 'httpx' package is required to use LODHTTPXAsyncTransport. "
                "Install it using 'pip install httpx'."
            )
