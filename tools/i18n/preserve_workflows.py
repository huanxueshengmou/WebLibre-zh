"""Keep generated workflows identical to the existing fork parent, index only.

Stage generated files before calling this helper; write the commit tree after it
without staging the upstream workflows again. Application sources stay intact.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

WORKFLOWS = ".github/workflows"


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args])


def preserve_workflows(repo: Path, source: str) -> None:
    # Resolve first, so a missing baseline cannot partially change the index.
    source_sha = git(repo, "rev-parse", "--verify", "--end-of-options",
                     source + "^{commit}").decode().strip()
    original = git(repo, "ls-tree", "-r", "--name-only", "-z",
                   source_sha, "--", WORKFLOWS)
    staged = git(repo, "ls-files", "-z", "--", WORKFLOWS)
    if original or staged:
        # Also removes staged additions absent from the source. Do not copy
        # from main: its workflows may differ from the existing zh branch.
        git(repo, "restore", "--source=" + source_sha, "--staged", "--", WORKFLOWS)
    git(repo, "diff", "--cached", "--exit-code", source_sha, "--", WORKFLOWS)
    count = original.count(b"\0")
    print(f"Preserved {count} workflows from {source_sha[:12]}; application changes remain staged.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source", required=True)
    args = parser.parse_args()
    preserve_workflows(args.repo.resolve(), args.source)


if __name__ == "__main__":
    main()
