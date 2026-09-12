#!/usr/bin/env python3
"""
Wire the app up so the UI language follows the phone.

The codemod handles every string the app itself prints. This script handles the
rest of the plumbing:

  pubspec.yaml                        add flutter_localizations
  lib/main.dart                       call initI18n() before the first frame
  lib/presentation/main_app.dart      declare supportedLocales and the
                                      localizations delegates

Without the third one the app's own strings would be Chinese while Flutter's
built-in widgets - the date picker, the text selection menu, the accessibility
labels - stayed English, which looks broken.

Every edit is anchored on a distinctive piece of upstream source and tagged
with a marker comment. Anchors that no longer match raise an error instead of
silently doing nothing, so an upstream refactor shows up as a failed CI run
rather than a half-translated build.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MARK = "// [weblibre-zh]"

I18N_IMPORT = "import 'package:weblibre/i18n/i18n.dart';"
FL_IMPORT = "import 'package:flutter_localizations/flutter_localizations.dart';"

MAIN_APP = "apps/weblibre/lib/presentation/main_app.dart"
MAIN = "apps/weblibre/lib/main.dart"
PUBSPEC = "apps/weblibre/pubspec.yaml"
GRADLE = "apps/weblibre/android/app/build.gradle"

MATERIAL_APP_BLOCK = f"""          {MARK} framework-level localisation so Flutter's own widgets (date
          // pickers, text selection menus, accessibility labels) follow the
          // device language too, not just the tr() table.
          localizationsDelegates: const [
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: const [Locale('en'), Locale('zh')],
          localeResolutionCallback: (locale, supported) {{
            for (final l in supported) {{
              if (l.languageCode == locale?.languageCode) return l;
            }}
            return supported.first;
          }},
"""


class PatchError(RuntimeError):
    pass


def add_import(src: str, import_line: str, *, after: str | None = None) -> str:
    """Insert an import once, keeping the existing import block tidy."""
    if import_line in src:
        return src
    if after:
        m = re.search(rf"^{re.escape(after)}[ \t]*$", src, re.M)
        if m:
            return src[:m.end()] + "\n" + import_line + src[m.end():]
    matches = list(re.finditer(r"^[ \t]*import\s+[^;]*;[ \t]*$", src, re.M))
    if not matches:
        raise PatchError("no import block found")
    m = matches[-1]
    return src[:m.end()] + "\n" + import_line + src[m.end():]


def patch_pubspec(path: Path) -> bool:
    src = path.read_text(encoding="utf-8")
    if "flutter_localizations:" in src:
        return False
    anchor = re.search(r"^(  flutter:\n(?:    .*\n)+)", src, re.M)
    if not anchor:
        raise PatchError(f"{path}: could not find the `flutter:` dependency block")
    insert = "  flutter_localizations:\n    sdk: flutter\n"
    out = src[:anchor.end()] + insert + src[anchor.end():]
    path.write_text(out, encoding="utf-8")
    return True


def patch_main_app(path: Path) -> bool:
    src = path.read_text(encoding="utf-8")
    if MARK in src:
        return False
    m = re.search(r"^([ \t]*)return MaterialApp\.router\(\n", src, re.M)
    if not m:
        raise PatchError(
            f"{path}: could not find `return MaterialApp.router(` - upstream "
            f"changed; update the anchor in patch_app.py")
    out = src[:m.end()] + MATERIAL_APP_BLOCK + src[m.end():]
    out = add_import(out, FL_IMPORT)
    path.write_text(out, encoding="utf-8")
    return True


def patch_main(path: Path) -> bool:
    src = path.read_text(encoding="utf-8")
    if MARK in src:
        return False
    m = re.search(r"^[ \t]*WidgetsFlutterBinding\.ensureInitialized\(\);[ \t]*\n",
                  src, re.M)
    if not m:
        raise PatchError(
            f"{path}: could not find WidgetsFlutterBinding.ensureInitialized()")
    insert = (
        f"\n  {MARK} choose the UI language from the device before the first\n"
        f"  // frame is built, so nothing flashes English first.\n"
        f"  initI18n();\n"
    )
    out = src[:m.end()] + insert + src[m.end():]
    out = add_import(out, I18N_IMPORT)
    path.write_text(out, encoding="utf-8")
    return True


def patch_gradle(path: Path) -> bool:
    """
    Let the release build fall back to debug signing when no keystore is given.

    Upstream's gradle file points the release build at a keystore supplied
    through KEY_PATH / KEY_ALIAS / KEY_PASSWORD secrets. A fork does not have
    those, and without this fallback `storeFile` ends up null, which produces an
    *unsigned* APK that Android refuses to install. Falling back to the debug
    key keeps the fork buildable out of the box; supplying the secrets restores
    proper release signing.
    """
    src = path.read_text(encoding="utf-8")
    if MARK in src:
        return False
    anchor = "            signingConfig = signingConfigs.release"
    if anchor not in src:
        raise PatchError(
            f"{path}: could not find `signingConfig = signingConfigs.release`")
    replacement = (
        f"            {MARK} use the real keystore when the secrets are present,\n"
        f"            // otherwise fall back to debug signing so a fork still\n"
        f"            // produces an installable APK.\n"
        f"            signingConfig = System.getenv(\"KEY_PATH\") "
        f"? signingConfigs.release : signingConfigs.debug"
    )
    path.write_text(src.replace(anchor, replacement, 1), encoding="utf-8")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    targets = [
        ("pubspec.yaml", repo / PUBSPEC, patch_pubspec, "flutter_localizations:"),
        ("main.dart", repo / MAIN, patch_main, MARK),
        ("main_app.dart", repo / MAIN_APP, patch_main_app, MARK),
        ("build.gradle", repo / GRADLE, patch_gradle, MARK),
    ]

    for name, path, fn, marker in targets:
        if not path.exists():
            print(f"WARN: missing {path} - skipping {name}", file=sys.stderr)
            continue
        if args.dry_run:
            src = path.read_text(encoding="utf-8")
            print(f"{name:<16} {'already patched' if marker in src else 'would patch'}")
            continue
        try:
            changed = fn(path)
        except PatchError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1
        print(f"{name:<16} {'patched' if changed else 'already patched'}")

    print("\napp-level locale wiring is in place")
    return 0


if __name__ == "__main__":
    sys.exit(main())
