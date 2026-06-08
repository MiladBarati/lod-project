import http.server
import json
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List
from urllib.parse import parse_qs, urlparse

import jsonschema

from .ref_resolver import RefResolver


def compile_openapi_paths(spec_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Pre-compiles OpenAPI path templates into regex patterns to match incoming requests.
    Converts path parameter syntax like `/users/{id}` to regex `^/users/(?P<id>[^/]+)$`.
    """
    paths = spec_data.get("paths", {})
    compiled = []

    for path_template, path_item in paths.items():
        # Split by slash, escape static parts, convert parameters
        segments = path_template.split("/")
        regex_segments = []

        for seg in segments:
            if seg.startswith("{") and seg.endswith("}"):
                param_name = seg[1:-1]
                # Match everything except a slash
                regex_segments.append(f"(?P<{param_name}>[^/]+)")
            else:
                regex_segments.append(re.escape(seg))

        regex_str = "^" + "/".join(regex_segments) + "$"
        try:
            pattern = re.compile(regex_str)
            compiled.append({
                "template": path_template,
                "pattern": pattern,
                "item": path_item
            })
        except re.error as e:
            print(f"Warning: Failed to compile path pattern '{path_template}': {e}", file=sys.stderr)

    return compiled


def coerce_type(val: Any, schema_type: str) -> Any:
    """Coerces string parameter values to target types based on schema definition."""
    if schema_type == "integer":
        try:
            return int(val)
        except (ValueError, TypeError):
            return val
    elif schema_type == "number":
        try:
            return float(val)
        except (ValueError, TypeError):
            return val
    elif schema_type == "boolean":
        if str(val).lower() in ("true", "1"):
            return True
        elif str(val).lower() in ("false", "0"):
            return False
        return val
    return val


class ValidationProxyHandler(http.server.BaseHTTPRequestHandler):
    spec_data: Dict[str, Any] = {}
    upstream: str = ""
    compiled_paths: List[Dict[str, Any]] = []

    def log_message(self, format, *args):
        # Prevent default http.server request logging from cluttering stdout/stderr
        pass

    def do_OPTIONS(self):
        """Handle CORS preflights gracefully."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS, PATCH")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        self.dispatch()

    def do_POST(self):
        self.dispatch()

    def do_PUT(self):
        self.dispatch()

    def do_DELETE(self):
        self.dispatch()

    def do_PATCH(self):
        self.dispatch()

    def dispatch(self):
        start_time = time.perf_counter()
        parsed_url = urlparse(self.path)
        path_only = parsed_url.path
        query_params_raw = parse_qs(parsed_url.query)
        method = self.command.lower()

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
                "description": f"The requested path '{path_only}' does not match any endpoint defined in the OpenAPI specification."
            }]
            self.send_error_response(errors, start_time, path_only)
            return

        # 2. Match Method Operation
        path_item = matched_path["item"]
        operation = path_item.get(method)
        if not operation:
            allowed_methods = [m.upper() for m in ["get", "post", "put", "delete", "options", "patch"] if m in path_item]
            errors = [{
                "location": "path",
                "parameter": "method",
                "issue": "method_not_allowed",
                "description": f"HTTP method '{self.command}' is not supported by endpoint '{matched_path['template']}'. Allowed: {', '.join(allowed_methods)}"
            }]
            self.send_error_response(errors, start_time, path_only)
            return

        # 3. Read Body
        content_length = int(self.headers.get("Content-Length", 0))
        body_data = self.rfile.read(content_length) if content_length > 0 else b""

        # 4. Perform Schema Validation
        errors = []

        # Combine parameters from Path Item and Operation level
        spec_parameters = path_item.get("parameters", []) + operation.get("parameters", [])

        # Validate Parameters (Query, Path, Headers)
        for param in spec_parameters:
            name = param.get("name")
            param_in = param.get("in")
            required = param.get("required", False)
            schema = param.get("schema", {})
            schema_type = schema.get("type")

            # Extract parameter value based on its location
            val = None
            if param_in == "path":
                val = path_params.get(name)
            elif param_in == "query":
                if name in query_params_raw:
                    # If array schema expected, keep as list, otherwise extract first element
                    if schema_type == "array":
                        val = query_params_raw[name]
                    else:
                        val = query_params_raw[name][0]
            elif param_in == "header":
                val = self.headers.get(name)

            # Check presence
            if val is None:
                if required:
                    errors.append({
                        "location": param_in,
                        "parameter": name,
                        "issue": "missing_required_parameter",
                        "description": f"The '{name}' {param_in} parameter is required but was not provided."
                    })
                continue

            # Coerce values if string (path, query, header)
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
                    "description": e.message
                })

        # Validate Request Body
        request_body_spec = operation.get("requestBody")
        if request_body_spec:
            required = request_body_spec.get("required", False)
            if not body_data:
                if required:
                    errors.append({
                        "location": "body",
                        "parameter": "requestBody",
                        "issue": "missing_request_body",
                        "description": "Request body is required but was not provided."
                    })
            else:
                # Validate JSON request body
                content = request_body_spec.get("content", {})
                json_media = content.get("application/json")
                if json_media:
                    body_schema = json_media.get("schema", {})
                    try:
                        parsed_json = json.loads(body_data.decode("utf-8"))
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
                                "description": e.message
                            })
                    except json.JSONDecodeError as e:
                        errors.append({
                            "location": "body",
                            "parameter": "requestBody",
                            "issue": "invalid_json",
                            "description": f"Failed to parse request body as valid JSON: {e}"
                        })

        # 5. Handle Errors or Forward Request
        if errors:
            self.send_error_response(errors, start_time, path_only)
        else:
            self.forward_request(body_data, path_only, parsed_url.query, start_time)

    def send_error_response(self, errors: List[Dict[str, Any]], start_time: float, path_only: str):
        duration = time.perf_counter() - start_time

        self.send_response(422)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS, PATCH")
        self.send_header("Access-Control-Allow-Headers", "*")

        response_body = {
            "status": "error",
            "message": "API request validation failed",
            "errors": errors
        }

        body_bytes = json.dumps(response_body, indent=2).encode("utf-8")
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

        # Log to stderr
        print(f"[{self.log_date_time_string()}] {self.command} {path_only} - 422 Unprocessable Entity - Validation Failed ({duration:.4f}s)", file=sys.stderr)
        for err in errors:
            print(f"  - [{err['location']}] Parameter '{err['parameter']}': {err['description']}", file=sys.stderr)

    def forward_request(self, body_data: bytes, path_only: str, query_str: str, start_time: float):
        # Normalize upstream URL
        upstream_base = self.upstream.rstrip("/")
        upstream_url = upstream_base + path_only
        if query_str:
            upstream_url += "?" + query_str

        # Build downstream request headers
        headers = {}
        for k, v in self.headers.items():
            if k.lower() not in ("host", "content-length"):
                headers[k] = v

        req = urllib.request.Request(
            url=upstream_url,
            data=body_data if body_data else None,
            headers=headers,
            method=self.command
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_body = resp.read()
                status_code = resp.status

                self.send_response(status_code)
                for header_name, header_val in resp.getheaders():
                    if header_name.lower() not in ("transfer-encoding", "content-length"):
                        self.send_header(header_name, header_val)
                self.send_header("Content-Length", str(len(resp_body)))
                self.end_headers()
                self.wfile.write(resp_body)

                duration = time.perf_counter() - start_time
                print(f"[{self.log_date_time_string()}] {self.command} {path_only} - {status_code} Success - Forwarded ({duration:.4f}s)", file=sys.stdout)

        except urllib.error.HTTPError as e:
            # Downstream API returned HTTP Error status
            resp_body = e.read()
            status_code = e.code

            self.send_response(status_code)
            for header_name, header_val in e.headers.items():
                if header_name.lower() not in ("transfer-encoding", "content-length"):
                    self.send_header(header_name, header_val)
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)

            duration = time.perf_counter() - start_time
            print(f"[{self.log_date_time_string()}] {self.command} {path_only} - {status_code} Error - Forwarded ({duration:.4f}s)", file=sys.stderr)

        except Exception as e:
            # Bad gateway (connection failure or timeouts)
            self.send_response(502)
            self.send_header("Content-Type", "application/json")

            err_body_dict = {
                "status": "error",
                "message": f"Bad Gateway: Failed to connect or receive response from upstream host: {e}"
            }
            body_bytes = json.dumps(err_body_dict, indent=2).encode("utf-8")
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)

            duration = time.perf_counter() - start_time
            print(f"[{self.log_date_time_string()}] {self.command} {path_only} - 502 Bad Gateway - Connection Failed: {e} ({duration:.4f}s)", file=sys.stderr)


def build_proxy_app(spec_data: Dict[str, Any], upstream: str):
    """Builds and returns the FastAPI application for the request validation proxy."""
    import httpx
    from fastapi import FastAPI, Request, Response
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse

    # Resolve all spec schema pointers first
    resolved_spec = RefResolver(spec_data).resolve_refs_fully(spec_data)

    # Pre-compile paths
    compiled_paths = compile_openapi_paths(resolved_spec)

    app = FastAPI(title="LOD Validation Proxy")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.api_route("/{path_only:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
    async def proxy_endpoint(request: Request, path_only: str):
        path_with_slash = "/" + path_only
        method = request.method.lower()

        # 1. Match Path and Extract Path Parameters
        matched_path = None
        path_params = {}
        for item in compiled_paths:
            m = item["pattern"].match(path_with_slash)
            if m:
                matched_path = item
                path_params = m.groupdict()
                break

        if not matched_path:
            errors = [{
                "location": "path",
                "parameter": "url",
                "issue": "endpoint_not_found",
                "description": f"The requested path '{path_with_slash}' does not match any endpoint defined in the OpenAPI specification."
            }]
            return JSONResponse(status_code=422, content={
                "status": "error",
                "message": "API request validation failed",
                "errors": errors
            })

        # 2. Match Method Operation
        path_item = matched_path["item"]
        operation = path_item.get(method)
        if not operation:
            allowed_methods = [m.upper() for m in ["get", "post", "put", "delete", "options", "patch"] if m in path_item]
            errors = [{
                "location": "path",
                "parameter": "method",
                "issue": "method_not_allowed",
                "description": f"HTTP method '{request.method}' is not supported by endpoint '{matched_path['template']}'. Allowed: {', '.join(allowed_methods)}"
            }]
            return JSONResponse(status_code=422, content={
                "status": "error",
                "message": "API request validation failed",
                "errors": errors
            })

        # 3. Read Body
        body_data = await request.body()

        # 4. Perform Schema Validation
        errors = []

        spec_parameters = path_item.get("parameters", []) + operation.get("parameters", [])

        query_params_raw = {}
        for k, v in request.query_params.multi_items():
            if k not in query_params_raw:
                query_params_raw[k] = []
            query_params_raw[k].append(v)

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
                val = request.headers.get(name)

            # Check presence
            if val is None:
                if required:
                    errors.append({
                        "location": param_in,
                        "parameter": name,
                        "issue": "missing_required_parameter",
                        "description": f"The '{name}' {param_in} parameter is required but was not provided."
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
                    "description": e.message
                })

        # Validate Request Body
        request_body_spec = operation.get("requestBody")
        if request_body_spec:
            required = request_body_spec.get("required", False)
            if not body_data:
                if required:
                    errors.append({
                        "location": "body",
                        "parameter": "requestBody",
                        "issue": "missing_request_body",
                        "description": "Request body is required but was not provided."
                    })
            else:
                content = request_body_spec.get("content", {})
                json_media = content.get("application/json")
                if json_media:
                    body_schema = json_media.get("schema", {})
                    try:
                        parsed_json = json.loads(body_data.decode("utf-8"))
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
                                "description": e.message
                            })
                    except json.JSONDecodeError as e:
                        errors.append({
                            "location": "body",
                            "parameter": "requestBody",
                            "issue": "invalid_json",
                            "description": f"Failed to parse request body as valid JSON: {e}"
                        })

        # 5. Handle Errors or Forward Request
        if errors:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {request.method} {path_with_slash} - 422 Unprocessable Entity - Validation Failed", file=sys.stderr)
            for err in errors:
                print(f"  - [{err['location']}] Parameter '{err['parameter']}': {err['description']}", file=sys.stderr)
            return JSONResponse(status_code=422, content={
                "status": "error",
                "message": "API request validation failed",
                "errors": errors
            })

        # Forward request
        upstream_base = upstream.rstrip("/")
        upstream_url = upstream_base + path_with_slash
        if request.url.query:
            upstream_url += "?" + request.url.query

        headers = {}
        for k, v in request.headers.items():
            if k.lower() not in ("host", "content-length"):
                headers[k] = v

        start_time = time.perf_counter()
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                resp = await client.request(
                    method=request.method,
                    url=upstream_url,
                    headers=headers,
                    content=body_data if body_data else None
                )
                duration = time.perf_counter() - start_time
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {request.method} {path_with_slash} - {resp.status_code} Success - Forwarded ({duration:.4f}s)", file=sys.stdout)

                exclude_headers = {"content-length", "transfer-encoding"}
                resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in exclude_headers}
                return Response(content=resp.content, status_code=resp.status_code, headers=resp_headers)
            except Exception as e:
                duration = time.perf_counter() - start_time
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {request.method} {path_with_slash} - 502 Bad Gateway - Connection Failed: {e} ({duration:.4f}s)", file=sys.stderr)
                return JSONResponse(status_code=502, content={
                    "status": "error",
                    "message": f"Bad Gateway: Failed to connect or receive response from upstream host: {e}"
                })

    return app


def start_proxy(spec_data: Dict[str, Any], upstream: str, port: int):
    """Initializes and runs the validation proxy (using FastAPI/Uvicorn if available, otherwise ThreadingHTTPServer)."""
    try:
        import uvicorn

        # Build FastAPI app
        app = build_proxy_app(spec_data, upstream)

        print(f"LOD Validation Proxy (Async) listening on http://localhost:{port}", file=sys.stdout)
        print(f"Proxying requests to upstream: {upstream}", file=sys.stdout)
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

    except ImportError:
        # Fallback to ThreadingHTTPServer if uvicorn/fastapi/httpx are not available
        print("Warning: fastapi, uvicorn, or httpx not available. Falling back to legacy synchronous ThreadingHTTPServer proxy...", file=sys.stderr)

        resolved_spec = RefResolver(spec_data).resolve_refs_fully(spec_data)
        compiled_paths = compile_openapi_paths(resolved_spec)

        ValidationProxyHandler.spec_data = resolved_spec
        ValidationProxyHandler.upstream = upstream
        ValidationProxyHandler.compiled_paths = compiled_paths

        server_address = ("", port)
        server = http.server.ThreadingHTTPServer(server_address, ValidationProxyHandler)

        print(f"LOD Validation Proxy (Sync Fallback) listening on http://localhost:{port}", file=sys.stdout)
        print(f"Proxying requests to upstream: {upstream}", file=sys.stdout)
        server.serve_forever()



