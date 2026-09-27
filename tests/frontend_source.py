"""Helpers for asserting on frontend source from the pytest suite.

There is no frontend test runner in this repository, so the frontend gates are
pytest tests that read source files. That is a deliberate trade: the checks are
coarse (no rendering, no types) but they run in the existing backend job, so
they cannot be skipped by only running the frontend suite.

Comments are stripped before matching. Several files document, in prose, a
fabrication that was removed, and that history is worth keeping. A gate that
matched raw text would either fail on the documentation or force it to be
deleted; neither is a useful outcome.
"""
from __future__ import annotations

import pathlib
from typing import Iterable

SRC_SUFFIXES = {".ts", ".tsx", ".js", ".jsx"}


def frontend_src_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1] / "frontend" / "src"


def strip_comments(text: str) -> str:
    """Remove // and /* */ comments without touching string contents.

    A regex is not enough here. Every tile URL contains ``//``, so a naive
    line-comment pattern swallows the rest of the line, and a gate checking for
    ``tile.openstreetmap.org`` then passes vacuously because the URL it was
    meant to catch has been deleted from the text it is searching. That is the
    worst possible failure for a check like this one, so this walks the source
    and tracks string state instead.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    quote: str | None = None

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if quote is not None:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue

        # A quote only opens a string where one is legal to open. The set is
        # deliberately small: JSX text and regex literals are not handled, and
        # neither appears in the files these gates read.
        if ch in "'\"`":
            quote = ch
            out.append(ch)
            i += 1
            continue

        if ch == "/" and nxt == "*":
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            out.append(" ")
            continue

        if ch == "/" and nxt == "/":
            end = text.find("\n", i)
            i = n if end == -1 else end
            out.append(" ")
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def executable_source(path: pathlib.Path) -> str:
    return strip_comments(path.read_text())


def frontend_files(extra_excludes: Iterable[pathlib.Path] = ()) -> list[pathlib.Path]:
    """Every frontend source file, minus paths and directories to exclude."""
    root = frontend_src_root()
    if not root.is_dir():
        return []
    excluded = [pathlib.Path(e) for e in extra_excludes]
    out = []
    for path in root.rglob("*"):
        if path.suffix not in SRC_SUFFIXES:
            continue
        if any(path == e or e in path.parents for e in excluded):
            continue
        out.append(path)
    return out
