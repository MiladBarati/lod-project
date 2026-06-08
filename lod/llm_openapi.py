import json
from typing import Any, Dict, List, Set, Union, Optional
from .ref_resolver import RefResolver

class LLMOpenAPIConverter:
    """
    Parses OpenAPI 3.x specifications and generates token-optimized LOM (LLM-Optimized Markdown) format.
    Delegates to model-specific formatters if specified, otherwise uses the generic LOM format.
    """
    def __init__(self, spec: Dict[str, Any], model: Optional[str] = None):
        self.spec = spec
        self.resolver = RefResolver(spec)
        self.model = model.lower() if model else None

    def convert(self) -> str:
        if self.model == "claude":
            formatter = ClaudeXMLFormatter(self.spec, self.resolver)
        elif self.model == "gpt":
            formatter = GPTYAMLFormatter(self.spec, self.resolver)
        elif self.model == "gemini":
            formatter = GeminiTypeScriptFormatter(self.spec, self.resolver)
        else:
            formatter = GenericFormatter(self.spec, self.resolver)
        return formatter.convert()


class GenericFormatter:
    """
    Standard generic LOM (LLM-Optimized Markdown) formatter.
    Preserves exact original behavior for backward compatibility.
    """
    def __init__(self, spec: Dict[str, Any], resolver: RefResolver):
        self.spec = spec
        self.resolver = resolver

    def convert(self) -> str:
        md = []
        info = self.spec.get("info", {})
        title = info.get("title", "API Spec")
        version = info.get("version", "1.0.0")
        desc = info.get("description", "")
        
        md.append(f"# {title} (v{version})")
        if desc:
            md.append(f"desc: {desc.strip()}\n")
            
        components = self.spec.get("components", {})
        schemas = components.get("schemas", {})
        if schemas:
            md.append("definitions:")
            for schema_name, schema_body in schemas.items():
                md.extend(self._format_property(schema_name, schema_body, indent=2))
            md.append("")
            
        paths = self.spec.get("paths", {})
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            shared_params = path_item.get("parameters", [])
            for method, op in path_item.items():
                if method.lower() not in ["get", "post", "put", "delete", "patch", "options", "head", "trace"]:
                    continue
                if not isinstance(op, dict):
                    continue
                
                md.append(self._render_operation(path, method.upper(), op, shared_params))
                
        return "\n".join(md)

    def _render_operation(self, path: str, method: str, op: Dict[str, Any], shared_params: List[Dict[str, Any]]) -> str:
        summary = op.get("summary", "")
        summary_str = f' "{summary}"' if summary else ""
        desc = op.get("description", "").replace("\n", " ").strip()
        
        md = []
        md.append(f"{method} {path}{summary_str}")
        if desc:
            md.append(f"  desc: {desc}")
            
        security = op.get("security", self.spec.get("security", []))
        if security:
            auths = []
            for item in security:
                auths.extend(item.keys())
            md.append(f"  auth: {', '.join(auths)}")
            
        params = op.get("parameters", []) + shared_params
        if params:
            grouped_params = {}
            for param in params:
                if "$ref" in param:
                    try:
                        param = self.resolver.resolve_pointer(param["$ref"])
                    except:
                        continue
                if not isinstance(param, dict):
                    continue
                p_in = param.get("in", "query")
                if p_in not in grouped_params:
                    grouped_params[p_in] = []
                grouped_params[p_in].append(param)
                
            if grouped_params:
                md.append("  params:")
                for p_in, p_list in grouped_params.items():
                    md.append(f"    {p_in}:")
                    for p in p_list:
                        name = p.get("name", "")
                        req = " (required)" if p.get("required") else ""
                        pdesc = p.get("description", "").replace("\n", " ").strip()
                        pschema = p.get("schema", {})
                        ptype = "any"
                        if isinstance(pschema, dict):
                            ptype = pschema.get("type", "any")
                        pcomment = f" # {pdesc}" if pdesc else ""
                        md.append(f"      {name}: {ptype}{req}{pcomment}")
                        
        req_body = op.get("requestBody")
        if req_body:
            if "$ref" in req_body:
                try:
                    req_body = self.resolver.resolve_pointer(req_body["$ref"])
                except:
                    req_body = None
            if isinstance(req_body, dict):
                md.append("  req:")
                content = req_body.get("content", {})
                for ctype, cdetails in content.items():
                    schema = cdetails.get("schema", {})
                    md.extend(self._format_property(ctype, schema, indent=4))
                    
        responses = op.get("responses", {})
        if responses:
            md.append("  res:")
            for code, resp in responses.items():
                if "$ref" in resp:
                    try:
                        resp = self.resolver.resolve_pointer(resp["$ref"])
                    except:
                        continue
                if not isinstance(resp, dict):
                    continue
                rdesc = resp.get("description", "").replace("\n", " ").strip()
                rdesc_comment = f" # {rdesc}" if rdesc else ""
                
                rcontent = resp.get("content", {})
                if rcontent:
                    for ctype, cdetails in rcontent.items():
                        schema = cdetails.get("schema", {})
                        md.append(f"    {code}:{rdesc_comment}")
                        md.extend(self._format_property(ctype, schema, indent=6))
                else:
                    md.append(f"    {code}:{rdesc_comment}")
                    
        md.append("")
        return "\n".join(md)

    def _format_property(self, name: str, schema: Any, indent: int = 0, required: bool = False, visited: Set[str] = None) -> List[str]:
        if visited is None:
            visited = set()
            
        indent_str = " " * indent
        req_str = " (required)" if required else ""
        
        if not isinstance(schema, dict):
            return [f"{indent_str}{name}: {schema}{req_str}"]
            
        if "$ref" in schema:
            ref_path = schema["$ref"]
            if ref_path.startswith("#/components/schemas/"):
                ref_name = ref_path.split("/")[-1]
                sdesc = schema.get("description", "").replace("\n", " ").strip()
                comment_str = f" # {sdesc}" if sdesc else ""
                return [f"{indent_str}{name}: ${ref_name}{req_str}{comment_str}"]
            elif ref_path in visited or schema.get("circular"):
                ref_name = ref_path.split("/")[-1]
                return [f"{indent_str}{name}: [Circular: {ref_name}]{req_str}"]
            else:
                try:
                    new_visited = visited.copy()
                    new_visited.add(ref_path)
                    resolved = self.resolver.resolve_pointer(ref_path)
                    return self._format_property(name, resolved, indent, required, new_visited)
                except:
                    pass
            
        stype = schema.get("type", "any")
        sdesc = schema.get("description", "").replace("\n", " ").strip()
        default = schema.get("default")
        example = schema.get("example")
        
        comment_parts = []
        if sdesc:
            comment_parts.append(sdesc)
        if default is not None:
            comment_parts.append(f"default: {default}")
        if example is not None:
            comment_parts.append(f"example: {example}")
        comment_str = f" # {', '.join(comment_parts)}" if comment_parts else ""
        
        combiner = None
        for c in ["allOf", "anyOf", "oneOf"]:
            if c in schema:
                combiner = c
                break
                
        if combiner:
            lines = [f"{indent_str}{name} ({combiner}):{comment_str}"]
            for i, item in enumerate(schema[combiner]):
                lines.extend(self._format_property(f"option_{i}", item, indent + 2, visited=visited))
            return lines

        if stype == "object":
            properties = schema.get("properties", {})
            required_fields = set(schema.get("required", []))
            
            if not properties:
                return [f"{indent_str}{name}: object{req_str}{comment_str}"]
                
            lines = [f"{indent_str}{name}: object{req_str}{comment_str}"]
            for prop_name, prop_data in properties.items():
                is_req = prop_name in required_fields
                lines.extend(self._format_property(prop_name, prop_data, indent + 2, is_req, visited))
            return lines
            
        elif stype == "array":
            items = schema.get("items")
            if isinstance(items, dict):
                if "$ref" in items:
                    ref_path = items["$ref"]
                    if ref_path.startswith("#/components/schemas/"):
                        ref_name = ref_path.split("/")[-1]
                        return [f"{indent_str}{name}: array of ${ref_name}{req_str}{comment_str}"]
                    elif ref_path in visited or items.get("circular"):
                        ref_name = items["$ref"].split("/")[-1]
                        return [f"{indent_str}{name}: array of [Circular: {ref_name}]{req_str}{comment_str}"]
                    else:
                        try:
                            new_visited = visited.copy()
                            new_visited.add(ref_path)
                            resolved = self.resolver.resolve_pointer(ref_path)
                            items = resolved
                        except:
                            pass
                            
                if isinstance(items, dict):
                    item_type = items.get("type", "any")
                    if item_type == "object":
                        lines = [f"{indent_str}{name}: array of object{req_str}{comment_str}"]
                        properties = items.get("properties", {})
                        required_fields = set(items.get("required", []))
                        for prop_name, prop_data in properties.items():
                            is_req = prop_name in required_fields
                            lines.extend(self._format_property(prop_name, prop_data, indent + 2, is_req, visited))
                        return lines
                    elif "$ref" in items and items.get("circular"):
                        ref_name = items["$ref"].split("/")[-1]
                        return [f"{indent_str}{name}: array of [Circular: {ref_name}]{req_str}{comment_str}"]
                    else:
                        return [f"{indent_str}{name}: array of {item_type}{req_str}{comment_str}"]
                else:
                    return [f"{indent_str}{name}: array{req_str}{comment_str}"]
            else:
                return [f"{indent_str}{name}: array{req_str}{comment_str}"]
                
        else:
            return [f"{indent_str}{name}: {stype}{req_str}{comment_str}"]


class ClaudeXMLFormatter:
    """
    XML-tagged formatter optimized for Claude models.
    """
    def __init__(self, spec: Dict[str, Any], resolver: RefResolver):
        self.spec = spec
        self.resolver = resolver

    def convert(self) -> str:
        info = self.spec.get("info", {})
        title = info.get("title", "API Spec")
        version = info.get("version", "1.0.0")
        desc = info.get("description", "")
        
        lines = []
        lines.append(f'<api title="{title}" version="{version}">')
        if desc:
            lines.append(f'  <description>{desc.strip()}</description>')
            
        components = self.spec.get("components", {})
        schemas = components.get("schemas", {})
        if schemas:
            lines.append("  <definitions>")
            for schema_name, schema_body in schemas.items():
                lines.extend(self._format_property_xml(schema_body, name=schema_name, indent=4))
            lines.append("  </definitions>")
        
        paths = self.spec.get("paths", {})
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            shared_params = path_item.get("parameters", [])
            for method, op in path_item.items():
                if method.lower() not in ["get", "post", "put", "delete", "patch", "options", "head", "trace"]:
                    continue
                if not isinstance(op, dict):
                    continue
                lines.append(self._render_operation(path, method.upper(), op, shared_params))
                
        lines.append('</api>')
        return "\n".join(lines)

    def _render_operation(self, path: str, method: str, op: Dict[str, Any], shared_params: List[Dict[str, Any]]) -> str:
        summary = op.get("summary", "")
        desc = op.get("description", "").replace("\n", " ").strip()
        if not desc and summary:
            desc = summary
        
        lines = ["  <endpoint>"]
        lines.append(f"    <path>{method} {path}</path>")
        if summary:
            lines.append(f"    <summary>{summary}</summary>")
        if desc:
            lines.append(f"    <description>{desc}</description>")
            
        security = op.get("security", self.spec.get("security", []))
        if security:
            auths = []
            for item in security:
                auths.extend(item.keys())
            lines.append(f"    <auth>{', '.join(auths)}</auth>")
            
        params = op.get("parameters", []) + shared_params
        if params:
            grouped_params = {}
            for param in params:
                if "$ref" in param:
                    try:
                        param = self.resolver.resolve_pointer(param["$ref"])
                    except:
                        continue
                if not isinstance(param, dict):
                    continue
                p_in = param.get("in", "query")
                if p_in not in grouped_params:
                    grouped_params[p_in] = []
                grouped_params[p_in].append(param)
                
            if grouped_params:
                lines.append("    <parameters>")
                for p_in, p_list in grouped_params.items():
                    for p in p_list:
                        name = p.get("name", "")
                        req = "true" if p.get("required") else "false"
                        pdesc = p.get("description", "").replace("\n", " ").strip()
                        pschema = p.get("schema", {})
                        ptype = "any"
                        if isinstance(pschema, dict):
                            ptype = pschema.get("type", "any")
                        lines.append(f'      <{p_in} name="{name}" type="{ptype}" required="{req}">{pdesc}</{p_in}>')
                lines.append("    </parameters>")
                
        req_body = op.get("requestBody")
        if req_body:
            if "$ref" in req_body:
                try:
                    req_body = self.resolver.resolve_pointer(req_body["$ref"])
                except:
                    req_body = None
            if isinstance(req_body, dict):
                content = req_body.get("content", {})
                for ctype, cdetails in content.items():
                    schema = cdetails.get("schema", {})
                    lines.append(f'    <request_body content_type="{ctype}">')
                    lines.extend(self._format_property_xml(schema, indent=6))
                    lines.append('    </request_body>')
                    
        responses = op.get("responses", {})
        if responses:
            lines.append("    <responses>")
            for code, resp in responses.items():
                if "$ref" in resp:
                    try:
                        resp = self.resolver.resolve_pointer(resp["$ref"])
                    except:
                        continue
                if not isinstance(resp, dict):
                    continue
                rdesc = resp.get("description", "").replace("\n", " ").strip()
                rdesc_attr = f' description="{rdesc}"' if rdesc else ""
                
                rcontent = resp.get("content", {})
                if rcontent:
                    for ctype, cdetails in rcontent.items():
                        schema = cdetails.get("schema", {})
                        lines.append(f'      <response code="{code}"{rdesc_attr} content_type="{ctype}">')
                        lines.extend(self._format_property_xml(schema, indent=8))
                        lines.append('      </response>')
                else:
                    lines.append(f'      <response code="{code}"{rdesc_attr} />')
            lines.append("    </responses>")
            
        lines.append("  </endpoint>")
        return "\n".join(lines)

    def _format_property_xml(self, schema: Any, name: Optional[str] = None, indent: int = 0, required: bool = False, visited: Set[str] = None) -> List[str]:
        if visited is None:
            visited = set()
            
        indent_str = " " * indent
        name_attr = f' name="{name}"' if name else ""
        req_attr = ' required="true"' if required else ""
        
        if not isinstance(schema, dict):
            return [f'{indent_str}<property{name_attr} type="{schema}"{req_attr} />']
            
        if "$ref" in schema:
            ref_path = schema["$ref"]
            if ref_path.startswith("#/components/schemas/"):
                ref_name = ref_path.split("/")[-1]
                sdesc = schema.get("description", "").replace("\n", " ").strip()
                desc_attr = f' description="{sdesc}"' if sdesc else ""
                return [f'{indent_str}<property{name_attr} ref="{ref_name}"{req_attr}{desc_attr} />']
            elif ref_path in visited or schema.get("circular"):
                ref_name = ref_path.split("/")[-1]
                return [f'{indent_str}<property{name_attr} type="[Circular: {ref_name}]"{req_attr} />']
            else:
                try:
                    new_visited = visited.copy()
                    new_visited.add(ref_path)
                    resolved = self.resolver.resolve_pointer(ref_path)
                    return self._format_property_xml(resolved, name, indent, required, new_visited)
                except:
                    pass
            
        stype = schema.get("type", "any")
        sdesc = schema.get("description", "").replace("\n", " ").strip()
        desc_attr = f' description="{sdesc}"' if sdesc else ""
        default = schema.get("default")
        default_attr = f' default="{default}"' if default is not None else ""
        example = schema.get("example")
        example_attr = f' example="{example}"' if example is not None else ""
        
        combiner = None
        for c in ["allOf", "anyOf", "oneOf"]:
            if c in schema:
                combiner = c
                break
                
        if combiner:
            lines = [f'{indent_str}<property{name_attr} type="combiner" combiner="{combiner}"{req_attr}{desc_attr}>']
            for i, item in enumerate(schema[combiner]):
                lines.extend(self._format_property_xml(item, f"option_{i}", indent + 2, visited=visited))
            lines.append(f'{indent_str}</property>')
            return lines

        if stype == "object":
            properties = schema.get("properties", {})
            required_fields = set(schema.get("required", []))
            
            if not properties:
                return [f'{indent_str}<property{name_attr} type="object"{req_attr}{desc_attr}{default_attr}{example_attr} />']
                
            lines = [f'{indent_str}<property{name_attr} type="object"{req_attr}{desc_attr}{default_attr}{example_attr}>']
            for prop_name, prop_data in properties.items():
                is_req = prop_name in required_fields
                lines.extend(self._format_property_xml(prop_data, prop_name, indent + 2, is_req, visited))
            lines.append(f'{indent_str}</property>')
            return lines
            
        elif stype == "array":
            items = schema.get("items")
            if isinstance(items, dict):
                if "$ref" in items:
                    ref_path = items["$ref"]
                    if ref_path.startswith("#/components/schemas/"):
                        ref_name = ref_path.split("/")[-1]
                        return [f'{indent_str}<property{name_attr} type="array" ref="{ref_name}"{req_attr}{desc_attr} />']
                    elif ref_path in visited or items.get("circular"):
                        ref_name = items["$ref"].split("/")[-1]
                        return [f'{indent_str}<property{name_attr} type="array" item_type="[Circular: {ref_name}]"{req_attr}{desc_attr} />']
                    else:
                        try:
                            new_visited = visited.copy()
                            new_visited.add(ref_path)
                            resolved = self.resolver.resolve_pointer(ref_path)
                            items = resolved
                        except:
                            pass
                            
                if isinstance(items, dict):
                    item_type = items.get("type", "any")
                    if item_type == "object":
                        lines = [f'{indent_str}<property{name_attr} type="array" item_type="object"{req_attr}{desc_attr}>']
                        properties = items.get("properties", {})
                        required_fields = set(items.get("required", []))
                        for prop_name, prop_data in properties.items():
                            is_req = prop_name in required_fields
                            lines.extend(self._format_property_xml(prop_data, prop_name, indent + 2, is_req, visited))
                        lines.append(f'{indent_str}</property>')
                        return lines
                    elif "$ref" in items and items.get("circular"):
                        ref_name = items["$ref"].split("/")[-1]
                        return [f'{indent_str}<property{name_attr} type="array" item_type="[Circular: {ref_name}]"{req_attr}{desc_attr} />']
                    else:
                        return [f'{indent_str}<property{name_attr} type="array" item_type="{item_type}"{req_attr}{desc_attr}{default_attr}{example_attr} />']
                else:
                    return [f'{indent_str}<property{name_attr} type="array" item_type="any"{req_attr}{desc_attr} />']
            else:
                return [f'{indent_str}<property{name_attr} type="array" item_type="any"{req_attr}{desc_attr} />']
                
        else:
            return [f'{indent_str}<property{name_attr} type="{stype}"{req_attr}{desc_attr}{default_attr}{example_attr} />']


class GPTYAMLFormatter:
    """
    Whitespace-sensitive, comments-annotated YAML structure optimized for GPT models.
    """
    def __init__(self, spec: Dict[str, Any], resolver: RefResolver):
        self.spec = spec
        self.resolver = resolver

    def convert(self) -> str:
        info = self.spec.get("info", {})
        title = info.get("title", "API Spec")
        version = info.get("version", "1.0.0")
        desc = info.get("description", "")
        
        md = []
        md.append("info:")
        md.append(f"  title: {title}")
        md.append(f"  version: {version}")
        if desc:
            desc_val = desc.replace("\n", " ").strip()
            md.append(f"  desc: {desc_val}")
        md.append("")
        
        components = self.spec.get("components", {})
        schemas = components.get("schemas", {})
        if schemas:
            md.append("definitions:")
            for schema_name, schema_body in schemas.items():
                md.extend(self._format_property(schema_name, schema_body, indent=2))
            md.append("")
        
        paths = self.spec.get("paths", {})
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            shared_params = path_item.get("parameters", [])
            for method, op in path_item.items():
                if method.lower() not in ["get", "post", "put", "delete", "patch", "options", "head", "trace"]:
                    continue
                if not isinstance(op, dict):
                    continue
                md.append(self._render_operation(path, method.upper(), op, shared_params))
                
        return "\n".join(md)

    def _render_operation(self, path: str, method: str, op: Dict[str, Any], shared_params: List[Dict[str, Any]]) -> str:
        desc = op.get("description", "").replace("\n", " ").strip()
        summary = op.get("summary", "")
        if not desc and summary:
            desc = summary
            
        md = []
        md.append(f"{method} {path}:")
        if desc:
            md.append(f"  desc: {desc}")
            
        security = op.get("security", self.spec.get("security", []))
        if security:
            auths = []
            for item in security:
                auths.extend(item.keys())
            md.append(f"  auth: {', '.join(auths)}")
            
        params = op.get("parameters", []) + shared_params
        if params:
            grouped_params = {}
            for param in params:
                if "$ref" in param:
                    try:
                        param = self.resolver.resolve_pointer(param["$ref"])
                    except:
                        continue
                if not isinstance(param, dict):
                    continue
                p_in = param.get("in", "query")
                if p_in not in grouped_params:
                    grouped_params[p_in] = []
                grouped_params[p_in].append(param)
                
            if grouped_params:
                md.append("  params:")
                for p_in, p_list in grouped_params.items():
                    md.append(f"    {p_in}:")
                    for p in p_list:
                        name = p.get("name", "")
                        req = " (required)" if p.get("required") else ""
                        pdesc = p.get("description", "").replace("\n", " ").strip()
                        pschema = p.get("schema", {})
                        ptype = "any"
                        if isinstance(pschema, dict):
                            ptype = pschema.get("type", "any")
                        pcomment = f" # {pdesc}" if pdesc else ""
                        md.append(f"      {name}: {ptype}{req}{pcomment}")
                        
        req_body = op.get("requestBody")
        if req_body:
            if "$ref" in req_body:
                try:
                    req_body = self.resolver.resolve_pointer(req_body["$ref"])
                except:
                    req_body = None
            if isinstance(req_body, dict):
                md.append("  req:")
                content = req_body.get("content", {})
                for ctype, cdetails in content.items():
                    schema = cdetails.get("schema", {})
                    md.extend(self._format_property(ctype, schema, indent=4))
                    
        responses = op.get("responses", {})
        if responses:
            md.append("  res:")
            for code, resp in responses.items():
                if "$ref" in resp:
                    try:
                        resp = self.resolver.resolve_pointer(resp["$ref"])
                    except:
                        continue
                if not isinstance(resp, dict):
                    continue
                rdesc = resp.get("description", "").replace("\n", " ").strip()
                rdesc_comment = f" # {rdesc}" if rdesc else ""
                
                rcontent = resp.get("content", {})
                if rcontent:
                    for ctype, cdetails in rcontent.items():
                        schema = cdetails.get("schema", {})
                        md.append(f"    {code}:{rdesc_comment}")
                        md.extend(self._format_property(ctype, schema, indent=6))
                else:
                    md.append(f"    {code}:{rdesc_comment}")
                    
        md.append("")
        return "\n".join(md)

    def _format_property(self, name: str, schema: Any, indent: int = 0, required: bool = False, visited: Set[str] = None) -> List[str]:
        if visited is None:
            visited = set()
            
        indent_str = " " * indent
        req_str = " (required)" if required else ""
        
        if not isinstance(schema, dict):
            return [f"{indent_str}{name}: {schema}{req_str}"]
            
        if "$ref" in schema:
            ref_path = schema["$ref"]
            if ref_path.startswith("#/components/schemas/"):
                ref_name = ref_path.split("/")[-1]
                sdesc = schema.get("description", "").replace("\n", " ").strip()
                comment_str = f" # {sdesc}" if sdesc else ""
                return [f"{indent_str}{name}: ${ref_name}{req_str}{comment_str}"]
            elif ref_path in visited or schema.get("circular"):
                ref_name = ref_path.split("/")[-1]
                return [f"{indent_str}{name}: [Circular: {ref_name}]{req_str}"]
            else:
                try:
                    new_visited = visited.copy()
                    new_visited.add(ref_path)
                    resolved = self.resolver.resolve_pointer(ref_path)
                    return self._format_property(name, resolved, indent, required, new_visited)
                except:
                    pass
            
        stype = schema.get("type", "any")
        sdesc = schema.get("description", "").replace("\n", " ").strip()
        default = schema.get("default")
        example = schema.get("example")
        
        comment_parts = []
        if sdesc:
            comment_parts.append(sdesc)
        if default is not None:
            comment_parts.append(f"default: {default}")
        if example is not None:
            comment_parts.append(f"example: {example}")
        comment_str = f" # {', '.join(comment_parts)}" if comment_parts else ""
        
        combiner = None
        for c in ["allOf", "anyOf", "oneOf"]:
            if c in schema:
                combiner = c
                break
                
        if combiner:
            lines = [f"{indent_str}{name} ({combiner}):{comment_str}"]
            for i, item in enumerate(schema[combiner]):
                lines.extend(self._format_property(f"option_{i}", item, indent + 2, visited=visited))
            return lines

        if stype == "object":
            properties = schema.get("properties", {})
            required_fields = set(schema.get("required", []))
            
            if not properties:
                return [f"{indent_str}{name}: object{req_str}{comment_str}"]
                
            lines = [f"{indent_str}{name}: object{req_str}{comment_str}"]
            for prop_name, prop_data in properties.items():
                is_req = prop_name in required_fields
                lines.extend(self._format_property(prop_name, prop_data, indent + 2, is_req, visited))
            return lines
            
        elif stype == "array":
            items = schema.get("items")
            if isinstance(items, dict):
                if "$ref" in items:
                    ref_path = items["$ref"]
                    if ref_path.startswith("#/components/schemas/"):
                        ref_name = ref_path.split("/")[-1]
                        return [f"{indent_str}{name}: array of ${ref_name}{req_str}{comment_str}"]
                    elif ref_path in visited or items.get("circular"):
                        ref_name = items["$ref"].split("/")[-1]
                        return [f"{indent_str}{name}: array of [Circular: {ref_name}]{req_str}{comment_str}"]
                    else:
                        try:
                            new_visited = visited.copy()
                            new_visited.add(ref_path)
                            resolved = self.resolver.resolve_pointer(ref_path)
                            items = resolved
                        except:
                            pass
                            
                if isinstance(items, dict):
                    item_type = items.get("type", "any")
                    if item_type == "object":
                        lines = [f"{indent_str}{name}: array of object{req_str}{comment_str}"]
                        properties = items.get("properties", {})
                        required_fields = set(items.get("required", []))
                        for prop_name, prop_data in properties.items():
                            is_req = prop_name in required_fields
                            lines.extend(self._format_property(prop_name, prop_data, indent + 2, is_req, visited))
                        return lines
                    elif "$ref" in items and items.get("circular"):
                        ref_name = items["$ref"].split("/")[-1]
                        return [f"{indent_str}{name}: array of [Circular: {ref_name}]{req_str}{comment_str}"]
                    else:
                        return [f"{indent_str}{name}: array of {item_type}{req_str}{comment_str}"]
                else:
                    return [f"{indent_str}{name}: array{req_str}{comment_str}"]
            else:
                return [f"{indent_str}{name}: array{req_str}{comment_str}"]
                
        else:
            return [f"{indent_str}{name}: {stype}{req_str}{comment_str}"]


class GeminiTypeScriptFormatter:
    """
    TypeScript typed interface and signature formatter optimized for Gemini models.
    """
    def __init__(self, spec: Dict[str, Any], resolver: RefResolver):
        self.spec = spec
        self.resolver = resolver

    def convert(self) -> str:
        info = self.spec.get("info", {})
        title = info.get("title", "API Spec")
        version = info.get("version", "1.0.0")
        desc = info.get("description", "")
        
        md = []
        md.append(f"// {title} (v{version})")
        if desc:
            desc_val = desc.replace("\n", " ").strip()
            md.append(f"// {desc_val}\n")
            
        components = self.spec.get("components", {})
        schemas = components.get("schemas", {})
        if schemas:
            for schema_name, schema_body in schemas.items():
                stype = schema_body.get("type", "object")
                sdesc = schema_body.get("description", "").replace("\n", " ").strip()
                comment = f" // {sdesc}" if sdesc else ""
                
                if stype == "object":
                    md.append(f"interface {schema_name} {{{comment}")
                    properties = schema_body.get("properties", {})
                    required_fields = set(schema_body.get("required", []))
                    for prop_name, prop_data in properties.items():
                        is_req = prop_name in required_fields
                        md.extend(self._format_property_ts(prop_name, prop_data, indent=2, required=is_req))
                    md.append("}\n")
                else:
                    ts_type = self._openapi_to_ts_type(stype)
                    md.append(f"type {schema_name} = {ts_type};{comment}\n")
            
        paths = self.spec.get("paths", {})
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            shared_params = path_item.get("parameters", [])
            for method, op in path_item.items():
                if method.lower() not in ["get", "post", "put", "delete", "patch", "options", "head", "trace"]:
                    continue
                if not isinstance(op, dict):
                    continue
                md.append(self._render_operation(path, method.upper(), op, shared_params))
                
        return "\n".join(md)

    def _generate_base_name(self, method: str, path: str, op: Dict[str, Any]) -> str:
        op_id = op.get("operationId")
        if op_id:
            clean_id = "".join([c if c.isalnum() or c == "_" else "_" for c in op_id])
            return clean_id[0].lower() + clean_id[1:] if clean_id else "endpoint"
            
        path_parts = [p.strip("{}") for p in path.split("/") if p.strip() and p not in ("v1", "v2")]
        if not path_parts:
            path_parts = ["root"]
        clean_parts = []
        for part in path_parts:
            clean_part = "".join([c if c.isalnum() else "" for c in part])
            if clean_part:
                clean_parts.append(clean_part.capitalize())
        return method.lower() + "".join(clean_parts)

    def _openapi_to_ts_type(self, stype: str) -> str:
        if stype in ("integer", "number"):
            return "number"
        if stype == "boolean":
            return "boolean"
        if stype == "string":
            return "string"
        return "any"

    def _render_operation(self, path: str, method: str, op: Dict[str, Any], shared_params: List[Dict[str, Any]]) -> str:
        summary = op.get("summary", "")
        desc = op.get("description", "").replace("\n", " ").strip()
        if not desc and summary:
            desc = summary
            
        md = []
        md.append(f"// {method} {path}")
        if summary:
            md.append(f"// {summary}")
        if desc:
            md.append(f"// {desc}")
            
        base_name = self._generate_base_name(method, path, op)
        cap_name = base_name[0].upper() + base_name[1:]
        
        params = op.get("parameters", []) + shared_params
        has_params = False
        if params:
            param_lines = []
            for param in params:
                if "$ref" in param:
                    try:
                        param = self.resolver.resolve_pointer(param["$ref"])
                    except:
                        continue
                if not isinstance(param, dict):
                    continue
                name = param.get("name", "")
                req = param.get("required", False)
                pdesc = param.get("description", "").replace("\n", " ").strip()
                pschema = param.get("schema", {})
                ptype = "any"
                if isinstance(pschema, dict):
                    ptype = pschema.get("type", "any")
                ts_type = self._openapi_to_ts_type(ptype)
                opt = "" if req else "?"
                comment = f" // {pdesc}" if pdesc else ""
                param_lines.append(f"  {name}{opt}: {ts_type};{comment}")
                
            if param_lines:
                has_params = True
                md.append(f"interface {cap_name}Params {{")
                md.extend(param_lines)
                md.append("}")
                
        req_body = op.get("requestBody")
        has_req = False
        if req_body:
            if "$ref" in req_body:
                try:
                    req_body = self.resolver.resolve_pointer(req_body["$ref"])
                except:
                    req_body = None
            if isinstance(req_body, dict):
                content = req_body.get("content", {})
                for ctype, cdetails in content.items():
                    schema = cdetails.get("schema", {})
                    
                    if isinstance(schema, dict) and "$ref" in schema and schema["$ref"].startswith("#/components/schemas/"):
                        ref_name = schema["$ref"].split("/")[-1]
                        md.append(f"type {cap_name}Request = {ref_name};")
                        has_req = True
                    else:
                        resolved_schema = schema
                        if isinstance(resolved_schema, dict) and "$ref" in resolved_schema:
                            try:
                                resolved_schema = self.resolver.resolve_pointer(resolved_schema["$ref"])
                            except:
                                pass
                                
                        if isinstance(resolved_schema, dict) and resolved_schema.get("type") == "object":
                            md.append(f"interface {cap_name}Request {{")
                            properties = resolved_schema.get("properties", {})
                            required_fields = set(resolved_schema.get("required", []))
                            for prop_name, prop_data in properties.items():
                                is_req = prop_name in required_fields
                                md.extend(self._format_property_ts(prop_name, prop_data, indent=2, required=is_req))
                            md.append("}")
                            has_req = True
                        else:
                            stype = resolved_schema.get("type", "any") if isinstance(resolved_schema, dict) else "any"
                            ts_type = self._openapi_to_ts_type(stype)
                            md.append(f"type {cap_name}Request = {ts_type};")
                            has_req = True
                        
        responses = op.get("responses", {})
        has_res = False
        if responses:
            success_code = "200"
            for code in ["200", "201", "204", "202"]:
                if code in responses:
                    success_code = code
                    break
            if success_code not in responses and responses:
                success_code = list(responses.keys())[0]
                
            resp = responses[success_code]
            if "$ref" in resp:
                try:
                    resp = self.resolver.resolve_pointer(resp["$ref"])
                except:
                    resp = None
            if isinstance(resp, dict):
                rcontent = resp.get("content", {})
                if rcontent:
                    ctype = list(rcontent.keys())[0]
                    cdetails = rcontent[ctype]
                    schema = cdetails.get("schema", {})
                    
                    if isinstance(schema, dict) and "$ref" in schema and schema["$ref"].startswith("#/components/schemas/"):
                        ref_name = schema["$ref"].split("/")[-1]
                        md.append(f"type {cap_name}Response = {ref_name};")
                        has_res = True
                    else:
                        resolved_schema = schema
                        if isinstance(resolved_schema, dict) and "$ref" in resolved_schema:
                            try:
                                resolved_schema = self.resolver.resolve_pointer(resolved_schema["$ref"])
                            except:
                                pass
                                
                        if isinstance(resolved_schema, dict) and resolved_schema.get("type") == "object":
                            md.append(f"interface {cap_name}Response {{")
                            properties = resolved_schema.get("properties", {})
                            required_fields = set(resolved_schema.get("required", []))
                            for prop_name, prop_data in properties.items():
                                is_req = prop_name in required_fields
                                md.extend(self._format_property_ts(prop_name, prop_data, indent=2, required=is_req))
                            md.append("}")
                            has_res = True
                        else:
                            stype = resolved_schema.get("type", "any") if isinstance(resolved_schema, dict) else "any"
                            ts_type = self._openapi_to_ts_type(stype)
                            md.append(f"type {cap_name}Response = {ts_type};")
                            has_res = True
                            
        sig_args = []
        if has_params:
            sig_args.append(f"params: {cap_name}Params")
        if has_req:
            sig_args.append(f"req: {cap_name}Request")
        sig_args_str = ", ".join(sig_args)
        ret_str = f"{cap_name}Response" if has_res else "void"
        
        md.append(f"function {base_name}({sig_args_str}): Promise<{ret_str}>;")
        md.append("")
        return "\n".join(md)

    def _format_property_ts(self, name: str, schema: Any, indent: int = 0, required: bool = False, visited: Set[str] = None) -> List[str]:
        if visited is None:
            visited = set()
            
        indent_str = " " * indent
        opt_str = "" if required else "?"
        
        if not isinstance(schema, dict):
            ts_type = self._openapi_to_ts_type(str(schema))
            return [f"{indent_str}{name}{opt_str}: {ts_type};"]
            
        if "$ref" in schema:
            ref_path = schema["$ref"]
            if ref_path.startswith("#/components/schemas/"):
                ref_name = ref_path.split("/")[-1]
                sdesc = schema.get("description", "").replace("\n", " ").strip()
                comment = f" // {sdesc}" if sdesc else ""
                return [f"{indent_str}{name}{opt_str}: {ref_name};{comment}"]
            elif ref_path in visited or schema.get("circular"):
                ref_name = ref_path.split("/")[-1]
                return [f"{indent_str}{name}{opt_str}: [Circular: {ref_name}];"]
            else:
                try:
                    new_visited = visited.copy()
                    new_visited.add(ref_path)
                    resolved = self.resolver.resolve_pointer(ref_path)
                    return self._format_property_ts(name, resolved, indent, required, new_visited)
                except:
                    pass
            
        stype = schema.get("type", "any")
        sdesc = schema.get("description", "").replace("\n", " ").strip()
        comment = f" // {sdesc}" if sdesc else ""
        
        combiner = None
        for c in ["allOf", "anyOf", "oneOf"]:
            if c in schema:
                combiner = c
                break
                
        if combiner:
            return [f"{indent_str}{name}{opt_str}: any; // {combiner}"]

        if stype == "object":
            properties = schema.get("properties", {})
            required_fields = set(schema.get("required", []))
            
            if not properties:
                return [f"{indent_str}{name}{opt_str}: Record<string, any>;{comment}"]
                
            lines = [indent_str + f"{name}{opt_str}: {{" + comment]
            for prop_name, prop_data in properties.items():
                is_req = prop_name in required_fields
                lines.extend(self._format_property_ts(prop_name, prop_data, indent + 2, is_req, visited))
            lines.append(indent_str + "};")
            return lines
            
        elif stype == "array":
            items = schema.get("items")
            if isinstance(items, dict):
                if "$ref" in items:
                    ref_path = items["$ref"]
                    if ref_path.startswith("#/components/schemas/"):
                        ref_name = ref_path.split("/")[-1]
                        return [f"{indent_str}{name}{opt_str}: {ref_name}[];{comment}"]
                    elif ref_path in visited or items.get("circular"):
                        ref_name = items["$ref"].split("/")[-1]
                        return [f"{indent_str}{name}{opt_str}: Array<[Circular: {ref_name}]>;{comment}"]
                    else:
                        try:
                            new_visited = visited.copy()
                            new_visited.add(ref_path)
                            resolved = self.resolver.resolve_pointer(ref_path)
                            items = resolved
                        except:
                            pass
                            
                if isinstance(items, dict):
                    item_type = items.get("type", "any")
                    if item_type == "object":
                        lines = [indent_str + f"{name}{opt_str}: Array<{{" + comment]
                        properties = items.get("properties", {})
                        required_fields = set(items.get("required", []))
                        for prop_name, prop_data in properties.items():
                            is_req = prop_name in required_fields
                            lines.extend(self._format_property_ts(prop_name, prop_data, indent + 2, is_req, visited))
                        lines.append(indent_str + "}>;")
                        return lines
                    elif "$ref" in items and items.get("circular"):
                        ref_name = items["$ref"].split("/")[-1]
                        return [f"{indent_str}{name}{opt_str}: Array<[Circular: {ref_name}]>;{comment}"]
                    else:
                        ts_type = self._openapi_to_ts_type(item_type)
                        return [f"{indent_str}{name}{opt_str}: {ts_type}[];{comment}"]
                else:
                    return [f"{indent_str}{name}{opt_str}: any[];{comment}"]
            else:
                return [f"{indent_str}{name}{opt_str}: any[];{comment}"]
                
        else:
            ts_type = self._openapi_to_ts_type(stype)
            return [f"{indent_str}{name}{opt_str}: {ts_type};{comment}"]
