#!/usr/bin/env python3
"""
A small, careful Dart lexer good enough to locate string literals with exact
source offsets, plus enough surrounding tokens to understand their context.

We only need three things from the source:
  * where every string literal starts and ends (to splice text)
  * the decoded value of that literal (to use as a translation key)
  * whether the literal interpolates ($x / ${...}), which makes it a template

Comments are skipped. Raw strings (r'...'), triple-quoted strings ('''...''')
and all four quote/verbosity combinations are handled.

Nothing here tries to be a full Dart parser. It is deliberately conservative:
when in doubt it reports a token as "unknown" rather than guessing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Tok:
    kind: str          # 'str' | 'id' | 'num' | 'op'
    start: int
    end: int
    value: str         # for 'str' the *decoded* value; for others the raw text
    # string-only extras
    raw: bool = False
    triple: bool = False
    interpolated: bool = False
    interp_spans: tuple = ()   # ((start,end), ...) absolute offsets of $... parts
    interp_texts: tuple = ()   # the verbatim source of each interpolation


_ID_START = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_$")
_ID_CONT = _ID_START | set("0123456789")
_DIGITS = set("0123456789")


def _is_id_start(c: str) -> bool:
    return c in _ID_START or ord(c) > 127


def _is_id_cont(c: str) -> bool:
    return c in _ID_CONT or ord(c) > 127


def lex(src: str) -> list[Tok]:
    """Return a flat token list. Whitespace and comments are dropped."""
    toks: list[Tok] = []
    i = 0
    n = len(src)

    while i < n:
        c = src[i]

        # ---- whitespace -------------------------------------------------
        if c in " \t\r\n\f\v":
            i += 1
            continue

        # ---- comments ---------------------------------------------------
        if c == "/" and i + 1 < n:
            nxt = src[i + 1]
            if nxt == "/":
                j = src.find("\n", i)
                i = n if j < 0 else j + 1
                continue
            if nxt == "*":
                # Dart block comments nest
                depth = 1
                i += 2
                while i < n and depth:
                    if src.startswith("/*", i):
                        depth += 1
                        i += 2
                    elif src.startswith("*/", i):
                        depth -= 1
                        i += 2
                    else:
                        i += 1
                continue

        # ---- strings ----------------------------------------------------
        raw = False
        if c == "r" and i + 1 < n and src[i + 1] in "'\"":
            # only a raw string if the r is not part of a larger identifier
            if not toks or toks[-1].end != i or not _is_id_cont(toks[-1].value[-1:] or " "):
                if not (i > 0 and _is_id_cont(src[i - 1])):
                    raw = True
                    i += 1
                    c = src[i]

        if c in "'\"":
            tok, i = _read_string(src, i, raw)
            toks.append(tok)
            continue

        # ---- identifiers ------------------------------------------------
        if _is_id_start(c):
            j = i + 1
            while j < n and _is_id_cont(src[j]):
                j += 1
            toks.append(Tok("id", i, j, src[i:j]))
            i = j
            continue

        # ---- numbers ----------------------------------------------------
        if c in _DIGITS:
            j = i + 1
            while j < n and (src[j] in _DIGITS or src[j] in ".xXabcdefABCDEF_"):
                j += 1
            toks.append(Tok("num", i, j, src[i:j]))
            i = j
            continue

        # ---- operators / punctuation ------------------------------------
        # multi-char operators we care about (to keep context detection sane)
        three = src[i:i + 3]
        two = src[i:i + 2]
        if three in ("...", "?.", "??="):
            toks.append(Tok("op", i, i + 3, three))
            i += 3
            continue
        if two in ("=>", "==", "!=", "<=", ">=", "&&", "||", "??", "?.",
                   "..", "+=", "-=", "*=", "/=", "::", "?.", "<<" , ">>"):
            toks.append(Tok("op", i, i + 2, two))
            i += 2
            continue
        toks.append(Tok("op", i, i + 1, c))
        i += 1

    return toks


def _read_string(src: str, i: int, raw: bool) -> tuple[Tok, int]:
    """Parse one string literal starting at src[i] (a quote). Returns (tok, next_i)."""
    n = len(src)
    start = i
    q = src[i]

    triple = src.startswith(q * 3, i)
    if triple:
        i += 3
        closer = q * 3
    else:
        i += 1
        closer = q

    out: list[str] = []
    interp_spans: list[tuple[int, int]] = []
    interp_texts: list[str] = []
    interpolated = False

    while i < n:
        if src.startswith(closer, i):
            i += len(closer)
            break

        c = src[i]

        if not raw and c == "\\":
            # escape sequence
            if i + 1 < n:
                e = src[i + 1]
                simple = {"n": "\n", "r": "\r", "t": "\t", "b": "\b",
                          "f": "\f", "v": "\v", "0": "\0",
                          "'": "'", '"': '"', "\\": "\\", "$": "$"}
                if e in simple:
                    out.append(simple[e])
                    i += 2
                    continue
                if e == "x":
                    hexpart = src[i + 2:i + 4]
                    try:
                        out.append(chr(int(hexpart, 16)))
                        i += 4
                        continue
                    except ValueError:
                        pass
                if e == "u":
                    if src.startswith("u{", i + 1):
                        j = src.find("}", i + 3)
                        if j > 0:
                            try:
                                out.append(chr(int(src[i + 3:j], 16)))
                                i = j + 1
                                continue
                            except ValueError:
                                pass
                    hexpart = src[i + 2:i + 6]
                    try:
                        out.append(chr(int(hexpart, 16)))
                        i += 6
                        continue
                    except ValueError:
                        pass
                # unknown escape: keep the escaped char verbatim
                out.append(e)
                i += 2
                continue
            i += 1
            continue

        if not raw and c == "$":
            interpolated = True
            s0 = i
            if i + 1 < n and src[i + 1] == "{":
                depth = 1
                j = i + 2
                while j < n and depth:
                    if src[j] == "{":
                        depth += 1
                    elif src[j] == "}":
                        depth -= 1
                    elif src[j] in "'\"":
                        # skip nested string in the interpolation
                        _t, j = _read_string(src, j, False)
                        continue
                    j += 1
                interp_spans.append((s0, j))
                interp_texts.append(src[s0:j])
                out.append(src[s0:j])          # keep placeholder text for the key
                i = j
                continue
            j = i + 1
            while j < n and _is_id_cont(src[j]):
                j += 1
            interp_spans.append((s0, j))
            interp_texts.append(src[s0:j])
            out.append(src[s0:j])
            i = j
            continue

        out.append(c)
        i += 1

    return (
        Tok(
            kind="str",
            start=start,
            end=i,
            value="".join(out),
            raw=raw,
            triple=triple,
            interpolated=interpolated,
            interp_spans=tuple(interp_spans),
            interp_texts=tuple(interp_texts),
        ),
        i,
    )


def mask_non_code(src: str) -> str:
    """
    Return a copy of src where every string literal and comment is replaced by
    spaces of the same length. Offsets stay valid, so you can test "what does
    the code look like around position X" without strings confusing you.
    """
    buf = list(src)
    n = len(src)
    i = 0
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                buf[k] = " "
            i = j
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            depth = 1
            j = i + 2
            while j < n and depth:
                if src.startswith("/*", j):
                    depth += 1
                    j += 2
                elif src.startswith("*/", j):
                    depth -= 1
                    j += 2
                else:
                    j += 1
            for k in range(i, j):
                buf[k] = " "
            i = j
            continue
        if c in "'\"":
            _t, j = _read_string(src, i, False)
            for k in range(i, j):
                if buf[k] != "\n":
                    buf[k] = " "
            i = j
            continue
        i += 1
    return "".join(buf)


if __name__ == "__main__":
    import sys
    text = open(sys.argv[1], encoding="utf-8").read()
    for t in lex(text):
        if t.kind == "str":
            print(f"{t.start:>7} {t.end:>7} interp={int(t.interpolated)} {t.value!r}")
