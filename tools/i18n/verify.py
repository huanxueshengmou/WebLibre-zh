#!/usr/bin/env python3
"""Fail closed on official Dart parse errors or translations in const contexts.

This syntax gate needs only Dart + package:analyzer, not Flutter/NDK/Go. The CI
also runs the real Flutter analyzer before native builds, and the regression
suite compiles generated standalone fixtures with Dart's kernel compiler.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan_strings as S
from ast_bridge import analyze_sources, blocking_reason, constants_covering


def problems_from_plan(rel: str, plan: dict) -> list[dict]:
    problems = []
    for error in plan["errors"]:
        problems.append({"file": rel, "kind": "dart-parse-error",
                         "detail": f"offset {error['start']}: {error['message']}"})
    for call in plan["calls"]:
        start, end = call["start"], call["end"]
        why = blocking_reason(plan, start, end)
        if why:
            problems.append({"file": rel, "kind": why,
                             "detail": f"translation call at offset {start} requires a constant"})
        for region in constants_covering(plan, start, end):
            problems.append({"file": rel, "kind": "const-with-call",
                             "detail": f"const at {region['keyword_start']} encloses call at {start}"})
    return problems


def check_file(path: Path, rel: str, baseline: Path | None = None) -> list[dict]:
    plan = analyze_sources({rel: path.read_text(encoding="utf-8")})[rel]
    return problems_from_plan(rel, plan)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    parser.add_argument("--app-lib", default="apps/weblibre/lib")
    parser.add_argument("--baseline", help="legacy option; official parsing requires no heuristic baseline")
    parser.add_argument("--json")
    args = parser.parse_args()
    root = Path(args.repo).resolve() / args.app_lib
    sources = {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
               for p in S.iter_dart_files(root)}
    # Include generated runtime/table too: a malformed translation must not make
    # it into an APK just because the scanner deliberately excludes its own code.
    runtime = root / "i18n"
    if runtime.is_dir():
        for p in runtime.glob("*.dart"):
            sources[p.relative_to(root).as_posix()] = p.read_text(encoding="utf-8")
    plans = analyze_sources(sources)
    problems = [problem for rel, plan in plans.items()
                for problem in problems_from_plan(rel, plan)]
    calls = sum(len(plan["calls"]) for plan in plans.values())
    print(f"official Dart parser : {len(plans)} files")
    print(f"translation calls    : {calls}")
    print(f"problems             : {len(problems)}")
    if problems:
        print(dict(Counter(problem["kind"] for problem in problems)))
        for problem in problems[:40]:
            print(f"[{problem['kind']}] {problem['file']}: {problem['detail']}")
    if args.json:
        Path(args.json).write_text(json.dumps(problems, ensure_ascii=False, indent=1), encoding="utf-8")
    return int(bool(problems))


if __name__ == "__main__":
    sys.exit(main())
