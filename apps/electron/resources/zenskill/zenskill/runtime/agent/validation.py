"""工具参数 JSON Schema 校验（最小实现，零依赖）。

支持子集：type（string/integer/number/boolean/array/object）、required、
enum、items、properties。带宽松类型转换（字符串化的 JSON、数字字符串、
布尔字符串），对齐 pi 的 AJV coerce 语义。
"""
from __future__ import annotations

import json
from typing import Any, Dict


class ToolValidationError(Exception):
    pass


_TYPE_NAMES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _coerce_type(value: Any, expected: str, path: str) -> Any:
    if expected == "string":
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float, bool)):
            return json.dumps(value) if isinstance(value, (dict, list)) else str(value).lower() if isinstance(value, bool) else str(value)
        raise ToolValidationError(f"{path}: expected string, got {type(value).__name__}")

    if expected == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            if value.lower() in ("true", "yes", "1"):
                return True
            if value.lower() in ("false", "no", "0"):
                return False
        if isinstance(value, (int, float)) and value in (0, 1):
            return bool(value)
        raise ToolValidationError(f"{path}: expected boolean, got {value!r}")

    if expected in ("integer", "number"):
        if isinstance(value, bool):
            raise ToolValidationError(f"{path}: expected {expected}, got bool")
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value) if expected == "integer" else value
        if isinstance(value, str):
            try:
                parsed = float(value)
            except ValueError:
                raise ToolValidationError(f"{path}: expected {expected}, got {value!r}")
            return int(parsed) if expected == "integer" else parsed
        raise ToolValidationError(f"{path}: expected {expected}, got {type(value).__name__}")

    if expected == "array":
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (ValueError, SyntaxError):
                raise ToolValidationError(f"{path}: expected array, got non-JSON string")
            if isinstance(parsed, list):
                return parsed
        raise ToolValidationError(f"{path}: expected array, got {type(value).__name__}")

    if expected == "object":
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (ValueError, SyntaxError):
                raise ToolValidationError(f"{path}: expected object, got non-JSON string")
            if isinstance(parsed, dict):
                return parsed
        raise ToolValidationError(f"{path}: expected object, got {type(value).__name__}")

    return value


def _validate(value: Any, schema: Dict[str, Any], path: str) -> Any:
    if not isinstance(schema, dict):
        return value

    if "enum" in schema and value not in schema["enum"]:
        raise ToolValidationError(f"{path}: {value!r} not in enum {schema['enum']!r}")

    expected = schema.get("type")
    if expected is not None:
        value = _coerce_type(value, expected, path)

    if isinstance(value, dict):
        properties = schema.get("properties")
        required = schema.get("required", [])
        if properties or required:
            for key in required:
                if key not in value:
                    raise ToolValidationError(f"{path}: missing required property '{key}'")
            if properties:
                for key, sub_schema in properties.items():
                    if key in value:
                        value[key] = _validate(value[key], sub_schema, f"{path}.{key}")

    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        value = [
            _validate(item, schema["items"], f"{path}[{i}]")
            for i, item in enumerate(value)
        ]

    return value


def validate_tool_arguments(schema: Dict[str, Any], args: Any) -> Dict[str, Any]:
    """校验并转换工具参数。args 必须是（或可解析为）object。"""
    if args is None:
        args = {}
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (ValueError, SyntaxError):
            raise ToolValidationError(f"arguments is not valid JSON: {args[:120]!r}")
    if not isinstance(args, dict):
        raise ToolValidationError(f"arguments must be an object, got {type(args).__name__}")

    top_required = schema.get("required", [])
    for key in top_required:
        if key not in args:
            raise ToolValidationError(f"missing required argument '{key}'")

    return _validate(args, schema, "arguments")
