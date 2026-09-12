#!/usr/bin/env python3
"""Translate audited constant UI data at display time, never at declaration time.

Persistent IDs, controller values, error details and highlight keys stay intact.
Every replacement has an expected count; an upstream change fails before any
file is written. Run before codemod.py on a clean upstream checkout.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ast_bridge import analyze_sources, assert_parsed
from patch_app import add_import, I18N_IMPORT, PatchError

HERE = Path(__file__).resolve().parent
MARK = "// [weblibre-zh-ui-v1] audited constant-data consumers"
SETTING = "features/settings/presentation/"
PROXY = "features/proxy/presentation/widgets/"
PATCHES = {
    SETTING + "widgets/settings_detail.dart": [
        ("Text(title)", "Text(tr(title))", 2),
        ("hintText: hintText,", "hintText: tr(hintText),", 1),
        ("        sections[sectionIndex].title,\n", "        tr(sections[sectionIndex].title),\n", 1),
        ("  final haystack = values.join(' ').toLowerCase();",
         "  final haystack = [...values, ...values.map(tr)].join(' ').toLowerCase();", 1),
    ],
    SETTING + "screens/settings.dart": [
        ("Text(category.title)", "Text(tr(category.title))", 1),
        ("Text(category.subtitle)", "Text(tr(category.subtitle))", 1),
        ("Text(title)", "Text(tr(title))", 1),
        ("? '$category • $section'", "? '${tr(category)} • ${tr(section)}'", 1),
        (": '$category • $section\\n$subtitle'",
         ": '${tr(category)} • ${tr(section)}\\n${trNullable(subtitle)}'", 1),
    ],
    PROXY + "profile_editor/structured_profile_form.dart": [
        ("field.required ? '${field.label} *' : field.label",
         "field.required ? '${tr(field.label)} *' : tr(field.label)", 4),
        ("helperText: field.helperText ?? 'Stored in secure storage.',",
         "helperText: tr(field.helperText ?? 'Stored in secure storage.'),", 1),
        ("helperText: field.helperText,", "helperText: trNullable(field.helperText),", 3),
    ],
    PROXY + "profile_editor/profile_editor_section.dart": [
        ("          title,\n", "          tr(title),\n", 1),
    ],
    PROXY + "profile_list/latency_chip.dart": [
        ("      label: label,", "      label: tr(label),", 1),
        ("      tooltip: tooltip,", "      tooltip: isError ? tooltip : tr(tooltip),", 1),
    ],
}
# Literals that become keys only through an audited dynamic UI consumer. This
# includes strings passed to tr directly (the scanner must skip lookup keys).
EXTRA_KEYS = (
    "Search settings", "Stored in secure storage.", "Connection", "Credentials",
    "Protocol Options", "TLS", "Transport", "Multiplex", "Dial", "Testing...",
    "Latency test running", "Failed", "Overview",
)


def patch_source(rel: str, source: str) -> str:
    if MARK in source:
        return source
    result = source
    for before, after, count in PATCHES[rel]:
        actual = result.count(before)
        if actual != count:
            raise PatchError(f"{rel}: expected {count} anchors, got {actual}: {before!r}")
        result = result.replace(before, after)
    return add_import(result, I18N_IMPORT) + "\n" + MARK + "\n"


def apply(repo: Path) -> int:
    root = repo / "apps/weblibre/lib"
    outputs = {}
    for rel in PATCHES:
        path = root / rel
        if not path.is_file():
            raise PatchError(f"Missing required UI consumer: {path}")
        source = path.read_text(encoding="utf-8")
        result = patch_source(rel, source)
        if result != source:
            outputs[rel] = result
    assert_parsed(analyze_sources(outputs))
    test_template = HERE / "runtime" / "i18n_smoke_test.dart"
    if not test_template.is_file():
        raise PatchError(f"Missing smoke-test template: {test_template}")
    test_source = test_template.read_text(encoding="utf-8")
    assert_parsed(analyze_sources({"i18n_smoke_test.dart": test_source}))
    for rel, result in outputs.items():
        (root / rel).write_text(result, encoding="utf-8")
    test_path = repo / "apps/weblibre/test/i18n_smoke_test.dart"
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text(test_source, encoding="utf-8")
    manifest_path = repo / "i18n/strings.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    for key in EXTRA_KEYS:
        entry = manifest.setdefault(key, {"count": 0, "deferred_count": 0,
                                         "files": [], "interpolated": False})
        entry["audited_ui_consumer"] = True
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8")
    print(f"Audited UI consumers: {len(outputs)} files changed; {len(EXTRA_KEYS)} dynamic keys; smoke test installed")
    return len(outputs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repo")
    args = parser.parse_args()
    apply(Path(args.repo).resolve())


if __name__ == "__main__":
    main()
