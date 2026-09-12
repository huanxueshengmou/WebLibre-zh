"""Official Dart AST bridge, with UTF-16 -> Python offset conversion.

Set DART to the SDK executable and run `dart pub get` in dart_ast/ once.
Missing SDK/dependencies fail closed: never silently fall back to guessing Dart
constant contexts from a hand-written token walk.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE / "dart_ast"


def utf16_offsets(source: str) -> list[int]:
    """Map every Dart UTF-16 code-unit boundary to a Python code-point index."""
    out = [0]
    for index, char in enumerate(source):
        if ord(char) > 0xFFFF:
            out.append(index)
        out.append(index + 1)
    return out


def analyze_sources(sources: dict[str, str]) -> dict[str, dict]:
    if not sources:
        return {}
    dart = os.environ.get("DART") or shutil.which("dart")
    packages = PACKAGE / ".dart_tool" / "package_config.json"
    if not dart:
        raise RuntimeError("Dart SDK required: set DART to dart/dart.exe before rewriting")
    if not packages.is_file():
        raise RuntimeError(f"AST dependencies missing: run dart pub get in {PACKAGE}")
    command = [dart, f"--packages={packages}", str(PACKAGE / "bin" / "analyze.dart")]
    run = subprocess.run(command, input=json.dumps(sources, ensure_ascii=False),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         encoding="utf-8", check=False, timeout=180)
    if run.returncode:
        raise RuntimeError(f"Official Dart AST analysis failed:\n{run.stderr}")
    plans = json.loads(run.stdout)
    if set(plans) != set(sources):
        raise RuntimeError("AST response did not cover every requested file")
    for rel, plan in plans.items():
        mapping = utf16_offsets(sources[rel])
        for group in ("blocks", "constants", "calls", "literals", "errors"):
            for item in plan[group]:
                for key in ("start", "end", "keyword_start", "keyword_end"):
                    if key in item:
                        item[key] = mapping[item[key]]
    return plans


def blocking_reason(plan: dict, start: int, end: int) -> str | None:
    for region in plan["blocks"]:
        if region["start"] <= start and end <= region["end"]:
            return region["reason"]
    return None


def constants_covering(plan: dict, start: int, end: int) -> list[dict]:
    return [region for region in plan["constants"]
            if region["start"] <= start and end <= region["end"]]


def assert_parsed(plans: dict[str, dict]) -> None:
    errors = [f"{rel}:{error['start']}: {error['message']}"
              for rel, plan in plans.items() for error in plan["errors"]]
    if errors:
        raise RuntimeError("Dart parse errors (no files changed):\n" + "\n".join(errors[:40]))
