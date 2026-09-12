#!/usr/bin/env python3
"""
Find user-visible English strings in the WebLibre Dart sources.

Strategy: lex every .dart file, then for each string literal look at the
*syntactic neighbourhood* to decide whether a human would ever read it.

A literal counts as user-visible when one of these holds:
  named      - it is a named argument on the UI whitelist (title:, subtitle: ...)
  positional - it is a positional argument of a widget that exists to show text
  arrow      - it is the body of a `=>` getter that is not toString()
  list       - it is an element of a list literal and reads like prose

Everything else - log lines, keys, URLs, SQL, CSS, regexes, asset paths, route
names, locale codes, format patterns - is rejected.

The reject rules are intentionally aggressive: a false negative (one English
word left untranslated) is cosmetic, a false positive (a URL becoming a
translation key) is a real bug.

Anything the heuristics get wrong can be pinned in overrides.json without
touching this file - that escape hatch is what makes unattended CI safe.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dart_lexer import Tok, lex  # noqa: E402

HERE = Path(__file__).resolve().parent

# --------------------------------------------------------------------------
# what we are willing to translate
# --------------------------------------------------------------------------

# Named arguments whose value is shown to the user.
#
# Deliberately NOT included, with reasons (learned by auditing every named
# argument that takes a string literal in this codebase):
#   name, aliasName  -> route identifiers / DB column aliases ('AddonManagerRoute')
#   value            -> data
#   key, id, tag     -> identifiers
#   path, url, mime, mimeType, charset, scheme, host, fileName, assetPath
#   entityName, functionName, moduleAndArgs, constructor, createViewStmt
#   sqlite, outboundType, source, verb, noun, activity, type, variant, viewType
#   defaultValue, orderKey, fontFamily, heroTag, debugLabel, debugName, icon
#   password, username, issuer, customSecretJson, remote, bundled, inArchive
#   localizedTitle   -> already-localized data from a remote feed
#   logMessage       -> log output
UI_NAMED_ARGS = {
    # text content
    "title", "titleText", "subtitle", "subtitleText",
    "label", "labelText", "hint", "hintText", "helperText", "errorText",
    "counterText", "prefixText", "suffixText", "disabledHint",
    "tooltip", "message", "description", "desc",
    "header", "caption", "summary", "body", "content",
    "text", "textSpan",
    # buttons / dialogs
    "confirmText", "cancelText", "okText", "positiveText", "negativeText",
    "actionLabel", "actionText", "buttonText", "dialogTitle",
    "confirmLabel", "manageLabel", "badgeLabel",
    # empty / none states
    "placeholder", "searchHint", "searchHintText", "emptyText", "emptyMessage",
    "emptyLabel", "emptyDescription", "noneTitle", "noneSubtitle",
    # a11y
    "semanticsLabel", "semanticLabel",
    # settings screens in this app
    "note", "reason", "consequence", "planTitle", "directTitle", "directSubtitle",
    "attributionLine", "invalidMessage", "errorMessage", "tabCountText",
    "describe", "describeDone",
}

# Widgets / constructors whose *positional* argument is display text.
#
# Callees audited and deliberately excluded: LanguageOption('ar') and
# CountryOption('AR') take locale/country codes, not prose.
TEXT_CALLEES = {
    "Text", "TextSpan", "RichText", "SelectableText",
    "TextButton", "ElevatedButton", "OutlinedButton", "FilledButton",
    "CupertinoButton", "SimpleDialogOption",
    "SnackBar", "Tooltip", "Semantics",
    "AppBar", "ListTile", "Dialog", "AlertDialog",
    "MenuItemButton", "PopupMenuItem", "DropdownMenuItem",
    "Chip", "ActionChip", "InputChip", "FilterChip", "ChoiceChip",
    "ToggleButtons", "Tab", "BottomNavigationBarItem", "NavigationDestination",
    # app-specific
    "buildMenuSubTile",
    "newTab", "closeTab", "duplicateTab", "nextTab", "previousTab",
    "lastUsedTab", "togglePinTab",
}

# Files we never touch.
SKIP_PATH_PARTS = (
    "/build/", "/.dart_tool/", "/generated/", "/gen/",
    "/test/", "/integration_test/", "/native/",
    "/packages/",
)

SKIP_SUFFIXES = (
    ".g.dart", ".freezed.dart", ".gr.dart", ".mocks.dart",
    ".pb.dart", ".pbenum.dart", ".pbjson.dart", ".pbserver.dart",
    ".config.dart", ".gen.dart",
    # Drift's generated database code. Its `=>` getters and constraint lists
    # hold SQL fragments such as 'fts5(trigger, content=bang)' and
    # 'PRIMARY KEY("trigger", "group")', never UI text.
    ".drift.dart",
    ".steps.dart",
)

# --------------------------------------------------------------------------
# reject rules
# --------------------------------------------------------------------------

RE_URL = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.I)
RE_MAILTO = re.compile(r"^(mailto|tel):", re.I)
RE_PATHY = re.compile(r"^(\.{0,2}/|/)[\w.\-/]*$")
RE_ASSET = re.compile(r"\.(png|jpe?g|svg|webp|gif|ico|ttf|otf|woff2?|json|html|css|js|wasm|mp4|mp3|zip|gz|db|sqlite)$", re.I)
RE_DOTTED_KEY = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
RE_SNAKE_KEY = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")
RE_KEBAB_KEY = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)+$")
RE_HEX_COLOR = re.compile(r"^#?[0-9a-fA-F]{3,8}$")
RE_MIME = re.compile(r"^[a-z]+/[a-z0-9.+\-]+$")
RE_DATE_FMT = re.compile(r"^[yMdHhmsSaAzZETDGkKjJwWnNlLqQcCxXoOpP:.\-/\s]+$")
RE_ONLY_SYMBOLS = re.compile(r"^[^0-9A-Za-z\u4e00-\u9fff]+$")
RE_HTTP_HEADER = re.compile(r"^[A-Z][A-Za-z0-9\-]{2,}$")
RE_SQL = re.compile(
    r"(?:\bSELECT\b[\s\S]*\bFROM\b|\bINSERT\s+(?:OR\s+\w+\s+)?INTO\b|"
    r"\bUPDATE\s+[\w\"`]+\s+SET\b|\bDELETE\s+FROM\b|"
    r"\b(?:CREATE|DROP|ALTER)\s+(?:TABLE|VIEW|INDEX|TRIGGER)\b|"
    r"^PRAGMA\s+|\bCHECK\s*\(|\b(?:PRIMARY|FOREIGN)\s+KEY\s*\(|"
    r"\bUNIQUE\s*\(|\bREFERENCES\s+\w+\s*\()",
    re.I,
)
# Column definitions such as 'TEXT NOT NULL' or 'INTEGER PRIMARY KEY'
RE_SQL_COLUMN = re.compile(
    r"\b(INTEGER|VARCHAR|BLOB|REAL|NUMERIC|BOOLEAN|TEXT)\s+"
    r"(NOT\s+NULL|PRIMARY\s+KEY|UNIQUE|DEFAULT|COLLATE)\b", re.I)
RE_JS = re.compile(r"(=>|\bfunction\b|\bdocument\.|\bwindow\.|\bvar\b|\bconst\b\s*=|;)")
RE_CSS = re.compile(r"[.#][\w\-]+\s*\{|\}\s*$|\bpx\b|\brem\b")
RE_BASE64 = re.compile(r"^[A-Za-z0-9+/]{24,}={0,2}$")
RE_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-")
RE_PACKAGE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){2,}$")
RE_VERSION = re.compile(r"^v?\d+(\.\d+)+([\-+].*)?$")
RE_UPPER_CONST = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")
RE_CHANNEL = re.compile(r"^(stable|beta|alpha|nightly|release|debug|profile)$", re.I)
RE_DOMAIN = re.compile(r"^[\w\-]+\.(com|org|net|io|dev|eu|cn)$", re.I)
# Dart exception toString() bodies look like `Foo(bar: $bar, baz: $baz)`
RE_TOSTRING = re.compile(r"^[A-Z][A-Za-z0-9_]*\(.*\)$", re.S)
# about:blank, chrome://, data:, view-source:
RE_INTERNAL_SCHEME = re.compile(r"^(about|chrome|data|view-source|resource|blob):", re.I)

LOG_HINTS = re.compile(
    r"\b(error|exception|failed|failure|stack|trace|debug|warn|verbose|"
    r"initializ|register|dispos|unmount|http|socket|stream|token|"
    r"cache hit|payload|endpoint|request|response)\b", re.I
)

# Single words that really are shown in this app's UI. Without this list the
# "no spaces -> not prose" rule would throw away half of the buttons.
SHORT_OK = {
    "OK", "Ok", "Yes", "No", "On", "Off", "All", "None", "Auto", "Never",
    "Always", "Done", "Save", "Saved", "Cancel", "Close", "Back", "Next",
    "Skip", "Retry", "Undo", "Redo", "Copy", "Cut", "Paste", "Select",
    "Unselect", "Search", "Add", "Edit", "Delete", "Remove", "Clear",
    "Reset", "Apply", "Share", "More", "Less", "Show", "Hide", "Open",
    "New", "Rename", "Settings", "History", "Downloads", "Bookmarks",
    "Containers", "Container", "Pinned", "Isolated", "Custom", "Default",
    "Allow", "Deny", "Block", "Accept", "Decline", "Continue", "Finish",
    "Start", "Stop", "Pause", "Resume", "Reload", "Refresh", "Sync",
    "English", "Chinese", "Japanese", "German", "French", "Spanish",
    "Enable", "Disable", "Enabled", "Disabled", "Private", "Public",
    "Global", "Local", "Strict", "Normal", "Advanced", "Basic", "Expert",
    "Proxy", "Tor", "Tabs", "Tab", "General", "Privacy", "Security",
    "Appearance", "Language", "Languages", "Theme", "Font", "Fonts",
    "About", "Help", "Info", "Warning", "Error", "Success", "Loading",
    "Upload", "Download", "Import", "Export", "Install", "Uninstall",
    "Update", "Updates", "Version", "Logs", "Log", "Report", "Support",
    "Unpin", "Pin", "Lock", "Unlock", "View", "Zoom", "Print", "Find",
    "Replace", "Sort", "Filter", "Group", "Direct", "Trace", "Regular",
    "Paused", "Inactive", "Empty", "Description", "Name", "Permissions",
    "Extensions", "Feedback", "Gestures", "Timeout", "Restore", "Sign Out",
    "Small Web", "New Feed", "Edit Feed", "Search Credits", "Account",
    "Subscription", "Supporter Subscription", "Supporter subscription",
    "Manage Subscription", "Update Payment Method", "Renew Subscription",
    "Subscribe", "Will not renew", "Past due", "Account Settings",
}


def looks_like_prose(s: str) -> bool:
    if not s or not s.strip():
        return False
    t = s.strip()
    if t in SHORT_OK:
        return True
    return bool(re.search(r"[A-Za-z]{2}", t))


def is_rejected(s: str, *, arg_name: str | None, callee: str | None) -> str | None:
    """Return a reason string if the literal must NOT be translated."""
    t = s.strip()

    if not t:
        return "empty"
    if RE_ONLY_SYMBOLS.match(t):
        return "symbols-only"
    if RE_URL.match(t) or RE_MAILTO.match(t):
        return "url"
    if RE_INTERNAL_SCHEME.match(t):
        return "internal-scheme"
    if RE_UUID.match(t):
        return "uuid"
    if RE_BASE64.match(t):
        return "base64"
    if RE_VERSION.match(t):
        return "version"
    if RE_HEX_COLOR.match(t) and len(t.replace("#", "")) in (3, 4, 6, 8):
        return "hex-color"
    if RE_MIME.match(t) and len(t) < 60:
        return "mime"
    if RE_PATHY.match(t):
        return "path"
    if RE_ASSET.search(t) and (" " not in t) and len(t) < 60:
        return "asset"
    if RE_DOTTED_KEY.match(t) and len(t.split(".")) >= 3:
        return "dotted-key"
    if RE_PACKAGE.match(t) and t.count(".") >= 2 and " " not in t:
        return "package-id"
    if RE_SNAKE_KEY.match(t) and len(t) < 40:
        return "snake-key"
    if RE_KEBAB_KEY.match(t) and len(t) < 40 and not t[0].isupper():
        return "kebab-key"
    if RE_UPPER_CONST.match(t) and " " not in t:
        return "const-name"
    if RE_DATE_FMT.match(t) and not re.search(r"[A-Za-z]{3,}", t):
        return "date-format"
    if RE_HTTP_HEADER.match(t) and "-" in t and " " not in t:
        return "http-header"
    if RE_CHANNEL.match(t):
        return "channel-name"
    if RE_DOMAIN.match(t):
        return "domain"
    if RE_SQL.search(t):
        return "sql"
    if RE_SQL_COLUMN.search(t):
        return "sql"
    if RE_JS.search(t) and len(t) > 40:
        return "js"
    if RE_CSS.search(t) and len(t) > 20:
        return "css"
    if RE_TOSTRING.match(t) and "$" in t:
        return "dart-tostring"
    if len(t) > 400:
        return "too-long"
    # Single words are accepted only at known display boundaries. Generic
    # fields such as reason/message also carry machine IDs (profileSwitch).
    explicit_ui = arg_name in {
        "title", "subtitle", "label", "labelText", "hintText", "helperText",
        "errorText", "tooltip", "header", "caption", "searchHintText",
    } or callee in {"Text", "TextSpan", "SelectableText", "RichText"}
    if " " not in t and not t.isupper() and t not in SHORT_OK and not explicit_ui:
        return "not-prose"
    if arg_name in ("message", "text", "content", "description", "value", "name") \
            and LOG_HINTS.search(t) and " " not in t:
        return "log-line"
    return None


# --------------------------------------------------------------------------
# context detection
# --------------------------------------------------------------------------

def _prev(toks: list[Tok], i: int, k: int = 1) -> Tok | None:
    j = i - k
    return toks[j] if 0 <= j < len(toks) else None


def _callee_before_paren(toks: list[Tok], paren_idx: int) -> str | None:
    """Name of the thing being called by the `(` at toks[paren_idx]."""
    p1 = _prev(toks, paren_idx, 1)
    if p1 and p1.kind == "id":
        return p1.value
    # generic invocation: Foo<T>('...')  /  Foo<T, U>('...')
    if p1 and p1.kind == "op" and p1.value == ">":
        depth = 0
        j = paren_idx - 1
        while j >= 0:
            v = toks[j].value
            if v == ">":
                depth += 1
            elif v == "<":
                depth -= 1
                if depth == 0:
                    break
            j -= 1
        c = _prev(toks, j, 1) if j >= 0 else None
        if c and c.kind == "id":
            return c.value
    return None


def enclosing_bracket(toks: list[Tok], i: int) -> tuple[str | None, int]:
    """
    The innermost bracket that encloses token `i`, as (kind, token index).

    Walk backwards counting already-closed brackets; the first opener met at
    depth zero is the one that encloses us. This is what tells a positional
    argument (`foo(a, 'x')`) apart from a list element (`['a', 'x']`) - a
    distinction the previous version guessed at by searching for a bare `[`,
    which a `tr("...", [arg])` elsewhere in the file could spoof.
    """
    depth = 0
    j = i - 1
    while j >= 0:
        v = toks[j].value
        if v in (")", "]", "}"):
            depth += 1
        elif v in ("(", "[", "{"):
            if depth == 0:
                return v, j
            depth -= 1
        j -= 1
    return None, -1


def _getter_name(toks: list[Tok], i: int) -> str | None:
    """
    Name of the getter whose body this literal is, or None.

    `String get moduleAndArgs => 'fts5(...)'`  ->  'moduleAndArgs'
    `completed => 'Restore finished.'`         ->  None  (a switch-expression
                                                        arm, not a getter)

    The distinction matters because Drift getters return SQL, while switch arms
    inside a getter return display text.
    """
    if i < 1 or toks[i - 1].value != "=>":
        return None
    if i >= 3 and toks[i - 2].kind == "id" and toks[i - 3].value == "get":
        return toks[i - 2].value
    return None


def _in_tostring(toks: list[Tok], i: int) -> bool:
    """
    True if the `=>` body at toks[i] belongs to a toString() override.

    A toString body is a single expression, so a short backwards walk that
    stops at the previous statement boundary is enough.
    """
    j = i - 1
    steps = 0
    while j >= 0 and steps < 40:
        v = toks[j].value
        if v == "toString":
            return True
        if v in (";", "{", "}"):
            return False
        j -= 1
        steps += 1
    return False


def classify(toks: list[Tok], i: int) -> tuple[str | None, str | None, str]:
    """
    Work out how the string at toks[i] is used.

    Returns (arg_name, callee, how) with how in
      'named' | 'positional' | 'arrow' | 'list' | 'other'
    """
    p1 = _prev(toks, i, 1)

    # `name: '...'`
    if p1 and p1.kind == "op" and p1.value == ":":
        p2 = _prev(toks, i, 2)
        if p2 and p2.kind == "id":
            p3 = _prev(toks, i, 3)
            if p3 and p3.kind == "op" and p3.value in ("?", ":"):
                return None, None, "other"
            return p2.value, None, "named"

    # `=> '...'`  (getter body, or a switch-expression arm inside one)
    if p1 and p1.kind == "op" and p1.value == "=>":
        if _in_tostring(toks, i):
            return None, None, "other"
        return _getter_name(toks, i), None, "arrow"

    # Argument or element position: decide from the innermost enclosing
    # bracket rather than from the token that happens to precede the literal.
    kind, bidx = enclosing_bracket(toks, i)
    if kind == "(":
        callee = _callee_before_paren(toks, bidx)
        if callee:
            return None, callee, "positional"
    elif kind == "[":
        return None, None, "list"

    return None, None, "other"


# --------------------------------------------------------------------------
# interpolation -> template + args
# --------------------------------------------------------------------------

def make_template(value: str, interp_texts) -> tuple[str, list[str]]:
    """
    Turn a (possibly interpolated) string into (template, arg_expressions).

    'Remove ${x.name} from WebLibre?' -> ('Remove {0} from WebLibre?', ['x.name'])
    """
    args: list[str] = []
    template = value
    for idx, raw in enumerate(interp_texts):
        if raw.startswith("${") and raw.endswith("}"):
            expr = raw[2:-1]
        elif raw.startswith("$"):
            expr = raw[1:]
        else:
            expr = raw
        args.append(expr)
        template = template.replace(raw, "{%d}" % idx, 1)
    return template, args


def string_runs(toks: list[Tok], src: str) -> list[list[int]]:
    """
    Group token indices into runs of adjacent string literals.

    Dart concatenates adjacent literals at compile time:

        Text(
          'These settings apply only to this container and fully replace '
          'the global app-link settings for its tabs.',
        )

    That is ONE string to the user and to the translator, and it must be
    replaced as one unit - rewriting only the first half would emit
    `tr("...") 'the global...'`, which is not valid Dart. So we always work
    on whole runs.
    """
    runs: list[list[int]] = []
    current: list[int] = []
    for i, t in enumerate(toks):
        if t.kind != "str":
            if current:
                runs.append(current)
                current = []
            continue
        if current:
            prev = toks[current[-1]]
            gap = src[prev.end:t.start]
            if gap.strip() == "":
                current.append(i)
                continue
            runs.append(current)
        current = [i]
    if current:
        runs.append(current)
    return runs


# --------------------------------------------------------------------------
# overrides
# --------------------------------------------------------------------------

DEFAULT_OVERRIDES = {
    "exclude_files": [],
    "exclude_strings": [],
    "include_strings": [],
    "extra_named_args": [],
    "extra_callees": [],
    "banned_named_args": [],
    "banned_getters": [],
}


def load_overrides(path: Path) -> dict:
    ov = {k: list(v) for k, v in DEFAULT_OVERRIDES.items()}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SystemExit(f"overrides.json is not valid JSON: {e}")
        for k in ov:
            if k in data:
                ov[k] = data[k]
    return ov


# --------------------------------------------------------------------------
# main scan
# --------------------------------------------------------------------------

def iter_dart_files(root: Path):
    for p in sorted(root.rglob("*.dart")):
        if p.relative_to(root).parts[0] == "i18n":
            continue  # never rewrite the translation runtime or generated table
        posix = p.as_posix()
        if any(part in posix for part in SKIP_PATH_PARTS):
            continue
        if p.name.endswith(SKIP_SUFFIXES):
            continue
        yield p


def scan(root: Path, overrides: dict | None = None) -> tuple[list[dict], Counter]:
    ov = overrides or {k: list(v) for k, v in DEFAULT_OVERRIDES.items()}
    named_args = (set(UI_NAMED_ARGS) | set(ov["extra_named_args"])) - set(ov["banned_named_args"])
    callees = set(TEXT_CALLEES) | set(ov["extra_callees"])
    hard_exclude = set(ov["exclude_strings"])
    hard_include = set(ov["include_strings"])
    banned_getters = set(ov["banned_getters"])
    excl_files = list(ov["exclude_files"])

    hits: list[dict] = []
    reasons: Counter = Counter()

    for path in iter_dart_files(root):
        rel = path.relative_to(root).as_posix()
        if any(re.search(pat, rel) for pat in excl_files):
            reasons["excluded-file"] += 1
            continue
        try:
            src = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if not re.search(r"[A-Za-z]{3}", src):
            continue

        toks = lex(src)
        for run in string_runs(toks, src):
            first = toks[run[0]]
            last = toks[run[-1]]

            # Adjacent literals are one string to Dart and to the reader, so
            # merge them before deciding anything.
            value = "".join(toks[k].value for k in run)
            interp_texts = tuple(txt for k in run for txt in toks[k].interp_texts)
            interpolated = any(toks[k].interpolated for k in run)

            arg, callee, how = classify(toks, run[0])
            # Translation keys must remain literals even if include_strings
            # selects their text. Otherwise a forced key nests tr(tr(...)) on
            # every pass and convergence is impossible.
            if how == "positional" and callee in {"tr", "trText", "trNullable"}:
                continue

            forced = value in hard_include
            if how == "other" and not forced:
                continue

            if not forced:
                if value in hard_exclude:
                    reasons["manual-exclude"] += 1
                    continue
                if how == "named" and arg not in named_args:
                    continue
                if how == "positional" and callee not in callees:
                    continue
                if how == "arrow" and arg in banned_getters:
                    reasons["banned-getter"] += 1
                    continue
                if how == "list":
                    # only prose-looking list elements; this skips enum tokens
                    if " " not in value.strip() or not value.strip()[0].isupper():
                        reasons["list-not-prose"] += 1
                        continue

                why = is_rejected(value, arg_name=arg, callee=callee)
                if why:
                    reasons[why] += 1
                    continue
                if not re.search(r"[A-Za-z]", value):
                    reasons["no-latin"] += 1
                    continue

            template, args = make_template(value, interp_texts)
            if interpolated and not re.search(r"[A-Za-z]{2}", template):
                # pure interpolation such as '$depth' or '${x}%' - nothing to say
                reasons["interp-only"] += 1
                continue

            hits.append({
                "file": rel,
                "start": first.start,
                "end": last.end,
                "raw_literal": src[first.start:last.end],
                "value": value,
                "template": template,
                "args": args,
                "arg": arg,
                "callee": callee,
                "how": how,
                "interpolated": interpolated,
                "raw_string": all(toks[k].raw for k in run),
                "triple": any(toks[k].triple for k in run),
                "parts": len(run),
                "forced": forced,
            })

    return hits, reasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="directory to scan (e.g. apps/weblibre/lib)")
    ap.add_argument("--json", help="write full hit list here")
    ap.add_argument("--overrides", default=str(HERE / "overrides.json"))
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    root = Path(args.root).resolve()
    ov = load_overrides(Path(args.overrides))
    hits, reasons = scan(root, ov)

    uniq = Counter(h["template"] for h in hits)
    files = Counter(h["file"] for h in hits)
    by_how = Counter(h["how"] for h in hits)

    print(f"scanned     : {root}")
    print(f"occurrences : {len(hits)}")
    print(f"unique      : {len(uniq)}")
    print(f"files       : {len(files)}")
    print(f"interpolated: {sum(1 for h in hits if h['interpolated'])}")
    print(f"by kind     : {dict(by_how)}")
    print()
    print("--- reject reasons ---")
    for k, v in reasons.most_common():
        print(f"  {v:>7}  {k}")
    print()
    print(f"--- top {args.top} unique ---")
    for s, c in uniq.most_common(args.top):
        print(f"  {c:>4}x  {s[:95]!r}")

    if args.json:
        Path(args.json).write_text(
            json.dumps({"hits": hits, "unique": uniq.most_common()},
                       ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
