#!/usr/bin/env python3
"""
Wire the app up so the UI language follows the phone.

The codemod handles every string the app itself prints. This script handles the
rest of the plumbing:

  pubspec.yaml (root)                 relax melos `enforceLockfile`
  apps/weblibre/pubspec.yaml          add flutter_localizations, widen intl
  lib/main.dart                       call initI18n() before the first frame
  lib/presentation/main_app.dart      declare supportedLocales + delegates
  android/app/build.gradle            fall back to debug signing

Without the delegates the app's own strings would be Chinese while Flutter's
built-in widgets - the date picker, the text selection menu, the accessibility
labels - stayed English, which looks broken.

Two upstream constraints make this delicate, so both are handled explicitly:

  * `melos bootstrap` runs with `enforceLockfile: true`, which fails as soon as
    pubspec.yaml no longer matches pubspec.lock. Adding a dependency
    invalidates the lockfile by definition, so that check has to be relaxed.

  * `flutter_localizations` pins `intl` to whatever version the Flutter SDK
    ships, and the app asks for a specific older range. Those two cannot both
    be satisfied, so the app's constraint is widened to `any` - the version is
    then decided by the SDK, which is the point of using the SDK's delegates.

Because dependency resolution cannot be verified without a Flutter SDK, the
workflow treats the framework-level part as optional: if `melos bootstrap`
still fails, it re-runs this script with --revert-l10n, which removes only the
flutter_localizations wiring and leaves the tr() translation fully in place.

Every edit is anchored on a distinctive piece of upstream source and tagged with
a marker comment. Anchors that no longer match raise an error instead of
silently doing nothing, so an upstream refactor shows up as a failed CI run
rather than a half-translated build.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MARK = "// [weblibre-zh]"
YAML_MARK = "# [weblibre-zh]"

I18N_IMPORT = "import 'package:weblibre/i18n/i18n.dart';"
FL_IMPORT = "import 'package:flutter_localizations/flutter_localizations.dart';"

MAIN_APP = "apps/weblibre/lib/presentation/main_app.dart"
MAIN = "apps/weblibre/lib/main.dart"
PUBSPEC = "apps/weblibre/pubspec.yaml"
ROOT_PUBSPEC = "pubspec.yaml"
GRADLE = "apps/weblibre/android/app/build.gradle"

FL_DEP_BLOCK = "  flutter_localizations:\n    sdk: flutter\n"

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


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def add_import(src: str, import_line: str) -> str:
    """Insert an import once, keeping the existing import block tidy."""
    if import_line in src:
        return src
    matches = list(re.finditer(r"^[ \t]*import\s+[^;]*;[ \t]*$", src, re.M))
    if not matches:
        raise PatchError("no import block found")
    m = matches[-1]
    return src[:m.end()] + "\n" + import_line + src[m.end():]


def drop_import(src: str, import_line: str) -> str:
    return re.sub(rf"^{re.escape(import_line)}[ \t]*\n", "", src, flags=re.M)


# --------------------------------------------------------------------------
# individual patches
# --------------------------------------------------------------------------

def patch_root_pubspec(path: Path) -> bool:
    """
    Relax melos's lockfile enforcement.

    Upstream bootstraps with `enforceLockfile: true`, which aborts when
    pubspec.yaml and pubspec.lock disagree. Adding flutter_localizations
    guarantees they disagree, so this has to be turned off or nothing builds.
    """
    if not path.exists():
        raise PatchError(f"missing {path}")
    src = path.read_text(encoding="utf-8")
    if YAML_MARK in src:
        return False
    anchor = "      enforceLockfile: true"
    if anchor not in src:
        raise PatchError(
            f"{path}: could not find `enforceLockfile: true` - upstream changed; "
            f"update the anchor in patch_app.py")
    replacement = (
        f"      {YAML_MARK} relaxed: we add a dependency (flutter_localizations),\n"
        f"      # so the lockfile necessarily differs from upstream's.\n"
        f"      enforceLockfile: false"
    )
    path.write_text(src.replace(anchor, replacement, 1), encoding="utf-8")
    return True


def patch_pubspec(path: Path) -> bool:
    src = path.read_text(encoding="utf-8")
    if FL_DEP_BLOCK in src:
        return False

    anchor = re.search(r"^(  flutter:\n(?:    .*\n)+)", src, re.M)
    if not anchor:
        raise PatchError(f"{path}: could not find the `flutter:` dependency block")
    src = src[:anchor.end()] + FL_DEP_BLOCK + src[anchor.end():]

    # Widen the app's intl constraint. flutter_localizations pins intl to the
    # version bundled with the Flutter SDK; a narrower app constraint would make
    # the two unsatisfiable together. The original line is recorded in a comment
    # so --revert-l10n can put it back - leaving `intl: any` behind would let pub
    # upgrade intl past the range the app was written against.
    def widen(m: re.Match) -> str:
        return (
            f"  {YAML_MARK} widened: flutter_localizations pins intl to the SDK version\n"
            f"  {YAML_MARK} original: {m.group(0).strip()}\n"
            f"  intl: any"
        )

    src, n = re.subn(r"^  intl: \^[0-9][^\n]*$", widen, src, count=1, flags=re.M)
    if n == 0:
        raise PatchError(f"{path}: could not find the `intl:` constraint")

    path.write_text(src, encoding="utf-8")
    return True


def revert_pubspec(path: Path) -> bool:
    src = path.read_text(encoding="utf-8")
    changed = False

    if FL_DEP_BLOCK in src:
        src = src.replace(FL_DEP_BLOCK, "", 1)
        changed = True

    # Put the original intl constraint back, if we widened it.
    m = re.search(
        rf"^  {re.escape(YAML_MARK)} widened:[^\n]*\n"
        rf"  {re.escape(YAML_MARK)} original: (.+?)\n"
        rf"^  intl: any[ \t]*$",
        src, re.M)
    if m:
        src = src[:m.start()] + "  " + m.group(1).strip() + src[m.end():]
        changed = True

    if changed:
        path.write_text(src, encoding="utf-8")
    return changed


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


def revert_main_app(path: Path) -> bool:
    src = path.read_text(encoding="utf-8")
    if MATERIAL_APP_BLOCK not in src:
        return False
    src = src.replace(MATERIAL_APP_BLOCK, "", 1)
    src = drop_import(src, FL_IMPORT)
    path.write_text(src, encoding="utf-8")
    return True


def patch_gradle(path: Path) -> bool:
    """
    Let the release build fall back to debug signing when no keystore is given.

    Upstream points the release build at a keystore supplied through the
    KEY_PATH / KEY_ALIAS / KEY_PASSWORD secrets. A fork does not have those, and
    without this fallback `storeFile` ends up null, which produces an *unsigned*
    APK that Android refuses to install.
    """
    src = path.read_text(encoding="utf-8")
    if MARK in src:
        return False
    anchor = "            signingConfig = signingConfigs.release"
    if anchor not in src:
        raise PatchError(
            f"{path}: could not find `signingConfig = signingConfigs.release`")
    replacement = (
        f"            {MARK} Use the real keystore only when the secrets are present\n"
        f"            // AND the file is actually on disk. Testing the env var alone is\n"
        f"            // not enough: KEY_PATH can be exported while the keystore was\n"
        f"            // never written (no KEY_JKS secret), and a storeFile pointing at\n"
        f"            // a missing file fails the build.\n"
        f"            def zhKeyPath = System.getenv(\"KEY_PATH\")\n"
        f"            signingConfig = (zhKeyPath != null && !zhKeyPath.isEmpty() "
        f"&& file(zhKeyPath).exists())\n"
        f"                ? signingConfigs.release\n"
        f"                : signingConfigs.debug"
    )
    path.write_text(src.replace(anchor, replacement, 1), encoding="utf-8")
    return True


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------

APPLY = [
    ("root pubspec", ROOT_PUBSPEC, patch_root_pubspec, YAML_MARK),
    ("pubspec.yaml", PUBSPEC, patch_pubspec, FL_DEP_BLOCK),
    ("main.dart", MAIN, patch_main, MARK),
    ("main_app.dart", MAIN_APP, patch_main_app, MARK),
    ("build.gradle", GRADLE, patch_gradle, MARK),
]

REVERT = [
    ("main_app.dart", MAIN_APP, revert_main_app),
    ("pubspec.yaml", PUBSPEC, revert_pubspec),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--revert-l10n", action="store_true",
                    help="remove only the flutter_localizations wiring, keeping "
                         "the tr() translation intact")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()

    if args.revert_l10n:
        print("reverting framework-level localisation (keeping tr()):")
        for name, rel, fn in REVERT:
            path = repo / rel
            if not path.exists():
                print(f"  {name:<16} missing, skipped")
                continue
            changed = fn(path)
            print(f"  {name:<16} {'reverted' if changed else 'nothing to revert'}")
        return 0

    for name, rel, fn, marker in APPLY:
        path = repo / rel
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
