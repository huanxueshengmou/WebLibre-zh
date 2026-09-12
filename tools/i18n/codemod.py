#!/usr/bin/env python3
"""Localise UI literals using the official Dart AST for all safety decisions.

The scanner chooses *which* English text is UI copy. Dart's own parser decides
*where* it is safe to introduce a runtime call. Constant declarations, parameter
defaults, annotations, enum values and constant patterns stay unchanged; their
keys remain in the manifest so audited UI consumers can translate them later.
Only explicit const *expressions* enclosing an actual replacement are removed.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scan_strings as S
from ast_bridge import analyze_sources, assert_parsed, blocking_reason, constants_covering

HERE = Path(__file__).resolve().parent
IMPORT_LINE = "import 'package:weblibre/i18n/i18n.dart';"
RUNTIME_DEST = Path("apps/weblibre/lib/i18n/i18n.dart")
TABLE_DEST = Path("apps/weblibre/lib/i18n/zh_table.dart")
RE_LAST_IMPORT = re.compile(r"^[ \t]*import\s+[^;]*;[ \t]*$", re.M)
RE_PART_OF = re.compile(r"^[ \t]*part\s+of\s+(['\"])(.+?)\1\s*;", re.M)


def dart_escape(s: str) -> str:
    escapes = {"\\": "\\\\", '"': '\\"', "$": "\\$", "\n": "\\n",
               "\r": "\\r", "\t": "\\t", "\b": "\\b", "\f": "\\f"}
    return "".join(escapes.get(ch, f"\\u{ord(ch):04x}" if ord(ch) < 32 else ch)
                   for ch in s)


def replacement_for(hit: dict) -> str:
    template = dart_escape(hit["template"])
    if hit["interpolated"] and hit["args"]:
        return 'tr("%s", [%s])' % (template, ", ".join(hit["args"]))
    return 'tr("%s")' % template


def add_import(src: str) -> tuple[str, bool]:
    if IMPORT_LINE in src:
        return src, False
    matches = list(RE_LAST_IMPORT.finditer(src))
    if matches:
        end = matches[-1].end()
        return src[:end] + "\n" + IMPORT_LINE + src[end:], True
    m = re.search(r"^[ \t]*library\s+[^;]*;", src, re.M)
    if m:
        return src[:m.end()] + "\n\n" + IMPORT_LINE + src[m.end():], True
    return IMPORT_LINE + "\n" + src, True


def resolve_part_parent(root: Path, rel: str, src: str) -> str | None:
    m = RE_PART_OF.search(src)
    if not m:
        return None
    target = m.group(2)
    if target.startswith("package:weblibre/"):
        return target[len("package:weblibre/"):]
    if target.startswith("package:"):
        return None
    try:
        return ((root / rel).parent / target).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def record_key(manifest: dict, key: str, rel: str, interpolated: bool,
               deferred: bool = False) -> None:
    entry = manifest.setdefault(key, {"count": 0, "files": [], "interpolated": False,
                                      "deferred_count": 0})
    entry["deferred_count" if deferred else "count"] += 1
    if rel not in entry["files"] and len(entry["files"]) < 6:
        entry["files"].append(rel)
    entry["interpolated"] |= interpolated


def _one_pass(root: Path, ov: dict, dry_run: bool = False):
    hits, reasons = S.scan(root, ov)
    by_file: dict[str, list[dict]] = {}
    for hit in hits:
        by_file.setdefault(hit["file"], []).append(hit)
    sources = {rel: (root / rel).read_text(encoding="utf-8") for rel in by_file}
    plans = analyze_sources(sources)
    assert_parsed(plans)  # Parse the WHOLE batch before modifying any file.
    report = {
        "files_changed": 0, "changed_files": [], "replacements": 0,
        "const_removed": 0, "imports_added": 0, "skipped": [],
        "skip_reasons": Counter(), "import_targets": set(),
    }
    manifest: dict[str, dict] = {}
    outputs: dict[str, str] = {}
    for rel, file_hits in sorted(by_file.items()):
        src, plan = sources[rel], plans[rel]
        literals = {(node["start"], node["end"]) for node in plan["literals"]}
        edits: list[tuple[int, int, str]] = []
        const_to_delete: set[tuple[int, int]] = set()
        for hit in file_hits:
            start, end = hit["start"], hit["end"]
            if (start, end) not in literals:
                raise RuntimeError(f"Scanner/AST literal range mismatch: {rel}:{start}:{end}")
            why = blocking_reason(plan, start, end)
            # include_strings controls classification, NEVER language safety.
            if why:
                report["skip_reasons"][why] += 1
                report["skipped"].append({
                    "file": rel, "value": hit["value"], "template": hit["template"],
                    "interpolated": hit["interpolated"], "reason": why,
                    "line": src.count("\n", 0, start) + 1,
                })
                continue
            edits.append((start, end, replacement_for(hit)))
            report["replacements"] += 1
            for region in constants_covering(plan, start, end):
                const_to_delete.add((region["keyword_start"], region["keyword_end"]))
            record_key(manifest, hit["template"], rel, hit["interpolated"])
        if not edits:
            continue
        for start, end in sorted(const_to_delete):
            if end < len(src) and src[end] == " ":
                end += 1
            edits.append((start, end, ""))
        report["const_removed"] += len(const_to_delete)
        previous_end = -1
        for start, end, _text in sorted(edits):
            if start < previous_end or not (0 <= start <= end <= len(src)):
                raise RuntimeError(f"Overlapping/invalid edit in {rel}: {start}:{end}")
            previous_end = end
        out = src
        for start, end, text in sorted(edits, reverse=True):
            out = out[:start] + text + out[end:]
        if RE_PART_OF.search(out):
            parent = resolve_part_parent(root, rel, out)
            if parent is None or not (root / parent).is_file():
                raise RuntimeError(f"Cannot safely import translations for part file: {rel}")
            report["import_targets"].add(parent)
        else:
            out, added = add_import(out)
            report["imports_added"] += int(added)
        outputs[rel] = out
    for rel in sorted(report["import_targets"]):
        src = outputs.get(rel, (root / rel).read_text(encoding="utf-8"))
        out, added = add_import(src)
        if added:
            outputs[rel] = out
            report["imports_added"] += 1
    if outputs:
        # Independent re-parse of emitted text catches broken interpolation,
        # adjacency and splice mistakes before anything is written to disk.
        assert_parsed(analyze_sources(outputs))
    if not dry_run:
        for rel, text in outputs.items():
            (root / rel).write_text(text, encoding="utf-8")
    report["changed_files"] = sorted(outputs)
    report["files_changed"] = len(outputs)
    report["import_targets"] = sorted(report["import_targets"])
    return report, manifest, reasons


def transform(root: Path, ov: dict, dry_run: bool = False, max_passes: int = 5):
    total = {"files_changed": 0, "replacements": 0, "const_removed": 0,
             "imports_added": 0, "skipped": [], "skip_reasons": Counter(),
             "import_targets": set(), "passes": 0, "safety_engine": "dart-analyzer"}
    manifest: dict[str, dict] = {}
    changed_files: set[str] = set()
    for index in range(max_passes):
        rep, current, reasons = _one_pass(root, ov, dry_run)
        total["passes"] = index + 1
        changed_files.update(rep["changed_files"])
        for key in ("replacements", "const_removed", "imports_added"):
            total[key] += rep[key]
        total["import_targets"].update(rep["import_targets"])
        # Skips are a final-tree snapshot, not summed across convergence passes.
        total["skip_reasons"] = rep["skip_reasons"]
        total["skipped"] = rep["skipped"]
        for key, value in current.items():
            entry = manifest.setdefault(key, {"count": 0, "files": [],
                                             "interpolated": False, "deferred_count": 0})
            entry["count"] += value["count"]
            entry["interpolated"] |= value["interpolated"]
            entry["files"] = list(dict.fromkeys(entry["files"] + value["files"]))[:6]
        if rep["replacements"] == 0 or dry_run:
            break
    else:
        raise RuntimeError(f"Codemod did not converge after {max_passes} passes")
    for skip in total["skipped"]:
        record_key(manifest, skip["template"], skip["file"], skip["interpolated"], True)
    total["files_changed"] = len(changed_files)
    total["changed_files"] = sorted(changed_files)
    total["import_targets"] = sorted(total["import_targets"])
    total["deferred_occurrences"] = len(total["skipped"])
    total["deferred_unique_keys"] = len({item["template"] for item in total["skipped"]})
    return total, manifest, reasons


def install_runtime(repo_root: Path, dry_run: bool = False) -> list[str]:
    files = sorted(p for p in (HERE / "runtime").glob("*.dart")
                   if not p.name.endswith("_test.dart"))
    if not files:
        raise RuntimeError("Translation runtime is missing")
    written = []
    for source in files:
        destination = repo_root / RUNTIME_DEST.parent / source.name
        if not dry_run:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        written.append(destination.relative_to(repo_root).as_posix())
    return written


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    parser.add_argument("--app-lib", default="apps/weblibre/lib")
    parser.add_argument("--overrides", default=str(HERE / "overrides.json"))
    parser.add_argument("--manifest", default="i18n/strings.json")
    parser.add_argument("--report", default="i18n/transform-report.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    root = repo / args.app_lib
    if not root.is_dir():
        raise SystemExit(f"Not a directory: {root}")
    report, manifest, reasons = transform(root, S.load_overrides(Path(args.overrides)), args.dry_run)
    installed = install_runtime(repo, args.dry_run)
    for key in ("passes", "files_changed", "replacements", "const_removed", "deferred_occurrences"):
        print(f"{key:22}: {report[key]}")
    print(f"unique keys (incl. deferred): {len(manifest)}")
    print(f"deferred reasons      : {dict(report['skip_reasons'])}")
    if args.dry_run:
        return
    manifest_path = repo / args.manifest
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    for key, value in manifest.items():
        if key not in existing:
            existing[key] = value
            continue
        previous = existing[key]
        previous["count"] = previous.get("count", 0) + value["count"]
        previous["deferred_count"] = value["deferred_count"]
        previous["interpolated"] = previous.get("interpolated", False) or value["interpolated"]
        previous["files"] = list(dict.fromkeys(previous.get("files", []) + value["files"]))[:6]
    manifest_path.write_text(json.dumps(existing, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    (repo / args.report).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {args.manifest}, {args.report}; installed {', '.join(installed)}")


if __name__ == "__main__":
    main()
