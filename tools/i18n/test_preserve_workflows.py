"""Exercise the actual Git index/tree operation without touching remote branches."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from preserve_workflows import git, preserve_workflows


class PreserveWorkflowsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="weblibre-workflow-test-")
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "Workflow test")
        git(self.repo, "config", "user.email", "workflow-test@example.invalid")
        git(self.repo, "config", "core.autocrlf", "false")

    def write(self, name: str, content: str):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    def commit(self) -> str:
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "Fixture")
        return git(self.repo, "rev-parse", "HEAD").decode().strip()

    def test_upstream_workflow_changes_do_not_block_application_updates(self):
        self.write(".github/workflows/build.yml", "flutter-version: 3.47.0\n")
        self.write(".github/workflows/fork-only.yml", "name: Keep fork workflow\n")
        self.write("app.dart", "old application\n")
        baseline = self.commit()
        self.write(".github/workflows/build.yml", "flutter-version: 3.47.5\n")
        (self.repo / ".github/workflows/fork-only.yml").unlink()
        self.write(".github/workflows/new-upstream.yml", "name: Upstream addition\n")
        self.write(".github/ISSUE_TEMPLATE/bug.md", "updated template\n")
        self.write("app.dart", "new translated application\n")
        git(self.repo, "add", "-A")
        preserve_workflows(self.repo, baseline)
        tree = git(self.repo, "write-tree").decode().strip()
        self.assertEqual(git(self.repo, "show", tree + ":.github/workflows/build.yml"),
                         b"flutter-version: 3.47.0\n")
        self.assertEqual(git(self.repo, "ls-tree", tree, "--", ".github/workflows"),
                         git(self.repo, "ls-tree", baseline, "--", ".github/workflows"))
        self.assertEqual(git(self.repo, "show", tree + ":app.dart"), b"new translated application\n")
        self.assertEqual(git(self.repo, "show", tree + ":.github/ISSUE_TEMPLATE/bug.md"),
                         b"updated template\n")
        self.assertEqual((self.repo / ".github/workflows/build.yml").read_text(),
                         "flutter-version: 3.47.5\n")
        preserve_workflows(self.repo, baseline)
        self.assertEqual(git(self.repo, "write-tree").decode().strip(), tree)

    def test_baseline_without_workflows_does_not_import_new_ones(self):
        self.write("app.dart", "old\n")
        baseline = self.commit()
        self.write(".github/workflows/new.yml", "name: Upstream only\n")
        self.write("app.dart", "new\n")
        git(self.repo, "add", "-A")
        preserve_workflows(self.repo, baseline)
        self.assertEqual(git(self.repo, "ls-files", "--", ".github/workflows"), b"")
        self.assertEqual(git(self.repo, "show", ":app.dart"), b"new\n")

    def test_upstream_without_workflows_restores_fork_workflows(self):
        self.write(".github/workflows/fork.yml", "name: Fork only\n")
        baseline = self.commit()
        (self.repo / ".github/workflows/fork.yml").unlink()
        git(self.repo, "add", "-A")
        preserve_workflows(self.repo, baseline)
        self.assertEqual(git(self.repo, "show", ":.github/workflows/fork.yml"),
                         b"name: Fork only\n")

    def test_neither_tree_has_workflows(self):
        self.write("app.dart", "old\n")
        baseline = self.commit()
        self.write("app.dart", "new\n")
        git(self.repo, "add", "-A")
        before = git(self.repo, "write-tree")
        preserve_workflows(self.repo, baseline)
        self.assertEqual(git(self.repo, "write-tree"), before)

    def test_invalid_baseline_fails_without_changing_index(self):
        self.write(".github/workflows/build.yml", "name: Original\n")
        self.commit()
        before = git(self.repo, "write-tree")
        with self.assertRaises(subprocess.CalledProcessError):
            preserve_workflows(self.repo, "missing-baseline")
        self.assertEqual(git(self.repo, "write-tree"), before)


if __name__ == "__main__":
    unittest.main()
