"""Small shared helpers for the gate scripts (stdlib only).

Everything the gate prints or writes into the job summary may contain strings
chosen by the author of a pull request (file names, test ids).  Those strings
are neutralised here so they cannot start a GitHub workflow command (a line
beginning with ``::``) or inject Markdown/HTML into the summary.
"""
from __future__ import annotations

import json
import os
import re

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def safe(text: object, limit: int = 300) -> str:
    """Return ``text`` on one line, control characters escaped, length-capped."""
    s = _CONTROL.sub(lambda m: "\\x%02x" % ord(m.group()), str(text))
    return s if len(s) <= limit else s[:limit] + "..."


def md_code(text: object, limit: int = 200) -> str:
    """Render ``text`` as an inline Markdown code span that cannot be escaped."""
    return "`" + safe(text, limit).replace("`", "'") + "`"


def write_json(path: str, data: object) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")


def read_json(path: str) -> object:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
