"""
Conservative JS/TS comment stripper.

This is used on COMPLETE extracted functions right before they're sent to
Gemini (see spec step 3: "Remove comments before sending to Gemini"). It is
a character-scanning state machine, not a naive regex, so that:

  - // and /* */ inside string literals are left untouched
  - // and /* */ inside template literals (including `${ ... }` expressions)
    are left untouched
  - // and /* */ inside regex literals are left untouched (best-effort -
    regex vs. division disambiguation is a classic JS lexing problem; we use
    the standard heuristic of looking at the previous significant token)

It deliberately does NOT try to be a full JS/TS parser. On pathological
input it can misjudge a `/` as division vs. regex-start, but it will never
corrupt a string or template literal, which is the primary risk called out
in the spec ("must not corrupt JavaScript/TypeScript syntax").
"""

_REGEX_PRECEDING_PUNCT = set("([{,;:=&|!?+-*%^~<>")
_REGEX_PRECEDING_KEYWORDS = {
    "return", "typeof", "instanceof", "case", "in", "of", "new",
    "delete", "void", "throw", "do", "else", "yield", "await",
}


def strip_js_comments(source: str) -> str:
    if not source:
        return source

    out: list = []
    i = 0
    n = len(source)

    def prev_token_allows_regex() -> bool:
        # Walk backward over already-emitted output, skipping whitespace,
        # to see whether a '/' here is more likely to start a regex literal
        # (after an operator/punctuation/keyword) or division (after an
        # identifier, number, ')' or ']').
        k = len(out) - 1
        while k >= 0 and out[k].isspace():
            k -= 1
        if k < 0:
            return True  # start of file
        ch = out[k]
        if ch in _REGEX_PRECEDING_PUNCT:
            return True
        if ch in (")", "]"):
            return False
        if ch.isalnum() or ch in ("_", "$"):
            word_chars = []
            j = k
            while j >= 0 and (out[j].isalnum() or out[j] in ("_", "$")):
                word_chars.append(out[j])
                j -= 1
            word = "".join(reversed(word_chars))
            return word in _REGEX_PRECEDING_KEYWORDS
        return True

    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""

        # line comment
        if ch == "/" and nxt == "/":
            j = source.find("\n", i)
            i = j if j != -1 else n
            continue

        # block comment (including /** ... */ doc comments)
        if ch == "/" and nxt == "*":
            j = source.find("*/", i + 2)
            i = (j + 2) if j != -1 else n
            continue

        # single/double-quoted strings
        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            i += 1
            while i < n:
                c = source[i]
                if c == "\\" and i + 1 < n:
                    out.append(c)
                    out.append(source[i + 1])
                    i += 2
                    continue
                out.append(c)
                i += 1
                if c == quote:
                    break
            continue

        # template literals, tracking `${ }` expression nesting so that
        # braces/comments *inside* an interpolation are still handled, while
        # braces that are literal template text are left completely alone
        if ch == "`":
            out.append(ch)
            i += 1
            depth = 0
            while i < n:
                c = source[i]
                nc = source[i + 1] if i + 1 < n else ""

                if depth > 0:
                    # inside a `${ ... }` interpolation: this is ordinary JS
                    # expression code, so comments/strings/nested templates
                    # here get the same treatment as top-level code.
                    if c == "/" and nc == "/":
                        j = source.find("\n", i)
                        i = j if j != -1 else n
                        continue
                    if c == "/" and nc == "*":
                        j = source.find("*/", i + 2)
                        i = (j + 2) if j != -1 else n
                        continue
                    if c in ("'", '"'):
                        quote = c
                        out.append(c)
                        i += 1
                        while i < n:
                            out.append(source[i])
                            if source[i] == "\\" and i + 1 < n:
                                out.append(source[i + 1])
                                i += 2
                                continue
                            if source[i] == quote:
                                i += 1
                                break
                            i += 1
                        continue

                if c == "\\" and i + 1 < n:
                    out.append(c)
                    out.append(source[i + 1])
                    i += 2
                    continue
                if c == "`" and depth == 0:
                    out.append(c)
                    i += 1
                    break
                if c == "$" and nc == "{":
                    out.append("${")
                    i += 2
                    depth += 1
                    continue
                if c == "{" and depth > 0:
                    depth += 1
                    out.append(c)
                    i += 1
                    continue
                if c == "}" and depth > 0:
                    depth -= 1
                    out.append(c)
                    i += 1
                    continue
                out.append(c)
                i += 1
            continue

        # regex literal (best-effort heuristic)
        if ch == "/" and prev_token_allows_regex():
            j = i + 1
            in_class = False
            valid = True
            while j < n:
                c = source[j]
                if c == "\\":
                    j += 2
                    continue
                if c == "[":
                    in_class = True
                elif c == "]":
                    in_class = False
                elif c == "/" and not in_class:
                    j += 1
                    break
                elif c == "\n":
                    valid = False
                    break
                j += 1
            if valid:
                k = j
                while k < n and source[k].isalpha():
                    k += 1
                out.append(source[i:k])
                i = k
                continue
            # fell through: not a valid regex on this line, treat '/' normally

        out.append(ch)
        i += 1

    cleaned = "".join(out)
    # collapse runs of 3+ blank lines left behind by removed block comments
    lines = cleaned.split("\n")
    result_lines = []
    blank_run = 0
    for line in lines:
        if line.strip() == "":
            blank_run += 1
            if blank_run > 2:
                continue
        else:
            blank_run = 0
        result_lines.append(line)
    return "\n".join(result_lines).strip()
