"""Turns a model's tool call into a Python call. (Given — you don't need to change this.)"""
import inspect
import typing


def _coerce(value, annotation):
    args = typing.get_args(annotation)
    if args and type(None) in args:            # Optional[X]
        if value is None:
            return None
        annotation = next(a for a in args if a is not type(None))
    if annotation is int:
        # Models often send 12.0 or "12" for an integer.
        if isinstance(value, bool):
            raise ValueError("expected an integer")
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value)
        if isinstance(value, int):
            return value
        raise ValueError(f"expected an integer, got {value!r}")
    if annotation is str:
        if not isinstance(value, str):
            raise ValueError(f"expected a string, got {value!r}")
        return value
    return value


def dispatch(functions: dict, name: str, args: dict) -> dict:
    fn = functions.get(name)
    if fn is None:
        return {"error": "unknown_tool", "hint": f"Available tools: {', '.join(sorted(functions))}."}
    sig = inspect.signature(fn)
    hints = typing.get_type_hints(fn)
    try:
        bound = sig.bind(**(args or {}))
        kwargs = {k: _coerce(v, hints.get(k)) for k, v in bound.arguments.items()}
    except (TypeError, ValueError) as e:
        return {"error": "invalid_arguments", "hint": f"{name}: {e}. Check the parameter descriptions."}
    return fn(**kwargs)
