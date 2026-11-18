"""Publish complete UTF-8 files. Immutable records use an exclusive destination name."""

from contextlib import contextmanager
import os
from pathlib import Path
import tempfile


@contextmanager
def atomic_text_file(destination: Path, *, overwrite: bool = False):
    # Readers looking for *.review.json (or HTML) only see the name after close succeeds.
    fd, temporary = tempfile.mkstemp(dir=destination.parent, prefix=".guardrail-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            yield handle
        if overwrite:
            os.replace(temporary, destination)
        elif os.name == "nt":
            os.rename(temporary, destination)  # Windows rename fails if the name already exists.
        else:
            os.link(temporary, destination)  # Atomic no-replace publication on POSIX.
    finally:
        Path(temporary).unlink(missing_ok=True)
