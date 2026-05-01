"""camelCase ↔ snake_case conversion utilities.

Used by CaseConversionMiddleware to translate between the frontend naming
convention (camelCase) and the backend convention (snake_case).
"""
import re


def to_snake_case(key: str) -> str:
    """'displayName' → 'display_name', 'photoURL' → 'photo_url'"""
    key = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", key)
    key = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", key)
    return key.lower()


def to_camel_case(key: str) -> str:
    """'display_name' → 'displayName', 'id_token' → 'idToken'"""
    parts = key.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def keys_to_snake(obj: object) -> object:
    if isinstance(obj, dict):
        return {to_snake_case(k): keys_to_snake(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [keys_to_snake(item) for item in obj]
    return obj


def keys_to_camel(obj: object) -> object:
    if isinstance(obj, dict):
        return {to_camel_case(k): keys_to_camel(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [keys_to_camel(item) for item in obj]
    return obj
