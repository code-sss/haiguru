"""Text normalization utilities for answer comparison."""

import re


def normalize_option_text(option: str | None) -> str:
    """Strip, lowercase, and collapse internal whitespace."""
    if not option:
        return ""
    return re.sub(r"\s+", " ", option.strip().lower())


def normalize_option_list(options: list[str] | None) -> list[str]:
    """Normalize a list of option strings."""
    if not options:
        return []
    return [normalize_option_text(o) for o in options]


def options_match(selected: list[str], correct: list[str]) -> bool:
    """Compare two option lists ignoring order and case."""
    return set(normalize_option_list(selected)) == set(normalize_option_list(correct))
