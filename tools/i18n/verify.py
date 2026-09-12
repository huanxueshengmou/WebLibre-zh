#!/usr/bin/env python3
"""
Check that the codemod produced valid Dart.

There is no Dart SDK on the machine that runs this, so instead of a real
analyser we re-lex the rewritten files and look for the specific ways this
transform is known to be able to break things:

  unbalanced          - a splice that cut into a bracket
  dangling-literal    - `tr("...") 'more text'` left over from string
                        concatenation that was not merged
  const-with-call     - a `const` still governing a `tr(...)` call, which is
                        not a compile-time constant
  default-value-call  - `= tr(...)` in a parameter list, which must be const
  enum-const-call     - a `tr(...)` in an enum constant's arguments
  annotation-call     - a `tr(...)` in an annotation argument
  unclosed-call       - a `tr(` whose parentheses never close

Exit code is non-zero when anything is found, so CI can gate on it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dart_lexer import lex  # noqa: E402
import scan_strings as S  # noqa: E402
from codemod import const_regions, const_is_ctor_decl, enum_body_spans, brace_depth_at  # noqa: E402


def find_tr_calls(toks) -> list[int]:
    """Indices of `tr` tokens that are followed by `(`."""
    out = []
    for i, t in enumerate(toks):
        if t.kind == "id" and t.value == "tr" and i + 1 < len(toks) and toks[i + 1].value == "(":
            out.append(i)
    return out


def call_end(toks, open_paren_idx: int) -> int | None:
    depth = 0
    j = open_paren_idx
    while j < len(toks):
        v = toks[j].value
        if v == "(":
            depth += 1
        elif v == ")":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return None


def bracket_balance(src: str) -> dict:
    toks = lex(src)
    depth = {"(": 0, "[": 0, "{": 0}
    pairs = {")": "(", "]": "[", "}": "{"}
    for t in toks:
        v = t.value
        if v in depth:
            depth[v] += 1
        elif v in pairs:
            depth[pairs[v]] -= 1
    return depth


def check_file(path: Path, rel: str, baseline: Path | None = None) -> list[dict]:
    src = path.read_text(encoding="utf-8")
    toks = lex(src)
    problems = []

    # ---- 1. bracket balance ------------------------------------------
    # Compare against the untouched original. Drift's generated SQL confuses
    # the lexer, so an absolute imbalance is not necessarily our doing; a
    # CHANGE in the imbalance always is.
    depth = bracket_balance(src)
    if baseline is not None:
        base_file = baseline / rel
        if base_file.exists():
            base = bracket_balance(base_file.read_text(encoding="utf-8"))
            depth = {k: depth[k] - base[k] for k in depth}
    for k, v in depth.items():
        if v != 0:
            problems.append({"kind": "unbalanced", "detail": f"{k} depth delta {v}"})

    # ---- 2. dangling literal after a tr(...) call ---------------------
    trs = find_tr_calls(toks)
    tr_call_spans = []
    for i in trs:
        e = call_end(toks, i + 1)
        if e is None:
            problems.append({"kind": "unclosed-call", "detail": f"tr( at offset {toks[i].start}"})
            continue
        tr_call_spans.append((i, e, toks[i].start, toks[e].end))

    for i, e, _s, _en in tr_call_spans:
        nxt = toks[e + 1] if e + 1 < len(toks) else None
        if nxt is not None and nxt.kind == "str":
            problems.append({
                "kind": "dangling-literal",
                "detail": f"string literal after tr() at offset {nxt.start}",
            })

    # ---- 3. const still governing a call ------------------------------
    cregions = const_regions(toks, len(src))
    for ci, rstart, rend, role in cregions:
        if const_is_ctor_decl(toks, ci):
            continue
        for i, e, ts, _te in tr_call_spans:
            if rstart <= ts < rend:
                problems.append({
                    "kind": "const-with-call",
                    "detail": f"const at offset {toks[ci].start} (role={role}) governs tr() at {ts}",
                })
                break

    # ---- 4. = tr(...) : parameter default / const initialiser ---------
    for i, e, ts, _te in tr_call_spans:
        prev = toks[i - 1] if i else None
        if prev is not None and prev.value == "=":
            problems.append({
                "kind": "default-value-call",
                "detail": f"= tr() at offset {ts}",
            })

    # ---- 5. enum constant argument -----------------------------------
    for a, b in enum_body_spans(toks):
        for i, e, ts, _te in tr_call_spans:
            if a <= ts < b and brace_depth_at(toks, i) <= 1:
                problems.append({
                    "kind": "enum-const-call",
                    "detail": f"tr() at offset {ts} inside enum constant args",
                })

    # ---- 6. annotation argument --------------------------------------
    for i, e, ts, _te in tr_call_spans:
        kind, bidx = S.enclosing_bracket(toks, i)
        if kind == "(" and bidx >= 2:
            c = toks[bidx - 1]
            a = toks[bidx - 2]
            if c.kind == "id" and a.value == "@":
                problems.append({
                    "kind": "annotation-call",
                    "detail": f"tr() at offset {ts} in annotation args",
                })

    for p in problems:
        p["file"] = rel
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--app-lib", default="apps/weblibre/lib")
    ap.add_argument("--baseline", default=None,
                    help="pristine copy of the same tree, for balance deltas")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    root = repo / args.app_lib
    baseline = None
    if args.baseline:
        b = Path(args.baseline).resolve() / args.app_lib
        baseline = b if b.is_dir() else None
    all_problems = []
    scanned = 0
    tr_total = 0

    for p in S.iter_dart_files(root):
        rel = p.relative_to(root).as_posix()
        try:
            src = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        if "tr(" not in src:
            continue
        tr_total += src.count("tr(")
        all_problems.extend(check_file(p, rel, baseline))

    kinds = Counter(p["kind"] for p in all_problems)
    print(f"files scanned : {scanned}")
    print(f"tr( occurrences: {tr_total}")
    print(f"problems      : {len(all_problems)}")
    if all_problems:
        print()
        for k, v in kinds.most_common():
            print(f"  {v:>5}  {k}")
        print()
        for p in all_problems[:40]:
            print(f"  [{p['kind']}] {p['file']}: {p['detail']}")

    if args.json:
        Path(args.json).write_text(
            json.dumps(all_problems, ensure_ascii=False, indent=1), encoding="utf-8")

    return 1 if all_problems else 0


if __name__ == "__main__":
    sys.exit(main())
