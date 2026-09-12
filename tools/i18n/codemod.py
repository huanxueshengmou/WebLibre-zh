#!/usr/bin/env python3
"""
Rewrite WebLibre's Dart sources so every user-visible English string goes
through `tr()` at runtime.

For each hit produced by scan_strings.py we replace the literal with a call:

    Text('Cancel')                      -> Text(tr("Cancel"))
    Text('Remove $name from here?')     -> Text(tr("Remove {0} from here?", [name]))

`tr()` returns the translation for the active locale, or the English original
when there is no translation. Because the English text stays in the source as
the lookup key, nothing is ever lost and untranslated strings degrade to
English instead of breaking.

THE const PROBLEM
-----------------
63% of these literals live inside a `const` expression, and a function call is
not a compile-time constant, so `const` has to go:

    const Text('Cancel')  ->  Text(tr("Cancel"))

Dropping `const` is harmless for widget construction (the object is simply no
longer canonicalised). It is FATAL in a handful of places where Dart requires a
compile-time constant. Those are detected and skipped rather than risked:

    default parameter values   void f({String s = 'x'})
    variable initialisers      const kName = 'x';
    annotation arguments       @Foo('x')
    switch case labels         case 'x':
    enum constant arguments    enum E { a('x') }

Every skip is recorded in the report so the untranslated remainder is known
exactly, never guessed at.

The transform is idempotent: `tr` is not a text-displaying callee, so a second
run over already-rewritten code finds nothing to do.
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
from dart_lexer import Tok, lex  # noqa: E402
import scan_strings as S  # noqa: E402

HERE = Path(__file__).resolve().parent

IMPORT_LINE = "import 'package:weblibre/i18n/i18n.dart';"
RUNTIME_DEST = Path("apps/weblibre/lib/i18n/i18n.dart")
TABLE_DEST = Path("apps/weblibre/lib/i18n/zh_table.dart")


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def dart_escape(s: str) -> str:
    """Escape a decoded string so it can be emitted inside double quotes."""
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
        else:
            out.append(ch)
    return "".join(out)


def replacement_for(hit: dict) -> str:
    """The `tr(...)` call text that replaces the literal."""
    tmpl = dart_escape(hit["template"])
    if hit["interpolated"] and hit["args"]:
        args = ", ".join(hit["args"])
        return 'tr("%s", [%s])' % (tmpl, args)
    return 'tr("%s")' % tmpl


def build_index(toks: list[Tok]) -> dict[int, int]:
    """Map a string token's start offset -> its index in the token list."""
    return {t.start: i for i, t in enumerate(toks) if t.kind == "str"}


# --------------------------------------------------------------------------
# const bookkeeping
# --------------------------------------------------------------------------

def const_regions(toks: list[Tok], src_len: int) -> list[tuple[int, int, int, str]]:
    """
    Every `const` keyword, as (token_index, region_start, region_end, role).

    The region is the extent of the expression the `const` governs, which is
    what we need in order to answer "does this `const` make my literal const?".
    """
    out = []
    for i, t in enumerate(toks):
        if t.kind != "id" or t.value != "const":
            continue
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if nxt is None:
            continue

        # ---- role: variable declaration vs construction -----------------
        role = "construct"
        j = i + 1
        # skip a type annotation and the declared name, if present
        saw_ident = 0
        while j < len(toks) and toks[j].kind in ("id", "op") and saw_ident < 3:
            v = toks[j].value
            if v == "=":
                role = "var-decl"
                break
            if v in ("(", "[", "{", "<"):
                break
            if toks[j].kind == "id":
                saw_ident += 1
            j += 1

        # ---- extent -----------------------------------------------------
        depth = 0
        end = None
        k = i + 1
        while k < len(toks):
            v = toks[k].value
            if v in ("(", "[", "{"):
                depth += 1
            elif v in (")", "]", "}"):
                depth -= 1
                if depth == 0:
                    end = toks[k].end
                    break
            elif depth == 0 and v in (";", ",") and k > i + 1:
                end = toks[k].start
                break
            k += 1
        if end is None:
            end = src_len
        out.append((i, nxt.start, end, role))
    return out


def const_is_ctor_decl(toks: list[Tok], ci: int) -> bool:
    """
    `const Foo(this.a, this.b);` declares a const constructor. Deleting that
    `const` would break every enum constant that uses it, so we never touch it.
    """
    j = ci + 1
    if j >= len(toks) or toks[j].kind != "id":
        return False
    j += 1
    if j >= len(toks) or toks[j].value != "(":
        return False
    depth = 0
    k = j
    while k < len(toks):
        v = toks[k].value
        if v == "(":
            depth += 1
        elif v == ")":
            depth -= 1
            if depth == 0:
                break
        elif v in ("this", "super"):
            return True
        k += 1
    return False


def brace_depth_at(toks: list[Tok], upto: int) -> int:
    """Curly-brace nesting depth at token index `upto`."""
    d = 0
    for t in toks[:upto]:
        if t.value == "{":
            d += 1
        elif t.value == "}":
            d -= 1
    return d


# --------------------------------------------------------------------------
# safety: refuse to touch places that need a compile-time constant
# --------------------------------------------------------------------------

def safety(toks: list[Tok], i: int, enum_spans: list[tuple[int, int]]) -> str | None:
    """Return a skip reason, or None when the literal is safe to rewrite."""
    start = toks[i].start
    prev = toks[i - 1] if i else None
    pv = prev.value if prev else ""

    # 1. default parameter value / variable initialiser
    #    `void f({String s = 'x'})`  /  `const kName = 'x';`
    if pv == "=":
        return "initializer-or-default"

    # 2. annotation argument: @Foo('x')
    kind, bidx = S.enclosing_bracket(toks, i)
    if kind == "(" and bidx >= 2:
        c = toks[bidx - 1]
        a = toks[bidx - 2]
        if c.kind == "id" and a.value == "@":
            return "annotation-arg"

    # 3. switch case label: `case 'x':`
    nxt = toks[i + 1] if i + 1 < len(toks) else None
    if nxt and nxt.value == ":":
        j = i - 1
        depth = 0
        steps = 0
        while j >= 0 and steps < 60:
            v = toks[j].value
            if v in (")", "]"):
                depth += 1
            elif v in ("(", "["):
                depth -= 1
            elif depth <= 0 and v == "case":
                return "switch-case-label"
            elif depth <= 0 and v in (";", "{", "}"):
                break
            j -= 1
            steps += 1

    # 4. enum constant argument. Enum constants live at brace depth 1 inside
    #    the enum body; method/getter bodies are deeper, and switch-expression
    #    arms inside them are ordinary runtime expressions and perfectly safe.
    for a, b in enum_spans:
        if a <= start < b:
            if brace_depth_at(toks, i) <= 1:
                return "enum-const-arg"
            break

    return None


def enum_body_spans(toks: list[Tok]) -> list[tuple[int, int]]:
    spans = []
    for i, t in enumerate(toks):
        if t.kind == "id" and t.value == "enum":
            j = i
            while j < len(toks) and toks[j].value != "{":
                j += 1
            if j >= len(toks):
                continue
            depth = 0
            k = j
            while k < len(toks):
                v = toks[k].value
                if v == "{":
                    depth += 1
                elif v == "}":
                    depth -= 1
                    if depth == 0:
                        break
                k += 1
            if k < len(toks):
                spans.append((toks[j].start, toks[k].end))
    return spans


# --------------------------------------------------------------------------
# imports
# --------------------------------------------------------------------------

RE_LAST_IMPORT = re.compile(r"^[ \t]*import\s+[^;]*;[ \t]*$", re.M)
RE_PART_OF = re.compile(r"^[ \t]*part\s+of\s+(['\"])(.+?)\1\s*;", re.M)


def add_import(src: str) -> tuple[str, bool]:
    """Insert the i18n import after the last import directive."""
    if IMPORT_LINE in src:
        return src, False
    matches = list(RE_LAST_IMPORT.finditer(src))
    if matches:
        m = matches[-1]
        return src[:m.end()] + "\n" + IMPORT_LINE + src[m.end():], True
    # no imports at all: put it after the library directive or at the very top
    m = re.search(r"^[ \t]*library\s+[^;]*;", src, re.M)
    if m:
        return src[:m.end()] + "\n\n" + IMPORT_LINE + src[m.end():], True
    return IMPORT_LINE + "\n" + src, True


def resolve_part_parent(root: Path, rel: str, src: str) -> str | None:
    """For `part of 'x.dart'`, the library file that must carry the import."""
    m = RE_PART_OF.search(src)
    if not m:
        return None
    target = m.group(2)
    if target.startswith("package:"):
        rest = target[len("package:"):]
        if rest.startswith("weblibre/"):
            return rest[len("weblibre/"):]
        return None
    # relative to the part file's directory
    base = (root / rel).parent
    try:
        return (base / target).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


# --------------------------------------------------------------------------
# main transform
# --------------------------------------------------------------------------

def _one_pass(root: Path, ov: dict, dry_run: bool = False):
    hits, reasons = S.scan(root, ov)
    by_file: dict[str, list[dict]] = {}
    for h in hits:
        by_file.setdefault(h["file"], []).append(h)

    report = {
        "files_changed": 0,
        "replacements": 0,
        "const_removed": 0,
        "imports_added": 0,
        "skipped": [],
        "skip_reasons": Counter(),
        "import_targets": set(),
    }
    manifest: dict[str, dict] = {}

    for rel, file_hits in sorted(by_file.items()):
        path = root / rel
        src = path.read_text(encoding="utf-8")
        toks = lex(src)
        idx = build_index(toks)
        enums = enum_body_spans(toks)
        cregions = const_regions(toks, len(src))

        edits: list[tuple[int, int, str]] = []          # (start, end, text)
        const_to_delete: set[int] = set()

        for h in file_hits:
            i = idx.get(h["start"])
            if i is None:
                report["skip_reasons"]["index-miss"] += 1
                continue

            why = safety(toks, i, enums)
            if why and not h.get("forced"):
                report["skip_reasons"][why] += 1
                report["skipped"].append({
                    "file": rel, "value": h["value"][:200], "reason": why,
                })
                continue

            # Which `const` keywords govern this literal? Decide safety BEFORE
            # queueing any edit - a `const kName = 'x';` initialiser cannot hold
            # a call, and replacing it anyway would emit broken Dart.
            enclosing = [(ci, role) for ci, rstart, rend, role in cregions
                         if rstart <= h["start"] < rend]
            if any(role == "var-decl" for _ci, role in enclosing) and not h.get("forced"):
                report["skip_reasons"]["const-var-decl"] += 1
                report["skipped"].append({
                    "file": rel, "value": h["value"][:200],
                    "reason": "const-var-decl",
                })
                continue

            # the literal itself
            edits.append((h["start"], h["end"], replacement_for(h)))
            report["replacements"] += 1

            # strip every const that would make this call a non-constant
            # expression, including enclosing ones such as `const Column(...)`
            for ci, _role in enclosing:
                if const_is_ctor_decl(toks, ci):
                    continue
                const_to_delete.add(ci)

            # record for the translation manifest
            key = h["template"]
            entry = manifest.setdefault(key, {"count": 0, "files": [], "interpolated": False})
            entry["count"] += 1
            if len(entry["files"]) < 6:
                entry["files"].append(rel)
            entry["interpolated"] = entry["interpolated"] or h["interpolated"]

        if not edits:
            continue

        # ---- apply const deletions -------------------------------------
        for ci in const_to_delete:
            ct = toks[ci]
            end = ct.end
            if end < len(src) and src[end] == " ":
                end += 1
            edits.append((ct.start, end, ""))
            report["const_removed"] += 1

        # ---- splice from the end so offsets stay valid -----------------
        edits.sort(key=lambda e: e[0])
        for a, b, _ in edits:
            if a < 0 or b > len(src) or a > b:
                raise SystemExit(f"bad edit range {a}:{b} in {rel}")

        out = src
        for a, b, text in sorted(edits, key=lambda e: -e[0]):
            out = out[:a] + text + out[b:]

        # ---- import ------------------------------------------------------
        if RE_PART_OF.search(out):
            parent = resolve_part_parent(root, rel, out)
            if parent:
                report["import_targets"].add(parent)
            else:
                report["skip_reasons"]["part-of-unresolved"] += 1
        else:
            out, added = add_import(out)
            if added:
                report["imports_added"] += 1

        if not dry_run:
            path.write_text(out, encoding="utf-8")
        report["files_changed"] += 1

    # ---- imports for the libraries that own part files ------------------
    for rel in sorted(report["import_targets"]):
        p = root / rel
        if not p.exists():
            report["skip_reasons"]["part-parent-missing"] += 1
            continue
        src = p.read_text(encoding="utf-8")
        out, added = add_import(src)
        if added:
            if not dry_run:
                p.write_text(out, encoding="utf-8")
            report["imports_added"] += 1

    report["import_targets"] = sorted(report["import_targets"])
    return report, manifest, reasons


def transform(root: Path, ov: dict, dry_run: bool = False, max_passes: int = 5):
    """
    Run the rewrite until it stops finding anything.

    One pass is not always enough. Rewriting an interpolated literal can turn
    text that used to be *inside* `${...}` into standalone literals:

        'Replaces ... $signedInFromBackup${cond ? ' It also takes the name.' : ''}'

    becomes

        tr("Replaces ... {0}{1}", [signedInFromBackup, cond ? " It also ..." : ""])

    and on the next pass that inner sentence is now a visible literal of its
    own. Iterating to a fixed point means the result no longer depends on how
    many times the tool happened to run, which is what makes it safe to call
    from CI on every upstream commit.
    """
    total = {
        "files_changed": 0, "replacements": 0, "const_removed": 0,
        "imports_added": 0, "skipped": [], "skip_reasons": Counter(),
        "import_targets": set(), "passes": 0,
    }
    manifest: dict[str, dict] = {}
    seen_skips: set[tuple[str, str, str]] = set()
    reasons: Counter = Counter()

    for p in range(max_passes):
        rep, man, rsn = _one_pass(root, ov, dry_run)
        total["passes"] = p + 1
        for k in ("files_changed", "replacements", "const_removed", "imports_added"):
            total[k] += rep[k]
        total["skip_reasons"] += rep["skip_reasons"]
        total["import_targets"] |= set(rep["import_targets"])
        for s in rep["skipped"]:
            key = (s["file"], s["value"], s["reason"])
            if key not in seen_skips:
                seen_skips.add(key)
                total["skipped"].append(s)
        for k, v in man.items():
            e = manifest.setdefault(k, {"count": 0, "files": [], "interpolated": False})
            e["count"] += v["count"]
            for f in v["files"]:
                if f not in e["files"] and len(e["files"]) < 6:
                    e["files"].append(f)
            e["interpolated"] = e["interpolated"] or v["interpolated"]
        reasons += rsn
        if rep["replacements"] == 0:
            break

    total["import_targets"] = sorted(total["import_targets"])
    return total, manifest, reasons


def install_runtime(repo_root: Path, dry_run: bool = False) -> list[str]:
    """Copy the hand-written runtime library into the app."""
    written = []
    src = HERE / "runtime" / "i18n.dart"
    dst = repo_root / RUNTIME_DEST
    if src.exists():
        if not dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        written.append(str(RUNTIME_DEST))
    return written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", help="repo root (contains apps/weblibre/lib)")
    ap.add_argument("--app-lib", default="apps/weblibre/lib")
    ap.add_argument("--overrides", default=str(HERE / "overrides.json"))
    ap.add_argument("--manifest", default="i18n/strings.json")
    ap.add_argument("--report", default="i18n/transform-report.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    root = repo / args.app_lib
    if not root.is_dir():
        raise SystemExit(f"not a directory: {root}")

    ov = S.load_overrides(Path(args.overrides))
    report, manifest, reasons = transform(root, ov, args.dry_run)
    written = install_runtime(repo, args.dry_run)

    print(f"passes        : {report['passes']}")
    print(f"files changed : {report['files_changed']}")
    print(f"replacements  : {report['replacements']}")
    print(f"const removed : {report['const_removed']}")
    print(f"imports added : {report['imports_added']}")
    print(f"unique strings: {len(manifest)}")
    print()
    print("--- skipped (must stay English) ---")
    for k, v in report["skip_reasons"].most_common():
        print(f"  {v:>6}  {k}")
    print()
    print("--- scan rejects ---")
    for k, v in reasons.most_common(8):
        print(f"  {v:>6}  {k}")

    if not args.dry_run:
        man_path = repo / args.manifest
        man_path.parent.mkdir(parents=True, exist_ok=True)

        # The manifest is a cumulative record of every string this project has
        # ever exposed, not a snapshot of one run. Merge rather than overwrite,
        # so a second (no-op) invocation does not wipe the translation key list.
        existing: dict[str, dict] = {}
        if man_path.exists():
            try:
                existing = json.loads(man_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                existing = {}
        for k, v in manifest.items():
            prev = existing.get(k)
            if prev:
                prev["count"] = prev.get("count", 0) + v["count"]
                for f in v["files"]:
                    if f not in prev.setdefault("files", []) and len(prev["files"]) < 6:
                        prev["files"].append(f)
                prev["interpolated"] = prev.get("interpolated", False) or v["interpolated"]
            else:
                existing[k] = v

        man_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=1, sort_keys=True),
            encoding="utf-8")

        rep = dict(report)
        rep["skip_reasons"] = dict(report["skip_reasons"])
        (repo / args.report).write_text(
            json.dumps(rep, ensure_ascii=False, indent=1),
            encoding="utf-8")
        print()
        print(f"wrote {args.manifest} ({len(existing)} keys total)")
        print(f"wrote {args.report}")
        for w in written:
            print(f"installed runtime -> {w}")


if __name__ == "__main__":
    main()
