import json
import os
import re
from typing import Any, Dict

DEFAULT_REGISTRY_DIR = "specs/registry"

def get_registry_path(spec_id: str, tag: str, registry_dir: str = DEFAULT_REGISTRY_DIR) -> str:
    """Returns the path for a given spec_id and tag in the registry."""
    # Ensure spec_id and tag are safe for path traversal
    safe_spec_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', spec_id)
    safe_tag = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', tag)
    return os.path.join(registry_dir, safe_spec_id, f"{safe_tag}.json")

def register_spec(input_path: str, spec_id: str, tag: str, registry_dir: str = DEFAULT_REGISTRY_DIR) -> str:
    """Registers a specification in the local registry."""
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file '{input_path}' not found.")

    with open(input_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON syntax: {e}")

    dest_path = get_registry_path(spec_id, tag, registry_dir)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    with open(dest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return dest_path

def get_spec(spec_id: str, tag: str, registry_dir: str = DEFAULT_REGISTRY_DIR) -> Dict[str, Any]:
    """Retrieves a registered specification from the registry."""
    path = get_registry_path(spec_id, tag, registry_dir)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Spec '{spec_id}' with tag '{tag}' not found in registry at '{path}'.")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def resolve_registry_uri(uri: str, registry_dir: str = DEFAULT_REGISTRY_DIR) -> Dict[str, Any]:
    """
    Resolves registry://<spec_id>:<tag> URI and returns the spec dict.
    Example: registry://petstore:v1.0.0
    """
    if not uri.startswith("registry://"):
        raise ValueError(f"Invalid registry URI: must start with 'registry://'. Got '{uri}'")

    pattern = uri[len("registry://"):]
    if ":" not in pattern:
        raise ValueError(f"Invalid registry URI format: must be 'registry://<spec_id>:<tag>'. Got '{uri}'")

    spec_id, tag = pattern.split(":", 1)
    if not spec_id or not tag:
        raise ValueError(f"Invalid registry URI content: spec_id and tag must be non-empty. Got '{uri}'")

    return get_spec(spec_id, tag, registry_dir)
