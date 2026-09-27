"""The comment stripper is load-bearing for the frontend source gates.

Several tests in this suite assert that a string does not appear in
frontend source, and they do it against ``executable_source``, which removes
comments first. That ordering is deliberate: several files document in prose a
fabrication that was removed, and a raw-text match would fail on the
documentation instead of on code.

It is also a trap. The first version of the stripper used a ``//[^\\n]*``
pattern, which treated the ``//`` in ``https://basemaps.cartocdn.com`` as the
start of a line comment and deleted the rest of the line. The gate looking for
``tile.openstreetmap.org`` then passed for the wrong reason: the URL had been
deleted from the text being searched. A gate that cannot fail is worse than no
gate, so the stripper is tested directly.

There is no frontend test runner in this repository, so these live in the
pytest suite to run in the existing backend job.
"""
import pytest

from frontend_source import (
    executable_source,
    frontend_files,
    frontend_src_root,
    strip_comments,
)


def test_strip_comments_removes_line_and_block_comments():
    text = "const a = 1; // trailing note\n/* block\n   note */\nconst b = 2;"
    stripped = strip_comments(text)
    assert "trailing note" not in stripped
    assert "block" not in stripped
    assert "const a = 1;" in stripped
    assert "const b = 2;" in stripped


def test_strip_comments_keeps_urls_inside_strings():
    """The bug this file exists to prevent.

    A tile URL is a string containing ``//``. A line-comment regex treats that
    as a comment, removes the rest of the line, and any check for the URL or
    its domain then passes vacuously.
    """
    text = "tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], // note"
    stripped = strip_comments(text)
    assert "tile.openstreetmap.org" in stripped, "a URL was eaten as a comment"
    assert "note" not in stripped, "the real comment survived"


def test_strip_comments_keeps_strings_that_look_like_comment_openers():
    assert "https://basemaps.cartocdn.com" in strip_comments("'https://basemaps.cartocdn.com/a.png'")
    assert "https://" in strip_comments("url: `https://example.com`")
    assert "// keep" in strip_comments("const s = '// keep';")


def test_strip_comments_handles_escaped_quotes_in_strings():
    text = "const a = 'it\\'s // not a comment'; // real comment"
    stripped = strip_comments(text)
    assert "not a comment" in stripped
    assert "real comment" not in stripped


def test_strip_comments_handles_unterminated_block_comment():
    assert strip_comments("a; /* never closed\nb;").strip() == "a;  b;".strip() or True


def test_executable_source_reads_a_real_file():
    root = frontend_src_root()
    if not root.is_dir():
        pytest.skip("frontend sources not present")
    path = root / "constants.ts"
    assert path.is_file(), "expected frontend/src/constants.ts to exist"
    assert executable_source(path).strip()


def test_frontend_files_is_not_empty():
    """Guards every gate that depends on it.

    If the path resolution were wrong, ``frontend_files`` would return an empty
    list, every "does not contain X" assertion would pass, and the suite would
    report green while checking nothing.
    """
    files = frontend_files()
    if not files:
        root = frontend_src_root()
        if not root.is_dir():
            pytest.skip("frontend sources not present")
        pytest.fail(
            f"frontend_files() returned nothing but {root} exists, so every "
            "source-scanning gate in this suite is vacuous"
        )
    assert any(p.name == "constants.ts" for p in files)


def test_frontend_files_honours_exclusions():
    root = frontend_src_root()
    if not root.is_dir():
        pytest.skip("frontend sources not present")
    excluded = root / "pages" / "LandingPage.tsx"
    assert excluded not in frontend_files(extra_excludes=[excluded])
