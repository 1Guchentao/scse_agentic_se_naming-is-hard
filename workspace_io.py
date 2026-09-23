"""Portable artifact paths and complete-file replacement."""

import json
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parent


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Repeated JSON field: {key}")
        value[key] = item
    return value


def _invalid_number(value):
    raise ValueError(f"Invalid JSON constant: {value}")


def decode_json(text):
    return json.loads(text, object_pairs_hook=_object, parse_constant=_invalid_number)


def read_json(path):
    return decode_json(Path(path).read_text(encoding="utf-8-sig"))


def save_text(path, text):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=destination.parent,
            prefix=destination.name + ".", suffix=".part", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        temporary.replace(destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_json(path, data):
    save_text(path, json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
