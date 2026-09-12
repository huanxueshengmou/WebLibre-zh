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
    check("delete button is not SQL", rej("Delete"), False)
    check("update prompt is not SQL", rej("Check for updates"), False)
    check("single-word section is UI",
          is_rejected("Overview", arg_name="title", callee=None), None)
    check("loading label is UI",
          is_rejected("Testing...", arg_name="label", callee=None), None)


def test_patch_app_roundtrip() -> None:
    """
    patch_app.py edits five upstream files by anchoring on their text. If
    upstream renames something the anchor stops matching, and the failure mode
    is a silently half-patched build - so the anchors and the revert path are
    both exercised here against a miniature copy of the real files.
    """
    section("patch_app round-trip")

    import contextlib
    import io
    import tempfile

    from patch_app import main as patch_main

    FIXTURES = {
        "pubspec.yaml": (
            "name: weblibre_project\n"
            "\n"
            "melos:\n"
            "  command:\n"
            "    bootstrap:\n"
            "      enforceLockfile: true\n"
            "    clean:\n"
            "      hooks:\n"
        ),
        "apps/weblibre/pubspec.yaml": (
            "name: weblibre\n"
            "\n"
            "dependencies:\n"
            "  flutter:\n"
            "    sdk: flutter\n"
            "  flutter_auto_size_text: ^5.0.0\n"
            "  intl: ^0.20.3\n"
            "  json_annotation: ^4.12.0\n"
        ),
        "apps/weblibre/lib/main.dart": (
            "import 'dart:async';\n"
            "\n"
            "void main() async {\n"
            "  WidgetsFlutterBinding.ensureInitialized();\n"
            "\n"
            "  runApp(const ProviderScope(child: MyApp()));\n"
            "}\n"
        ),
        "apps/weblibre/lib/presentation/main_app.dart": (
            "import 'package:flutter/material.dart';\n"
            "\n"
            "class MainApp extends StatelessWidget {\n"
            "  Widget build(BuildContext context) {\n"
            "    return MaterialApp.router(\n"
            "      debugShowCheckedModeBanner: false,\n"
            "      routerConfig: router.value,\n"
            "    );\n"
            "  }\n"
            "}\n"
        ),
        "apps/weblibre/android/app/build.gradle": (
            "android {\n"
            "    buildTypes {\n"
            "        release {\n"
            "            signingConfig = signingConfigs.release\n"
            "        }\n"
            "    }\n"
            "}\n"
        ),
    }

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        for rel, body in FIXTURES.items():
            p = repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")

        def run(*argv: str) -> int:
            saved = sys.argv
            sys.argv = ["patch_app.py", str(repo), *argv]
            try:
                # patch_app is chatty; keep the test output readable.
                with contextlib.redirect_stdout(io.StringIO()):
                    return patch_main()
            finally:
                sys.argv = saved

        check("patch run exits 0", run(), 0)

        root = (repo / "pubspec.yaml").read_text(encoding="utf-8")
        app = (repo / "apps/weblibre/pubspec.yaml").read_text(encoding="utf-8")
        main_dart = (repo / "apps/weblibre/lib/main.dart").read_text(encoding="utf-8")
        main_app = (repo / "apps/weblibre/lib/presentation/main_app.dart").read_text(encoding="utf-8")
        gradle = (repo / "apps/weblibre/android/app/build.gradle").read_text(encoding="utf-8")

        check("melos lockfile enforcement relaxed", "enforceLockfile: false" in root, True)
        check("flutter_localizations added", "flutter_localizations:" in app, True)
        check("upstream intl range preserved", "  intl: ^0.20.3" in app, True)
        check("no speculative dependency widening", "intl: any" in app, False)
        check("initI18n called", "initI18n();" in main_dart, True)
        check("i18n import added to main.dart",
              "package:weblibre/i18n/i18n.dart" in main_dart, True)
        check("supportedLocales declared", "supportedLocales:" in main_app, True)
        check("delegates declared", "localizationsDelegates:" in main_app, True)
        check("ordered locale list callback", "localeListResolutionCallback:" in main_app, True)
        check("shared language policy", "resolveAppLocale(locales)" in main_app, True)
        check("signing falls back to debug", "signingConfigs.debug" in gradle, True)
        # Testing the env var alone is not enough: KEY_PATH can be exported
        # while the keystore was never written, and a storeFile pointing at a
        # missing file fails the build.
        check("signing checks the keystore file exists",
              "file(zhKeyPath).exists()" in gradle, True)

        # Running again must change nothing.
        before = {rel: (repo / rel).read_text(encoding="utf-8") for rel in FIXTURES}
        check("second run exits 0", run(), 0)
        after = {rel: (repo / rel).read_text(encoding="utf-8") for rel in FIXTURES}
        check("patch is idempotent", before == after, True)

        # Revert must remove the framework wiring and restore intl, while
        # leaving the tr() translation and its import untouched.
        check("revert exits 0", run("--revert-l10n"), 0)
        app2 = (repo / "apps/weblibre/pubspec.yaml").read_text(encoding="utf-8")
        main_app2 = (repo / "apps/weblibre/lib/presentation/main_app.dart").read_text(encoding="utf-8")
        check("flutter_localizations removed", "flutter_localizations:" in app2, False)
        check("intl constraint restored", "  intl: ^0.20.3" in app2, True)
        check("delegates removed", "localizationsDelegates" in main_app2, False)
        check("flutter_localizations import removed",
              "flutter_localizations" in main_app2, False)
        check("MaterialApp.router still intact",
              "return MaterialApp.router(" in main_app2, True)


def test_punctuation_normalization() -> None:
    section("Chinese punctuation normalisation")

    from translate import normalize_punctuation as norm

    check("question mark after CJK", norm("从你的设备?"), "从你的设备？")
    check("question mark before CJK", norm("清除?吗"), "清除？吗")
    check("exclamation mark", norm("变了很多!"), "变了很多！")
    check("colon after CJK", norm("遵循默认值:先询问"), "遵循默认值：先询问")
    check("comma after CJK", norm("容器,标签页"), "容器，标签页")
    check("semicolon after CJK", norm("第一项;第二项"), "第一项；第二项")
    check("sentence-final period", norm('"{0}"被删除.'), '"{0}"被删除。')
    # The space after the period is removed as well - Chinese does not put one
    # between sentences.
    check("period before more text",
          norm("无法确定. 你想继续吗"), "无法确定。你想继续吗")
    # Must not touch numbers, versions or URLs.
    check("decimal point untouched", norm("版本 3.14 发布"), "版本 3.14 发布")
    check("version untouched", norm("v1.2 已发布"), "v1.2 已发布")
    check("url untouched", norm("访问 https://a.b/c?d=1"), "访问 https://a.b/c?d=1")
    check("file extension untouched", norm("打开 config.json"), "打开 config.json")
    # Idempotent, and a no-op for text that is already correct.
    check("already full width", norm("确定？"), "确定？")
    check("normalising twice is stable", norm(norm("从你的设备?")), "从你的设备？")
    check("english untouched", norm("Cancel?"), "Cancel?")

    # MT leaves spaces hugging full-width marks; 143 of 1854 real entries did.
    check("space before full-width period",
          norm("未找到关联控制台 。"), "未找到关联控制台。")
    check("space before full-width comma",
          norm("容器 ，标签页"), "容器，标签页")
    check("spaces inside full-width quotes",
          norm("“ {0} ” 被备份"), "“{0}”被备份")
    check("space after full-width opening bracket",
          norm("（ 见上文 ）"), "（见上文）")
    check("space after sentence punctuation before CJK",
          norm("第一句。 第二句"), "第一句。第二句")
    # Newlines are meaningful in multi-line help text - never eat them.
    check("newline preserved",
          norm("第一段 。\n\n第二段 。"), "第一段。\n\n第二段。")
    check("newline after punctuation preserved",
          norm("结束 。\n下一行"), "结束。\n下一行")
    # Must not disturb latin-only spacing.
    check("latin spacing untouched",
          norm("Open in WebLibre now"), "Open in WebLibre now")


def test_translate_fallback() -> None:
    """
    Argos drops the private-use sentinels that protect {0}, which was silently
    costing ~100 strings per run. translate_one must notice and retry with the
    placeholder left in place.
    """
    section("placeholder fallback strategies")

    import re

    from translate import Engine, translate_one

    class DroppingSentinels(Engine):
        """Mimics Argos: strips sentinels, and loses the placeholder with them."""
        name = "fake"
        calls: list[str] = []

        def translate(self, text: str) -> str:
            type(self).calls.append(text)
            cleaned = re.sub(r"[\ue000-\ue0ff]", "", text)
            if "{0}" in cleaned:
                return "从这里移除 {0}？"
            return "从这里移除？"

    DroppingSentinels.calls = []
    cand, why = translate_one(DroppingSentinels(), "Remove {0} from here?")
    check("recovers via the raw-text strategy", cand, "从这里移除 {0}？")
    check("reported as ok", why, "ok")
    check("engine was called twice", len(DroppingSentinels.calls), 2)
    check("first call was sentinel-masked",
          "\ue000" in DroppingSentinels.calls[0], True)
    check("second call kept the braces",
          "{0}" in DroppingSentinels.calls[1], True)

    class AlwaysEmpty(Engine):
        name = "empty"

        def translate(self, text: str) -> str:
            return ""

    cand2, why2 = translate_one(AlwaysEmpty(), "Remove {0} from here?")
    check("both strategies failing yields None", cand2, None)
    check("failure reason surfaced", why2, "engine-failed")

    class KeepsEverything(Engine):
        name = "good"

        def translate(self, text: str) -> str:
            return "从这里移除 {0}？"

    cand3, why3 = translate_one(KeepsEverything(), "Remove {0} from here?")
    check("first strategy wins when it works", cand3, "从这里移除 {0}？")
    check("no unnecessary retry", why3, "ok")


def test_const_declarations_are_left_alone() -> None:
    """
    End-to-end: the two patterns that actually broke the build, run through the
    real codemod. Both must leave their strings English rather than emitting a
    tr() call into a position where Dart demands a compile-time constant.
    """
    section("const declarations stay const")

    import contextlib
    import io
    import tempfile

    from codemod import _one_pass
    import scan_strings as SS

    SRC = (
        "import 'package:flutter/material.dart';\n"
        "\n"
        "const singboxProxyFormSpecs = <String, String>{\n"
        "  'a': 'SOCKS Version',\n"
        "  'b': 'Connect Timeout',\n"
        "};\n"
        "\n"
        "class _Chip extends StatelessWidget {\n"
        "  const _Chip.loading()\n"
        "    : this(\n"
        "        label: 'Testing...',\n"
        "        tooltip: 'Latency test running',\n"
        "      );\n"
        "}\n"
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "lib").mkdir()
        target = root / "lib" / "spec.dart"
        target.write_text(SRC, encoding="utf-8")

        with contextlib.redirect_stdout(io.StringIO()):
            rep, _man, _r = _one_pass(root, SS.load_overrides(Path("nope.json")))

        out = target.read_text(encoding="utf-8")

    check("no tr() emitted into a const declaration", "tr(" in out, False)
    check("map declaration keeps its const", "const singboxProxyFormSpecs" in out, True)
    check("constructor declaration keeps its const", "const _Chip.loading()" in out, True)
    check("nothing was replaced", rep["replacements"], 0)
    check("strings are still present and English",
          all(s in out for s in ("SOCKS Version", "Connect Timeout",
                                 "Latency test running")), True)


def main() -> int:
    test_placeholders()
    test_quality_gate()
    test_dart_escaping()
    test_replacement()
    test_run_merging()
    test_context_classification()
    test_bracket_resolution()
    test_rejects()
    test_punctuation_normalization()
    test_translate_fallback()
    test_const_declarations_are_left_alone()
    test_patch_app_roundtrip()
    from test_ast_regressions import run_tests
    run_tests()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {FAILURES}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
