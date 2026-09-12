"""Regression corpus validated both by the official AST and Dart's compiler."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ast_bridge import analyze_sources, assert_parsed, blocking_reason, constants_covering
from codemod import transform, IMPORT_LINE
from scan_strings import load_overrides
from verify import problems_from_plan

# These are real Dart declarations, not fragments that happen to fool a lexer.
SOURCE = """
class Text {
  final String value;
  const Text(this.value);
}
class Box {
  final String title;
  final List<Text> children;
  const Box({required this.title, this.children = const []});
}
class Metadata {
  final Text child;
  const Metadata(this.child);
}
const specs = <String, Box>{
  'protocol': Box(title: 'Protocol options'),
};
const Map<String, List<Box>> deepSpecs = <String, List<Box>>{
  'key': [Box(title: 'Nested protocol label')],
};
const first = Text('First const label'), second = Text('Second const label');
class Status {
  final String title;
  const Status({this.title = 'Default title'});
  const Status.loading() : this(title: 'Loading status');
}
@Metadata(Text('Annotation title'))
class Annotated {}
enum Choice {
  yes('Enum title');
  final String title;
  const Choice(this.title);
  String get label => switch (this) { Choice.yes => 'Runtime enum label' };
}
void optional({Text child = const Text('Default button')}) {}
String classify(String value) => switch (value) {
  'Match value' => 'Matched label',
  _ => 'Other label',
};
void main() {
  const local = <String, Text>{'key': Text('Local const title')};
  const smaller = 1 < 2;
  final afterComparison = Text('After comparison');
  final cancel = const Text('Cancel');
  final ternary = smaller ? const Text('Yes') : const Text('No');
  final panel = const Box(title: 'Panel title', children: [Text('Panel row')]);
  final record = const (Text('Record title'), 4);
  final adjacent = const Text('First adjacent ' 'second adjacent');
  final interpolated = Text('Hello ${smaller ? 'nested runtime title' : 'other runtime title'}');
  final symbols = const Text('Literal ( < > : , ; characters');
  if (specs['protocol']!.title != ('Protocol ' + 'options') ||
      deepSpecs['key']!.first.title != 'Nested protocol label' ||
      const Status.loading().title != 'Loading status' ||
      first.value != 'First const label' || second.value != 'Second const label' ||
      local['key']!.value != 'Local const title' ||
      cancel.value != 'translated:Cancel' ||
      ternary.value != 'translated:Yes' ||
      afterComparison.value != 'translated:After comparison' ||
      panel.title != 'translated:Panel title' ||
      record.$1.value != 'translated:Record title' ||
      adjacent.value != 'translated:First adjacent second adjacent') {
    throw StateError('Regression values do not match');
  }
  print('Dart compiler and runtime regression passed');
}
"""


def run_tests() -> int:
    count = 0

    def check(condition: bool, label: str):
        nonlocal count
        count += 1
        if not condition:
            raise AssertionError(label)
        print(f"  pass  {label}")

    # Inserting a non-BMP ideograph proves UTF-16 offsets do not corrupt slices.
    source = "// Unicode offset regression: " + chr(0x20000) + "\n" + SOURCE
    plan = analyze_sources({"fixture.dart": source})["fixture.dart"]
    assert_parsed({"fixture.dart": plan})
    for text, reason in (
        ("Protocol options", "const-var-decl"),
        ("Nested protocol label", "const-var-decl"),
        ("Second const label", "const-var-decl"),
        ("Loading status", "const-ctor-decl"),
        ("Default button", "parameter-default"),
        ("Annotation title", "annotation-arg"),
        ("Enum title", "enum-const-arg"),
        ("Match value", "constant-pattern"),
    ):
        start = source.index("'" + text + "'")
        check(blocking_reason(plan, start, start + len(text) + 2) == reason, text)
    for text in ("Cancel", "Yes", "No", "Runtime enum label", "After comparison"):
        start = source.index("'" + text + "'")
        check(blocking_reason(plan, start, start + len(text) + 2) is None,
              f"runtime expression remains translatable: {text}")
    yes = source.index("'Yes'")
    no = source.index("'No'")
    left = constants_covering(plan, yes, yes + 5)
    right = constants_covering(plan, no, no + 4)
    check(left and right and left[0] != right[0], "ternary const regions do not overlap")

    cases = {
        "bad_map.dart": "const a = <String, Object>{'x': tr('bad')};",
        "bad_ctor.dart": "class A { const A() : title = tr('bad'); final String title; }",
        "bad_default.dart": "void f({String title = tr('bad')}) {}",
        "bad_nested.dart": "final a = const Box(children: [Text(tr('bad'))]);",
        "good_sibling.dart": "final a = [const Box(), Text(tr('good'))];",
        "good_ternary.dart": "final a = true ? const Box() : Text(tr('good'));",
        "good_method.dart": "class A { const A(); String get label => tr('good'); }",
        "bad_adjacent.dart": "final a = Text(tr('bad') 'dangling');",
    }
    for rel, item in analyze_sources(cases).items():
        check(bool(problems_from_plan(rel, item)) == rel.startswith("bad_"), rel)

    with tempfile.TemporaryDirectory(prefix="weblibre-ast-") as temporary:
        root = Path(temporary)
        target = root / "fixture.dart"
        target.write_text(source, encoding="utf-8")
        overrides = load_overrides(root / "absent.json")
        overrides["include_strings"] = ["Protocol options", "Default button"]
        report, manifest, _ = transform(root, overrides)
        generated = target.read_text(encoding="utf-8")
        check(report["replacements"] > 10, "corpus really rewrites UI strings")
        check("tr(\"Forced constant title\")" not in generated, "forced UI selection cannot bypass const safety")
        check("Protocol options" in manifest, "deferred constant keys remain in manifest")
        check(manifest["Protocol options"]["deferred_count"] > 0, "deferred counts are explicit")
        check(not problems_from_plan("fixture.dart", analyze_sources({"fixture.dart": generated})["fixture.dart"]),
              "generated corpus has no parser/constant-context errors")
        again, _, _ = transform(root, overrides)
        check(again["replacements"] == 0, "second transform is a no-op")
        check(generated == target.read_text(encoding="utf-8"), "second transform is byte-identical")
        # Compile the emitted program with the real compiler, not the AST guard.
        compiled_source = generated.replace(IMPORT_LINE, "") + (
            "\nString tr(String en, [List<Object?>? args]) => 'translated:$en';\n")
        target.write_text(compiled_source, encoding="utf-8")
        dart = os.environ.get("DART") or shutil.which("dart")
        kernel = root / "fixture.dill"
        subprocess.run([dart, "compile", "kernel", str(target), "-o", str(kernel)], check=True)
        subprocess.run([dart, str(kernel)], check=True)
        check(True, "actual Dart kernel compilation and execution")
    print(f"Official AST/compiler regression: {count} checks passed")
    return count


if __name__ == "__main__":
    run_tests()
