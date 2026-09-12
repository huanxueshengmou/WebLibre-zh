"""Validate workflow YAML, cross-step references and shell syntax before push."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent


def main():
    dart = os.environ.get("DART") or shutil.which("dart")
    bash = os.environ.get("BASH_BIN") or shutil.which("bash")
    package = HERE / "dart_ast"
    workflow = HERE.parents[1] / ".github/workflows/i18n.yml"
    result = subprocess.run([
        dart, f"--packages={package / '.dart_tool/package_config.json'}",
        str(package / "bin/read_yaml.dart"), str(workflow),
    ], capture_output=True, text=True, encoding="utf-8", check=True)
    data = json.loads(result.stdout)
    assert data["on"]["push"]["branches"] == ["main"]
    count = 0
    for name, job in data["jobs"].items():
        ids = [step["id"] for step in job["steps"] if "id" in step]
        assert len(ids) == len(set(ids)), f"Duplicate step ID in {name}"
        refs = set(re.findall(r"steps\.([a-zA-Z_][a-zA-Z0-9_]*)\.", json.dumps(job)))
        assert refs <= set(ids), f"Undefined steps: {refs - set(ids)}"
        for step in job["steps"]:
            if "run" not in step:
                continue
            code = re.sub(r"\$\{\{.*?\}\}", "validated", step["run"])
            checked = subprocess.run([bash, "-n"], input=code,
                                     capture_output=True, text=True, encoding="utf-8")
            assert checked.returncode == 0, (name, step.get("name"), checked.stderr)
            count += 1
    build = data["jobs"]["build"]
    checkout = next(step for step in build["steps"] if step.get("uses", "").startswith("actions/checkout@"))
    assert checkout["with"]["ref"] == "${{ needs.translate.outputs.generated_sha }}"
    order = [step.get("id", step.get("name", "")) for step in build["steps"]]
    assert order.index("analyze") < order.index("Build native gomobile runtime")
    assert order.index("i18n_smoke") < order.index("Build native gomobile runtime")
    assert "revert-l10n" not in workflow.read_text(encoding="utf-8")
    print(f"PASS: YAML, step references, pinned build SHA, preflight order; {count} shell blocks")


if __name__ == "__main__":
    main()
