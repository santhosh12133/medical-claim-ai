"""Robust extraction of a JSON object from model output."""

from __future__ import annotations

import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class StructuredOutputError(ValueError):
    """Raised when model output does not contain a JSON object."""


def extract_json_object(text: str) -> dict:
    """Parse the first JSON object in ``text``.

    Handles plain JSON, Markdown code fences and leading/trailing prose,
    which models emit even when asked for "JSON only".
    """
    if not text or not text.strip():
        raise StructuredOutputError("Empty model output")
    candidates = [text.strip()]
    candidates.extend(match.strip() for match in _FENCE.findall(text))
    start = text.find("{")
    if start != -1:
        candidates.append(_balanced_object(text, start))
    for candidate in candidates:
        if not candidate:
            continue
        try:
            value = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(value, dict):
            return value
    raise StructuredOutputError("Model output did not contain a JSON object")


def _balanced_object(text: str, start: int) -> str:
    depth = 0
    in_string = False
    escaped = False
    for position in range(start, len(text)):
        character = text[position]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return text[start:position + 1]
    return ""
