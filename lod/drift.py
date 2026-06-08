import logging
from typing import Any, Dict, List, Set, Tuple, Optional
from .ref_resolver import RefResolver

logger = logging.getLogger("lod_gateway.drift")

class OpenAPIComparator:
    """
    Compares two OpenAPI specifications structurally to identify breaking
    and non-breaking changes, targeting parameters, types, and request bodies.
    """
    def __init__(self, base_spec: Dict[str, Any], new_spec: Dict[str, Any]):
        self.base_spec = base_spec
        self.new_spec = new_spec
        self.base_resolver = RefResolver(base_spec)
        self.new_resolver = RefResolver(new_spec)
        
        self.breaking_changes: List[str] = []
        self.non_breaking_changes: List[str] = []

    def compare(self) -> Dict[str, Any]:
        """
        Executes comparison and returns a summary report.
        """
        base_paths = self.base_spec.get("paths", {})
        new_paths = self.new_spec.get("paths", {})

        # Compare endpoints
        self._compare_endpoints(base_paths, new_paths)

        return {
            "is_breaking": len(self.breaking_changes) > 0,
            "breaking_changes": self.breaking_changes,
            "non_breaking_changes": self.non_breaking_changes
        }

    def _compare_endpoints(self, base_paths: Dict[str, Any], new_paths: Dict[str, Any]) -> None:
        # 1. Check for deleted paths/methods
        for path, path_item in base_paths.items():
            if not isinstance(path_item, dict):
                continue
            for method, op in path_item.items():
                if method.lower() not in ["get", "post", "put", "delete", "patch", "options", "head", "trace"]:
                    continue
                
                # Check if path or method is missing in new spec
                if path not in new_paths or method not in new_paths[path]:
                    self.breaking_changes.append(
                        f"Deleted endpoint: {method.upper()} {path}"
                    )
                    continue

                # Compare existing endpoint
                new_op = new_paths[path][method]
                if isinstance(op, dict) and isinstance(new_op, dict):
                    self._compare_operation(path, method, op, new_op)

        # 2. Check for newly added endpoints (non-breaking)
        for path, path_item in new_paths.items():
            if not isinstance(path_item, dict):
                continue
            for method in path_item.keys():
                if method.lower() not in ["get", "post", "put", "delete", "patch", "options", "head", "trace"]:
                    continue
                if path not in base_paths or method not in base_paths[path]:
                    self.non_breaking_changes.append(
                        f"Added endpoint: {method.upper()} {path}"
                    )

    def _compare_operation(self, path: str, method: str, base_op: Dict[str, Any], new_op: Dict[str, Any]) -> None:
        endpoint_label = f"{method.upper()} {path}"

        # Get and resolve parameters
        base_params = self._resolve_operation_params(base_op, self.base_resolver)
        new_params = self._resolve_operation_params(new_op, self.new_resolver)

        # Compare parameters by (name, in)
        base_param_map = {(p.get("name"), p.get("in")): p for p in base_params if p.get("name") and p.get("in")}
        new_param_map = {(p.get("name"), p.get("in")): p for p in new_params if p.get("name") and p.get("in")}

        # Check for parameter deletions/changes
        for (name, p_in), base_p in base_param_map.items():
            if (name, p_in) not in new_param_map:
                self.breaking_changes.append(
                    f"{endpoint_label}: Deleted parameter `{name}` in `{p_in}`"
                )
                continue

            new_p = new_param_map[(name, p_in)]
            self._compare_parameter(endpoint_label, base_p, new_p)

        # Check for newly added parameters
        for (name, p_in), new_p in new_param_map.items():
            if (name, p_in) not in base_param_map:
                is_required = new_p.get("required", False)
                if is_required:
                    self.breaking_changes.append(
                        f"{endpoint_label}: Added required parameter `{name}` in `{p_in}`"
                    )
                else:
                    self.non_breaking_changes.append(
                        f"{endpoint_label}: Added optional parameter `{name}` in `{p_in}`"
                    )

        # Compare requestBody if present
        self._compare_request_body(endpoint_label, base_op.get("requestBody"), new_op.get("requestBody"))

    def _resolve_operation_params(self, op: Dict[str, Any], resolver: RefResolver) -> List[Dict[str, Any]]:
        resolved_params = []
        raw_params = op.get("parameters", [])
        for p in raw_params:
            if "$ref" in p:
                try:
                    resolved = resolver.resolve_pointer(p["$ref"])
                    if isinstance(resolved, dict):
                        resolved_params.append(resolved)
                except Exception:
                    pass
            elif isinstance(p, dict):
                resolved_params.append(p)
        return resolved_params

    def _compare_parameter(self, endpoint: str, base_p: Dict[str, Any], new_p: Dict[str, Any]) -> None:
        name = base_p.get("name")
        p_in = base_p.get("in")

        # Check required flag
        base_req = base_p.get("required", False)
        new_req = new_p.get("required", False)
        if not base_req and new_req:
            self.breaking_changes.append(
                f"{endpoint}: Parameter `{name}` in `{p_in}` changed from optional to required"
            )
        elif base_req and not new_req:
            self.non_breaking_changes.append(
                f"{endpoint}: Parameter `{name}` in `{p_in}` changed from required to optional"
            )

        # Compare schema types
        base_type = self._get_schema_type(base_p.get("schema"), self.base_resolver)
        new_type = self._get_schema_type(new_p.get("schema"), self.new_resolver)

        if base_type != new_type:
            self.breaking_changes.append(
                f"{endpoint}: Parameter `{name}` in `{p_in}` type changed from `{base_type}` to `{new_type}`"
            )

    def _get_schema_type(self, schema: Any, resolver: RefResolver) -> str:
        if not isinstance(schema, dict):
            return "any"
        if "$ref" in schema:
            try:
                resolved = resolver.resolve_pointer(schema["$ref"])
                return self._get_schema_type(resolved, resolver)
            except Exception:
                return schema["$ref"].split("/")[-1]
        return schema.get("type", "any")

    def _compare_request_body(self, endpoint: str, base_body: Any, new_body: Any) -> None:
        # If body is missing/added
        if not base_body and not new_body:
            return
        
        # Resolve body refs
        if isinstance(base_body, dict) and "$ref" in base_body:
            try:
                base_body = self.base_resolver.resolve_pointer(base_body["$ref"])
            except Exception:
                base_body = None
        if isinstance(new_body, dict) and "$ref" in new_body:
            try:
                new_body = self.new_resolver.resolve_pointer(new_body["$ref"])
            except Exception:
                new_body = None

        if base_body and not new_body:
            # We had request body, now we don't. That could be breaking if we expected properties.
            # But let's check if it was required.
            if base_body.get("required", False):
                self.breaking_changes.append(f"{endpoint}: Removed required request body")
            return
        if not base_body and new_body:
            if new_body.get("required", False):
                self.breaking_changes.append(f"{endpoint}: Added required request body")
            else:
                self.non_breaking_changes.append(f"{endpoint}: Added optional request body")
            return

        # Both exist, compare content schemas
        base_content = base_body.get("content", {})
        new_content = new_body.get("content", {})

        # We typically compare the application/json media type as it's the primary one for agent APIs
        media_types = set(base_content.keys()).union(set(new_content.keys()))
        for mtype in media_types:
            if mtype not in new_content:
                # Removed supported content type
                self.breaking_changes.append(f"{endpoint}: Removed support for media type `{mtype}`")
                continue
            if mtype not in base_content:
                self.non_breaking_changes.append(f"{endpoint}: Added support for media type `{mtype}`")
                continue

            base_schema = base_content[mtype].get("schema", {})
            new_schema = new_content[mtype].get("schema", {})
            self._compare_json_schemas(endpoint, base_schema, new_schema)

    def _compare_json_schemas(self, endpoint: str, base_schema: Dict[str, Any], new_schema: Dict[str, Any]) -> None:
        base_flat = self._flatten_schema(base_schema, self.base_resolver)
        new_flat = self._flatten_schema(new_schema, self.new_resolver)

        # Check for field deletions/changes
        for field, (ftype, freq) in base_flat.items():
            if field not in new_flat:
                self.breaking_changes.append(
                    f"{endpoint}: Request body field `{field}` deleted"
                )
                continue
            
            new_ftype, new_freq = new_flat[field]
            if ftype != new_ftype:
                self.breaking_changes.append(
                    f"{endpoint}: Request body field `{field}` type changed from `{ftype}` to `{new_ftype}`"
                )
            elif not freq and new_freq:
                self.breaking_changes.append(
                    f"{endpoint}: Request body field `{field}` changed from optional to required"
                )
            elif freq and not new_freq:
                self.non_breaking_changes.append(
                    f"{endpoint}: Request body field `{field}` changed from required to optional"
                )

        # Check for added fields
        for field, (ftype, freq) in new_flat.items():
            if field not in base_flat:
                if freq:
                    self.breaking_changes.append(
                        f"{endpoint}: Added required request body field `{field}`"
                    )
                else:
                    self.non_breaking_changes.append(
                        f"{endpoint}: Added optional request body field `{field}`"
                    )

    def _flatten_schema(self, schema: Dict[str, Any], resolver: RefResolver, prefix: str = "", visited: Set[str] = None) -> Dict[str, Tuple[str, bool]]:
        """
        Flattens schema properties recursively. Returns dict: { 'field_path': (type, required) }
        """
        if visited is None:
            visited = set()

        if not isinstance(schema, dict):
            return {}

        if "$ref" in schema:
            ref_path = schema["$ref"]
            if ref_path in visited:
                return {}
            try:
                resolved = resolver.resolve_pointer(ref_path)
                new_visited = visited.copy()
                new_visited.add(ref_path)
                return self._flatten_schema(resolved, resolver, prefix, new_visited)
            except Exception:
                return {}

        # Combine properties from combinations (allOf/anyOf/oneOf)
        properties = {}
        for combiner in ["allOf", "anyOf", "oneOf"]:
            if combiner in schema:
                for sub in schema[combiner]:
                    if isinstance(sub, dict):
                        if "$ref" in sub:
                            try:
                                sub = resolver.resolve_pointer(sub["$ref"])
                            except Exception:
                                continue
                        if isinstance(sub, dict) and "properties" in sub:
                            properties.update(sub["properties"])

        if "properties" in schema:
            properties.update(schema["properties"])

        reqs = set(schema.get("required", []))
        fields = {}

        for prop_name, prop_data in properties.items():
            if not isinstance(prop_data, dict):
                continue

            full_path = f"{prefix}{prop_name}"
            is_req = prop_name in reqs
            prop_type = prop_data.get("type", "any")

            if "$ref" in prop_data:
                ref_path = prop_data["$ref"]
                try:
                    resolved = resolver.resolve_pointer(ref_path)
                    ref_type = resolved.get("type", "object")
                    fields[full_path] = (ref_type, is_req)
                    # Recurse
                    nested = self._flatten_schema(resolved, resolver, f"{full_path}.", visited)
                    fields.update(nested)
                except Exception:
                    fields[full_path] = (ref_path.split("/")[-1], is_req)
            elif prop_type == "object" and "properties" in prop_data:
                fields[full_path] = ("object", is_req)
                nested = self._flatten_schema(prop_data, resolver, f"{full_path}.", visited)
                fields.update(nested)
            elif prop_type == "array" and "items" in prop_data:
                items_data = prop_data["items"]
                if isinstance(items_data, dict):
                    if "$ref" in items_data:
                        try:
                            resolved = resolver.resolve_pointer(items_data["$ref"])
                            fields[full_path] = (f"array of {resolved.get('type', 'object')}", is_req)
                            nested = self._flatten_schema(resolved, resolver, f"{full_path}[].", visited)
                            fields.update(nested)
                        except Exception:
                            fields[full_path] = ("array", is_req)
                    elif items_data.get("type") == "object" and "properties" in items_data:
                        fields[full_path] = ("array of objects", is_req)
                        nested = self._flatten_schema(items_data, resolver, f"{full_path}[].", visited)
                        fields.update(nested)
                    else:
                        fields[full_path] = (f"array of {items_data.get('type', 'any')}", is_req)
                else:
                    fields[full_path] = ("array", is_req)
            else:
                fields[full_path] = (prop_type, is_req)

        return fields

def compare_specs(base_spec: Dict[str, Any], new_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Compare two OpenAPI specs and return a dictionary of breaking and non-breaking changes."""
    comparator = OpenAPIComparator(base_spec, new_spec)
    return comparator.compare()
