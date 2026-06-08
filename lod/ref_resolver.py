from typing import Any, Dict, Set


class RefResolver:
    """
    A high-efficiency JSON Reference ($ref) resolver with support for local
    JSON Pointers, caching, and cycle detection.
    """
    def __init__(self, document: Dict[str, Any]):
        self.document = document
        self.cache: Dict[str, Any] = {}

    def resolve_pointer(self, ref_path: str) -> Any:
        """
        Resolves a local JSON pointer (e.g. '#/components/schemas/UserModel').
        Supports RFC 6901 decoding (~1 -> /, ~0 -> ~).
        """
        if ref_path in self.cache:
            return self.cache[ref_path]

        if not ref_path.startswith("#"):
            # If it doesn't start with '#', we only support local refs in this spec
            return None

        if ref_path == "#" or ref_path == "#/":
            return self.document

        parts = ref_path.lstrip("#/").split("/")
        current = self.document

        for part in parts:
            if not part:
                continue
            # Decode JSON pointer characters
            part = part.replace("~1", "/").replace("~0", "~")

            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list) and part.isdigit():
                idx = int(part)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    raise KeyError(f"Index {idx} out of range in pointer {ref_path}")
            else:
                raise KeyError(f"Key/Index '{part}' not found in pointer {ref_path}")

        self.cache[ref_path] = current
        return current

    def resolve_refs_fully(self, obj: Any, visited_refs: Set[str] = None) -> Any:
        """
        Recursively resolves all references in a nested structure.
        Uses a visited set to detect cycles. If a cycle is detected,
        the reference is kept as {"$ref": ref_path, "circular": True} to prevent infinite loops.
        """
        if visited_refs is None:
            visited_refs = set()

        if isinstance(obj, dict):
            if "$ref" in obj:
                ref_path = obj["$ref"]
                if ref_path in visited_refs:
                    # Return circular indicator
                    return {"$ref": ref_path, "circular": True}

                try:
                    resolved = self.resolve_pointer(ref_path)

                    # Track this reference to detect circular paths down the line
                    new_visited = visited_refs.copy()
                    new_visited.add(ref_path)

                    # Recursively resolve the resolved value
                    return self.resolve_refs_fully(resolved, new_visited)
                except Exception as e:
                    # Fallback if pointer resolution fails
                    return {"$ref": ref_path, "error": str(e)}

            # Standard dictionary: resolve all items
            return {k: self.resolve_refs_fully(v, visited_refs) for k, v in obj.items()}

        elif isinstance(obj, list):
            # Resolve all elements in list
            return [self.resolve_refs_fully(item, visited_refs) for item in obj]

        return obj
