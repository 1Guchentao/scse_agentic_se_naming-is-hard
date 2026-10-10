"""Shared strict JSON shape for measured-result reviews."""

from workspace_io import decode_json

TEXT_FIELDS = ("issue", "likely_cause", "recommendation")


def shape(flags):
    return {"type": "object", "additionalProperties": False,
            "required": [*TEXT_FIELDS, *flags],
            "properties": {**{field: {"type": "string", "minLength": 1} for field in TEXT_FIELDS},
                           **{field: {"type": "boolean", "enum": [value]}
                              for field, value in flags.items()}}}


def validate_review(value, flags):
    if not isinstance(value, dict) or set(value) != set(TEXT_FIELDS) | set(flags):
        raise ValueError("Review keys do not match the required schema.")
    if any(not isinstance(value[field], str) or not value[field].strip() for field in TEXT_FIELDS):
        raise ValueError("Review explanations must be nonempty strings.")
    if any(type(value[field]) is not bool or value[field] != expected for field, expected in flags.items()):
        raise ValueError("Review flags must agree with the measured results.")
    return value


def request_review(stage, instructions, context, flags, ask, trace_folder):
    text = ask(stage, instructions, context, response_shape=shape(flags), trace_folder=trace_folder)
    return validate_review(decode_json(text), flags)
