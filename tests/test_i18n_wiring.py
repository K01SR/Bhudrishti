"""The locale dictionary has to be wired into the UI, not merely present.

The Hindi dictionary shipped complete -- two locales, no blanks, matching
placeholder tokens -- and none of it reached a rendered string. The language
selector wrote to the context, the context merged the dictionaries, and the
merge result was never read, because no component called `useTranslation()`.
Switching to Hindi in the running app changed nothing at all.

`IngestPage` was the first page to be wired, and these tests pin that wiring so
it cannot silently regress into a dictionary nobody reads. The checks are
structural rather than rendered: `IngestPage` renders provenance banners, upload
forms and result tables whose every cell is a claim about what the platform did
or did not establish. A hardcoded English string there is a string that will
keep reading as English for a Hindi user while the locale switch appears to
work.

The same class of bug hid inside the interpolation helper. The point-cloud toast
passed `{ file, format }` to a template that only mentioned `{format}`, so the
uploaded filename was dropped from the message while the code appeared to
include it. Static key-existence checks cannot see that; these tests compare the
variables each `fill()` call passes against the placeholders its template
actually contains.
"""

import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
TRANSLATIONS = REPO / "frontend" / "src" / "i18n" / "translations.ts"
INGEST_PAGE = REPO / "frontend" / "src" / "pages" / "app" / "IngestPage.tsx"


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# --- a small parser for the object literals in translations.ts ---------------
#
# The suite runs in python:3.11-slim with no Node, so the TypeScript cannot be
# executed to inspect it. Rather than regex the whole file, this walks the
# braces and string literals properly, which keeps a brace inside a comment or
# a "//" inside a URL from corrupting the parse.


def _skip(src: str, i: int) -> int:
    """Advance past whitespace and comments."""
    while i < len(src):
        if src[i].isspace():
            i += 1
        elif src.startswith("//", i):
            nl = src.find("\n", i)
            i = len(src) if nl == -1 else nl + 1
        elif src.startswith("/*", i):
            end = src.find("*/", i + 2)
            assert end != -1, "unterminated block comment in translations.ts"
            i = end + 2
        else:
            break
    return i


def _parse_string(src: str, i: int) -> tuple[str, int]:
    quote = src[i]
    i += 1
    out = []
    while i < len(src):
        c = src[i]
        if c == "\\":
            nxt = src[i + 1]
            out.append({"n": "\n", "t": "\t", "r": "\r"}.get(nxt, nxt))
            i += 2
            continue
        if c == quote:
            return "".join(out), i + 1
        out.append(c)
        i += 1
    raise AssertionError("unterminated string literal in translations.ts")


def _parse_object(src: str, i: int) -> tuple[dict, int]:
    assert src[i] == "{", f"expected '{{' at offset {i}, found {src[i]!r}"
    i += 1
    node: dict = {}
    while True:
        i = _skip(src, i)
        if i >= len(src):
            raise AssertionError("unterminated object in translations.ts")
        if src[i] == "}":
            return node, i + 1
        if src[i] in "\"'`":
            key, i = _parse_string(src, i)
        else:
            start = i
            while i < len(src) and src[i] not in ":{},\n":
                i += 1
            key = src[start:i].strip()
            assert key, f"unparseable key at offset {start}"
        i = _skip(src, i)
        assert src[i] == ":", f"expected ':' after key {key!r}, found {src[i]!r}"
        i = _skip(src, i + 1)
        if src[i] == "{":
            node[key], i = _parse_object(src, i)
        elif src[i] in "\"'`":
            node[key], i = _parse_string(src, i)
        else:
            raise AssertionError(
                f"dictionary value for {key!r} is not a string or object; "
                "these tests only model user-facing text"
            )
        i = _skip(src, i)
        if i < len(src) and src[i] == ",":
            i = _skip(src, i + 1)


def _translations() -> dict:
    src = _read(TRANSLATIONS)
    start = src.index("export const translations")
    root, _ = _parse_object(src, src.index("{", start))
    return root


def _leaves(node: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in node.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(_leaves(value, f"{path}."))
        else:
            out[path] = value
    return out


def _placeholders(text: str) -> set[str]:
    return set(re.findall(r"\{(\w+)\}", text))


@pytest.fixture(scope="module")
def locales() -> dict[str, dict[str, str]]:
    root = _translations()
    return {code: _leaves(tree) for code, tree in root.items()}


# --- the dictionary itself --------------------------------------------------


def test_every_locale_defines_the_same_keys(locales):
    """
    A key present in one locale and absent in the other renders as `undefined`
    in whichever language is missing it -- a blank label or a literal
    "t.ingest.foo.bar" in the UI.
    """
    codes = sorted(locales)
    assert codes, "no locales parsed from translations.ts"
    reference = set(locales[codes[0]])
    for code in codes[1:]:
        assert set(locales[code]) == reference, (
            f"{code} differs from {codes[0]}: "
            f"missing={sorted(reference - set(locales[code]))} "
            f"extra={sorted(set(locales[code]) - reference)}"
        )


def test_hindi_is_never_blank(locales):
    blanks = sorted(k for k, v in locales["hi"].items() if not v.strip())
    assert not blanks, f"Hindi values are empty: {blanks}"


def test_placeholders_survive_translation(locales):
    """
    A token dropped in translation leaves the raw `{token}` on screen. A token
    invented in translation has nothing to fill it and renders as `{token}`
    too, because `fill()` leaves unknown tokens in place.
    """
    mismatched = []
    for key, english in locales["en"].items():
        hindi = locales["hi"].get(key)
        if hindi is None:
            continue
        expected, actual = _placeholders(english), _placeholders(hindi)
        if expected != actual:
            mismatched.append(f"{key}: en={sorted(expected)} hi={sorted(actual)}")
    assert not mismatched, "placeholder mismatch:\n" + "\n".join(mismatched)


# --- the page actually consumes it -----------------------------------------

# Three different bindings reach into the dictionary in this page, and they are
# rooted differently, so a flat `t.` search would resolve them against the wrong
# subtree and report noise:
#
#   ti                     = t.ingest                     (the whole ingest group)
#   t.ingest.*             = t.ingest.*                   (components taking the
#                                                         full dictionary)
#   classifyProvenance(..) = t = t.ingest                 (provenance tone labels)
#   parseGnssRows(..)      = t = t.ingest.gnss            (GNSS row validation)
#
# Each is resolved against the subtree its own signature binds it to.


def _match(src: str, i: int, opener: str, closer: str) -> int:
    """Index of the closer matching the opener at `i`."""
    depth = 0
    while i < len(src):
        if src[i] == opener:
            depth += 1
        elif src[i] == closer:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise AssertionError(f"unbalanced {opener}{closer} in {name_of(src)}")


def name_of(src: str) -> str:  # pragma: no cover - error text only
    return "IngestPage.tsx"


def _function_body(src: str, name: str) -> str:
    """
    Return the source of a top-level `function name(...) { ... }`.

    Brace matching alone is not enough here: `classifyProvenance` declares an
    inline object return type, so its first `{` after the parameter list opens a
    type annotation rather than the body. The body is the candidate whose closing
    brace ends the declaration.
    """
    start = src.index(f"function {name}(")
    after_params = _match(src, src.index("(", start), "(", ")") + 1
    i = after_params
    while True:
        i = src.index("{", i)
        end = _match(src, i, "{", "}")
        if src[end + 1 :].lstrip(" \t\r")[:1] in ("", "\n", ";"):
            return src[start : end + 1]
        i = end + 1


def _refs(scope: str, prefix: str, pattern: str) -> set[str]:
    return {prefix + m for m in re.findall(pattern, scope)}


def _without_scoped_functions(page: str, names: tuple[str, ...]) -> str:
    """
    Blank out the helpers that rebind `t`, so the page-level scope does not also
    read their `t.errorX` references against the wrong subtree. `parseGnssRows`
    takes the gnss group, so its `t.errorOutsideIndia` would otherwise resolve
    as `ingest.errorOutsideIndia` and look undefined.
    """
    out = page
    for name in names:
        start = out.index(f"function {name}(")
        end = _match(out, start + len(f"function {name}(") - 1, "{", "}")
        out = out[:start] + " " * (end - start + 1) + out[end + 1 :]
    return out


def _page_bindings() -> list[tuple[str, str, str]]:
    """(scope source, dictionary prefix, dotted-path regex) per binding."""
    page = _read(INGEST_PAGE)
    helpers = ("classifyProvenance", "parseGnssRows")
    outside = _without_scoped_functions(page, helpers)
    return [
        (outside, "ingest.", r"\bti\.([A-Za-z0-9_.]+)"),
        (outside, "ingest.", r"\bt\.ingest\.([A-Za-z0-9_.]+)"),
        (_function_body(page, "classifyProvenance"), "ingest.", r"\bt\.([A-Za-z0-9_.]+)"),
        (_function_body(page, "parseGnssRows"), "ingest.gnss.", r"\bt\.([A-Za-z0-9_.]+)"),
    ]


def _referenced_keys() -> set[str]:
    refs: set[str] = set()
    for scope, prefix, pattern in _page_bindings():
        refs |= _refs(scope, prefix, pattern)
    return refs


def test_ingest_page_reads_the_locale_dictionary():
    """
    The regression this file exists for: a complete dictionary that no component
    reads. If the hook call goes away the selector keeps working, the
    dictionaries keep matching, and nothing renders differently -- which is
    exactly the state this page was in.

    Asserting only that the identifier appears somewhere is not enough. The
    import statement and the type annotation both mention `useTranslation` and
    `TranslationDictionary`, so both survive the call being replaced with a
    local `{}` and the page renders `undefined` while this test still passes.
    The call itself is what has to be present.
    """
    page = _read(INGEST_PAGE)
    calls = re.findall(r"const\s*\{\s*t[^}]*\}\s*=\s*useTranslation\(\)", page)
    assert calls, (
        "IngestPage no longer calls useTranslation(); the locale selector "
        "would work and the page would still render in English"
    )
    assert "TranslationDictionary" in page, "the ingest keys are no longer type-checked"
    # The hook must be reached from the real context, not stubbed locally.
    assert not re.search(r"=\s*\{\s*\}\s*(?:as\s+any)?\s*;", page), (
        "IngestPage stubs the dictionary instead of reading it"
    )


def test_every_ingest_key_the_page_uses_exists(locales):
    """
    Resolves the dotted paths against the subtree each binding is rooted at. A
    typo in a key renders as empty at runtime with `tsc` staying quiet, because
    the dictionary is reached through a nested object type rather than indexed.
    """
    missing = []
    for ref in sorted(_referenced_keys()):
        if ref in locales["en"]:
            continue  # a whole subtree passed as a parameter, e.g. ti.gnss
        if not any(k.startswith(ref + ".") for k in locales["en"]):
            missing.append(ref)
    assert not missing, f"IngestPage references undefined ingest keys: {missing}"


def test_ingest_page_leaves_no_dictionary_key_unused(locales):
    """
    Keys nobody renders are not translations, they are decoration, and they make
    the dictionary look more covered than the UI actually is.
    """
    refs = _referenced_keys()
    unused = [
        key for key in sorted(locales["en"])
        if key.startswith("ingest.")
        and key not in refs
        and not any(r.startswith(key + ".") for r in refs)
    ]
    assert not unused, f"ingest keys defined but never rendered: {unused}"


def test_interpolation_variables_match_their_templates(locales):
    """
    The point-cloud toast passed `{ file, format }` to a template mentioning only
    `{format}`. The upload succeeded and the confirmation named its format but
    not its file, which reads as a fault in the upload path rather than a token
    the translator forgot.
    """
    problems = []
    checked = 0
    for scope, prefix, _ in _page_bindings():
        for path, args in re.findall(
            r"fill\(\s*(?:ti|t)\.([A-Za-z0-9_.]+)\s*,\s*\{([^}]*)\}", scope
        ):
            if "..." in args:
                continue  # spread of a wider context object
            key = prefix + path
            template = locales["en"].get(key)
            if template is None:
                problems.append(f"{key}: no such template")
                continue
            checked += 1
            passed = {m.group(1) for m in re.finditer(r"([A-Za-z_]\w*)\s*:", args)}
            used = _placeholders(template)
            if passed - used:
                problems.append(f"{key}: passed {sorted(passed - used)}, template has {used}")
            if used - passed:
                problems.append(f"{key}: template wants {sorted(used - passed)}, not passed")
    assert checked, "no interpolated template found; the fill() audit is not running"
    assert not problems, "\n".join(problems)


# --- no English left behind in the rendered page ---------------------------

# Placeholders that show the *shape* of an expected value stay in Latin script on
# purpose: a coordinate or a sample slug is not UI chrome to be translated.
_FORMAT_EXAMPLE = re.compile(r"^(e\.g\.|\d|[a-z0-9]+(?:-[a-z0-9]+)+$)")


def _is_prose(value: str) -> bool:
    """Two or more words, in Latin script, on one line, and not a payload."""
    if '"' in value or "'" in value or "\\n" in value:
        return False  # a JSON sample, not something a reader sees
    if " " not in value:
        return False
    return len(re.findall(r"\b[A-Za-z]{2,}\b", value)) >= 2


# A Tailwind class list is all-lowercase tokens punctuated the way the utility
# syntax is (`text-xs`, `file:mr-3`, `w-1/2`, `text-[10px]`). Sentence case and
# commas do not survive that test, which separates styling from something a
# reader sees. The class lists wrap across lines, so a same-line `className`
# check cannot stand in for this.
_CLASS_TOKEN = re.compile(r"^[a-z0-9:/.[\]%_-]+$")


def _looks_like_class_list(value: str) -> bool:
    tokens = value.split()
    return bool(tokens) and all(_CLASS_TOKEN.match(t) for t in tokens)


# Anything that reads as code rather than as copy. Parentheses are deliberately
# absent: "Point cloud file (max 100 MB)" is interface text, and dropping it on
# the grounds that it contains brackets is how a leak survives.
_CODE_CHARS = re.compile(r"[;={}\[\]]|=>|//|/\*|\b(?:const|let|function|import|export|return|if|for|while|new|await|async|type|interface)\b")


def _children_text(page: str) -> list[str]:
    """Text sitting between a `>` and a `<`, across line breaks."""
    found = []
    for match in re.finditer(r">([^<>]*)<", page, re.S):
        text = match.group(1).strip()
        if not text or len(text) > 200 or _CODE_CHARS.search(text):
            continue
        if " " not in text or len(re.findall(r"\b[A-Za-z]{2,}\b", text)) < 2:
            continue
        if not re.search(r"\b[A-Z][a-z]{2,}\b", text):
            continue
        found.append(text)
    return found


def test_ingest_page_has_no_hardcoded_interface_strings():
    """
    A rendered string can reach the page in four shapes, and each one was a way
    to leave English in a page whose locale switch appears to work:

      <span>Text</span>                      JSX children
      <MetaCell label="Text" />              attribute
      {'Text'}                               expression container
      {condition ? 'Text' : other}           ternary branch

    All four are checked. The expression and ternary forms are what let a label
    survive a review that only looked at markup.
    """
    page = _read(INGEST_PAGE)
    offenders = []

    # 1. JSX children, including text that wraps onto its own line -- which is
    #    how every label in this file is actually written.
    for text in _children_text(page):
        offenders.append(("jsx children", text))

    # 2. label / title / placeholder attributes.
    for match in re.finditer(r'\b(label|title|placeholder)=(?:"([^"]*)"|\'([^\']*)\')', page):
        value = match.group(2) or match.group(3) or ""
        if not re.search(r"[A-Za-z]{3,}", value) or " " not in value:
            continue
        if _FORMAT_EXAMPLE.match(value):
            continue
        offenders.append((match.group(1), value))

    # 3. a whole expression container holding one string literal.
    for match in re.finditer(r"\{(['\"])((?:(?!\1).)*)\1\}", page):
        value = match.group(2)
        if _is_prose(value) and not _FORMAT_EXAMPLE.match(value):
            offenders.append(("expression", value))

    # 4. a string literal used for text rather than for styling. Every literal in
    #    the file is examined, so the filter has to separate a Tailwind class
    #    list from a sentence rather than assume where each one sits.
    for match in re.finditer(r"'((?:[^'\\\n]|\\.)*)'", page):
        value = match.group(1)
        if not _is_prose(value) or _looks_like_class_list(value):
            continue
        if _FORMAT_EXAMPLE.match(value):
            continue
        offenders.append(("string literal", value))

    assert not offenders, f"untranslated strings left in IngestPage: {offenders}"
