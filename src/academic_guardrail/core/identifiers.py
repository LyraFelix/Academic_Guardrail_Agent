"""DOI extraction shared by bibliography and local-paper readers."""

import re

DOI_REGEX = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")


def clean_doi(value: str) -> str:
    """Remove sentence punctuation and unmatched closing parentheses only."""
    value = value.rstrip(".,;:!?")
    while value.endswith(")") and value.count(")") > value.count("("):
        value = value[:-1].rstrip(".,;:!?")
    return value


def extract_doi(text: str):
    match = DOI_REGEX.search(text)
    return clean_doi(match.group()) if match else None
