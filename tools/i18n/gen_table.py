#!/usr/bin/env python3
"""
Turn i18n/zh.json into apps/weblibre/lib/i18n/zh_table.dart.

The table has to be a Dart source file rather than a JSON asset because tr()
must be synchronous: it is called from inside build methods all over the app,
where an async asset load is not an option.

A single const map is used so the whole table lives in the constant pool -
no parsing at startup, no lazy allocation on first lookup.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HEADER = """// GENERATED FILE - DO NOT EDIT BY HAND.
//
// Source   : i18n/zh.json
// Producer : tools/i18n/gen_table.py
//
// To change a translation, edit tools/i18n/glossary.json (preferred, it wins
// over machine translation and survives a retranslation) or i18n/zh.json, then
// re-run the i18n workflow.
//
// The keys are the original English strings as they appear in the Dart source,
// which is what makes an untranslated string degrade to English instead of
// showing a placeholder.
library;

/// Simplified Chinese lookup table: English source text -> translation.
const Map<String, String> kZhTable = <String, String>{
"""

FOOTER = "};\n"


def dart_string(s: str) -> str:
    """Emit a Dart double-quoted string literal for an arbitrary value."""
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "$":
            out.append("\\$")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20:
            out.append("\\u{%x}" % ord(ch))
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--cache", default="i18n/zh.json")
    ap.add_argument("--out", default="apps/weblibre/lib/i18n/zh_table.dart")
    ap.add_argument("--check", action="store_true",
                    help="fail if the generated file would change")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    cache_path = repo / args.cache
    out_path = repo / args.out

    if not cache_path.exists():
        raise SystemExit(f"missing {cache_path} - run translate.py first")

    data = json.loads(cache_path.read_text(encoding="utf-8"))
    entries = {k: v for k, v in data.items() if not k.startswith("_")}

    lines = [HEADER]
    for k in sorted(entries):
        lines.append(f"  {dart_string(k)}: {dart_string(entries[k])},\n")
    lines.append(FOOTER)
    content = "".join(lines)

    if args.check:
        current = out_path.read_text(encoding="utf-8") if out_path.exists() else ""
        if current != content:
            print(f"{args.out} is out of date", file=sys.stderr)
            return 1
        print(f"{args.out} is up to date ({len(entries)} entries)")
        return 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    print(f"wrote {args.out} ({len(entries)} entries, {len(content)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
