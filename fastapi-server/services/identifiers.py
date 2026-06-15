"""Shared identifier extraction helpers.

A single source of truth for the DOORS/ABS requirement-id pattern that was
previously duplicated across several server routes (and the archived migration
script).
"""
import re

DOORS_PATTERN = re.compile(r"@?(?:DOORS-\d+|ABS-\d+)", re.IGNORECASE)


def extract_doors_id(tag: str) -> str | None:
    """Return the DOORS/ABS identifier found in ``tag`` (without a leading ``@``).

    Returns ``None`` when the tag contains no requirement identifier.
    """
    match = DOORS_PATTERN.search(tag)
    return match.group(0).lstrip("@") if match else None
