"""
Extracts the complete enclosing function around a range of changed lines in
a JS/TS source file.

This is intentionally a heuristic, regex + brace-matching extractor rather
than a real parser (no tree-sitter/babel dependency is assumed to be
available in this environment). It is designed to fail closed: if it can't
confidently find a function whose body fully covers the changed lines, it
returns None rather than guessing or stitching together a fake function
(see spec step 20: "Do NOT manufacture a function from incomplete
fragments").

Important ordering note: extraction runs against the ORIGINAL file text
(comments intact), because line numbers from the diff/patch only line up
with the original text. Comment stripping happens AFTER extraction, on the
extracted function text only (see comment_stripper.py).
"""

import re
from typing import List, Optional, Tuple

_SIG_PATTERNS = [
    # function foo(...) / export default async function foo(...)
    re.compile(r'^\s*(export\s+)?(default\s+)?(async\s+)?function\s*\*?\s*[A-Za-z_$][\w$]*\s*\('),
    # const foo = function(...) / const foo = async function(...)
    re.compile(r'^\s*(export\s+)?(const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*(async\s+)?function\s*\*?\s*\('),
    # const foo = (args) => ... / const foo = async (args): T =>
    re.compile(r'^\s*(export\s+)?(const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*(async\s+)?\([^=]*\)\s*(:\s*[^=]+)?=>'),
    # const foo = arg => ...
    re.compile(r'^\s*(export\s+)?(const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*(async\s+)?[A-Za-z_$][\w$]*\s*=>'),
    # class/object method shorthand: name(args) { ... }  or  async name(args) {
    # (negative lookahead excludes control-flow keywords like if/for/while/
    # switch/catch/function, which have the same surface shape)
    re.compile(
        r'^\s*(public\s+|private\s+|protected\s+|static\s+|async\s+|\*\s*)*'
        r'(?!if\b|for\b|while\b|switch\b|catch\b|function\b|return\b)'
        r'[A-Za-z_$][\w$]*\s*\([^)]*\)\s*(:\s*[^{]+)?\{\s*$'
    ),
]


def _skip_string_or_comment(source: str, i: int, n: int) -> Optional[int]:
    """If position i starts a string/template/comment, returns the index
    just past it. Otherwise returns None."""
    c = source[i]
    if c == "/" and i + 1 < n and source[i + 1] == "/":
        j = source.find("\n", i)
        return j if j != -1 else n
    if c == "/" and i + 1 < n and source[i + 1] == "*":
        j = source.find("*/", i + 2)
        return (j + 2) if j != -1 else n
    if c in ("'", '"'):
        quote = c
        j = i + 1
        while j < n and source[j] != quote:
            if source[j] == "\\":
                j += 1
            j += 1
        return min(j + 1, n)
    if c == "`":
        j = i + 1
        depth = 0
        while j < n:
            cc = source[j]
            if cc == "\\":
                j += 2
                continue
            if cc == "`" and depth == 0:
                return j + 1
            if cc == "$" and j + 1 < n and source[j + 1] == "{":
                depth += 1
                j += 2
                continue
            if cc == "}" and depth > 0:
                depth -= 1
            j += 1
        return n
    return None


def _find_matching_close_paren(source: str, open_idx: int) -> Optional[int]:
    """open_idx points at a '(' - returns index of its matching ')',
    skipping over strings/comments/nested parens/braces."""
    depth = 0
    i = open_idx
    n = len(source)
    while i < n:
        skip_to = _skip_string_or_comment(source, i, n)
        if skip_to is not None:
            i = skip_to
            continue
        c = source[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _find_body_open_brace(source: str, sig_start_idx: int) -> Optional[int]:
    """Given the start of a function signature, finds the '{' that opens
    the function BODY - not a '{' that appears earlier in the signature
    itself (e.g. a destructured parameter like `({ data }) => {`, or a
    TypeScript return-type annotation). Handles both `(...) => {` arrow
    bodies and `name(...) {` / `function name(...) {` bodies by first
    skipping past the balanced parameter-list parens, then taking the
    first '{' after that (skipping any `: ReturnType` in between)."""
    n = len(source)
    paren_idx = source.find("(", sig_start_idx)
    if paren_idx == -1:
        return None
    close_paren = _find_matching_close_paren(source, paren_idx)
    if close_paren is None:
        return None
    i = close_paren + 1
    while i < n:
        skip_to = _skip_string_or_comment(source, i, n)
        if skip_to is not None:
            i = skip_to
            continue
        c = source[i]
        if c == "{":
            return i
        if c == "(":
            # e.g. a second parameter list segment / generic call - unlikely,
            # but stay safe and skip balanced parens rather than mis-triggering
            closer = _find_matching_close_paren(source, i)
            i = (closer + 1) if closer is not None else n
            continue
        if c == ";":
            # arrow function with an expression body (no block) - not usable
            return None
        i += 1
    return None


def _find_matching_close_brace(source: str, open_idx: int) -> Optional[int]:
    depth = 0
    i = open_idx
    n = len(source)
    while i < n:
        skip_to = _skip_string_or_comment(source, i, n)
        if skip_to is not None:
            i = skip_to
            continue
        c = source[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def extract_enclosing_function(
    source: str, target_start_line: int, target_end_line: int
) -> Optional[Tuple[str, int, int]]:
    """Returns (function_text, start_line, end_line) for the nearest
    function-like construct that starts at or before target_start_line and
    whose closing brace is at or after target_end_line. 1-indexed, inclusive
    line numbers. Returns None if nothing confidently matches."""
    if not source:
        return None

    lines: List[str] = source.split("\n")
    n_lines = len(lines)
    target_start_line = max(1, min(target_start_line, n_lines))
    target_end_line = max(target_start_line, min(target_end_line, n_lines))

    offsets = [0] * (n_lines + 1)
    acc = 0
    for idx, ln in enumerate(lines, start=1):
        offsets[idx] = acc
        acc += len(ln) + 1

    for sig_line in range(target_start_line, 0, -1):
        line_text = lines[sig_line - 1]
        if not any(p.search(line_text) for p in _SIG_PATTERNS):
            continue

        search_from = offsets[sig_line]
        brace_idx = _find_body_open_brace(source, search_from)
        if brace_idx is None:
            continue

        close_idx = _find_matching_close_brace(source, brace_idx)
        if close_idx is None:
            continue

        end_line = source.count("\n", 0, close_idx) + 1
        if end_line < target_end_line:
            # this candidate function ends before the changed range does -
            # not the right enclosing scope, keep looking further up
            continue

        func_text = source[offsets[sig_line]:close_idx + 1].strip()
        return func_text, sig_line, end_line

    return None
