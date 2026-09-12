#!/usr/bin/env python3
"""
Tests for the i18n toolchain.

Run with:  python tools/i18n/test_i18n.py

These cover the parts that are easy to get subtly wrong and expensive to debug
in a 40-minute CI build: placeholder handling, the translation quality gate,
Dart string escaping, and the merging of adjacent string literals.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from codemod import dart_escape, replacement_for  # noqa: E402
from dart_lexer import lex  # noqa: E402
from scan_strings import (  # noqa: E402
    classify, enclosing_bracket, is_rejected, string_runs,
)
from translate import acceptable, placeholders_ok, protect, restore  # noqa: E402

FAILURES: list[str] = []


def check(name: str, got, want) -> None:
    if got == want:
        print(f"  pass  {name}")
    else:
        FAILURES.append(name)
        print(f"  FAIL  {name}\n          got  = {got!r}\n          want = {want!r}")


def section(title: str) -> None:
    print(f"\n{title}")


# --------------------------------------------------------------------------
def test_placeholders() -> None:
    section("placeholder protection")

    masked, tokens = protect("Remove {0} from WebLibre?")
    check("braces are masked before translation", "{0}" in masked, False)
    check("round-trips", restore(masked, tokens), "Remove {0} from WebLibre?")

    masked, tokens = protect("{0} of {1} items")
    check("handles several placeholders", restore(masked, tokens), "{0} of {1} items")

    check("kept -> ok", placeholders_ok("a {0} b", "x {0} y"), True)
    check("dropped -> not ok", placeholders_ok("a {0} b", "x y"), False)
    check("duplicated -> not ok", placeholders_ok("a {0}", "x {0} {0}"), False)
    # Reordering is deliberately allowed: Chinese frequently reverses argument
    # order, so "Remove {0} from {1}" legitimately becomes "从 {1} 中移除 {0}".
    check("reordered -> still ok", placeholders_ok("a {0} b {1}", "x {1} y {0}"), True)


def test_quality_gate() -> None:
    section("translation quality gate")

    check("real translation accepted", acceptable("Cancel", "取消")[0], True)
    check("identity rejected", acceptable("Cancel", "Cancel")[0], False)
    check("non-chinese rejected", acceptable("Cancel", "Annuler")[0], False)
    check("empty rejected", acceptable("Cancel", "")[0], False)
    check("engine failure rejected", acceptable("Cancel", None)[0], False)
    check("lost placeholder rejected", acceptable("Remove {0}?", "移除？")[0], False)
    check("kept placeholder accepted", acceptable("Remove {0}?", "移除 {0}？")[0], True)
    check("runaway output rejected",
          acceptable("Save", "保存" * 200)[0], False)
    check("reason is reported", acceptable("Cancel", "Cancel")[1], "untranslated")


def test_dart_escaping() -> None:
    section("Dart string escaping")

    check("double quote", dart_escape('say "hi"'), 'say \\"hi\\"')
    check("dollar", dart_escape("cost $5"), "cost \\$5")
    check("newline", dart_escape("a\nb"), "a\\nb")
    check("carriage return", dart_escape("a\rb"), "a\\rb")
    check("tab", dart_escape("a\tb"), "a\\tb")
    check("backslash", dart_escape("a\\b"), "a\\\\b")
    check("chinese untouched", dart_escape("取消"), "取消")


def test_replacement() -> None:
    section("tr() call generation")

    check("plain literal",
          replacement_for({"template": "Cancel", "interpolated": False, "args": []}),
          'tr("Cancel")')
    check("interpolated literal",
          replacement_for({"template": "Remove {0}?",
                           "interpolated": True, "args": ["name"]}),
          'tr("Remove {0}?", [name])')
    check("quote inside text",
          replacement_for({"template": 'Say "hi"',
                           "interpolated": False, "args": []}),
          'tr("Say \\"hi\\"")')


def test_run_merging() -> None:
    section("adjacent literal merging")

    src = ("Text(\n"
           "  'These settings apply only to this container and fully replace '\n"
           "  'the global app-link settings.',\n"
           ")")
    runs = string_runs(lex(src), src)
    check("adjacent literals become one run", len(runs), 1)
    check("run contains both tokens", len(runs[0]), 2)

    src2 = "Text('a'), Text('b')"
    check("separate calls stay separate", len(string_runs(lex(src2), src2)), 2)

    src3 = "Text('a' 'b' 'c')"
    check("three-way concatenation", len(string_runs(lex(src3), src3)[0]), 3)


def test_context_classification() -> None:
    section("context classification")

    def how(src: str) -> tuple[str | None, str | None, str]:
        toks = lex(src)
        idx = [i for i, t in enumerate(toks) if t.kind == "str"][0]
        return classify(toks, idx)

    check("named argument", how("Text(title: 'Hi')"), ("title", None, "named"))
    check("positional Text arg", how("Text('Hi')"), (None, "Text", "positional"))
    check("list element", how("final x = ['Hi'];"), (None, None, "list"))
    # A method call resolves to the method name, not the receiver. That is what
    # we want: it keeps logger.e('...') out (callee 'e' is not a text widget)
    # while still matching things like Row.buildMenuSubTile('Proxy Settings').
    check("method call resolves to method name",
          how("logger.e('Hi')"), (None, "e", "positional"))
    check("qualified call resolves to method name",
          how("widgets.buildMenuSubTile('Proxy Settings')"),
          (None, "buildMenuSubTile", "positional"))
    check("=> getter", how("String get label => 'Hi';"), ("label", None, "arrow"))
    check("switch arm is not a getter",
          how("String get label => switch (this) { a => 'Hi' };")[0:3],
          (None, None, "arrow")[0:3])


def test_bracket_resolution() -> None:
    section("innermost enclosing bracket")

    src = "foo(bar(1), 'Hi')"
    toks = lex(src)
    i = [k for k, t in enumerate(toks) if t.kind == "str"][0]
    kind, _ = enclosing_bracket(toks, i)
    check("string is inside a call", kind, "(")

    src2 = "final x = ['Hi'];"
    toks2 = lex(src2)
    i2 = [k for k, t in enumerate(toks2) if t.kind == "str"][0]
    check("string is inside a list", enclosing_bracket(toks2, i2)[0], "[")

    # The bug that made the first version non-idempotent: a tr("...", [arg])
    # earlier in the file used to spoof the list detection.
    src3 = "a(tr('X', [y]));\nb('Hi');"
    toks3 = lex(src3)
    strs = [k for k, t in enumerate(toks3) if t.kind == "str"]
    check("later call arg not mistaken for a list element",
          enclosing_bracket(toks3, strs[-1])[0], "(")


def test_rejects() -> None:
    section("non-UI strings are rejected")

    def rej(s: str) -> bool:
        return is_rejected(s, arg_name=None, callee=None) is not None

    check("url", rej("https://example.com/x"), True)
    check("asset path", rej("assets/images/logo.png"), True)
    check("about:blank", rej("about:blank"), True)
    check("snake key", rej("some_snake_case_key"), True)
    check("dotted key", rej("a.b.c.d"), True)
    check("package id", rej("eu.weblibre.gecko"), True)
    check("date format", rej("yyyy-MM-dd"), True)
    check("sql", rej("SELECT * FROM t"), True)
    check("sql check constraint", rej('CHECK(a = 1)'), True)
    check("sql column def", rej("TEXT NOT NULL"), True)
    check("const name", rej("SOME_CONSTANT"), True)
    check("real sentence", rej("Always open links in their native apps"), False)
    check("single UI word", rej("Cancel"), False)
    check("preferences is not SQL", rej("Reset all preferences"), False)


def main() -> int:
    test_placeholders()
    test_quality_gate()
    test_dart_escaping()
    test_replacement()
    test_run_merging()
    test_context_classification()
    test_bracket_resolution()
    test_rejects()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {FAILURES}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
