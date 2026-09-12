#!/usr/bin/env python3
"""CI 专用：检查 codemod 字节幂等性，提取 Flutter/Gradle 失败 annotation。"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


def app_snapshot(repo: Path) -> dict[str, bytes]:
    app = repo / "apps/weblibre"
    manifest = repo / "i18n/strings.json"
    files = sorted(app.rglob("*.dart"))
    if not files or not manifest.is_file():
        raise RuntimeError("缺少应用 Dart 源码或 strings manifest，不能检查幂等性")
    return {path.relative_to(repo).as_posix(): path.read_bytes()
            for path in [*files, manifest]}


def check_idempotency(repo: Path) -> None:
    repo = repo.resolve()
    before = app_snapshot(repo)
    report = repo / "i18n/transform-report.json"
    original_report = report.read_bytes() if report.is_file() else None
    try:
        subprocess.run([sys.executable, str(Path(__file__).with_name("codemod.py")),
                        str(repo)], check=True)
    finally:
        # A verification-only no-op must not erase the initial run's counts.
        if original_report is not None:
            report.write_bytes(original_report)
    after = app_snapshot(repo)
    changed = sorted(path for path in before.keys() | after.keys()
                     if before.get(path) != after.get(path))
    if changed:
        raise RuntimeError("no-op codemod 改变了文件字节或文件集合：\n" + "\n".join(changed))
    print(f"幂等性通过：{len(before)} 个应用 Dart/manifest 文件字节不变；报告不参与比较。")


def annotation_text(logs: list[Path]) -> str:
    sections = []
    tails = []
    for log in logs:
        try:
            text = log.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            tails.append(f"{log.name}：无法读取日志（该步骤可能未执行）：{error}")
            continue
        text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
        lines = text.splitlines()

        def grab(pattern: str, limit: int) -> list[str]:
            return [line for line in lines if re.search(pattern, line, re.I)][:limit]

        # 优先保留所有日志中的错误，再追加尾部，避免 bootstrap 输出挤掉分析错误。
        sections += [f"[{log.name}] DART / ANALYZER / TEST ERRORS"]
        sections += grab(r"\.dart:\d+:\d+: (Error|Warning):|\berror\b|\[E\]|Some tests failed", 25) or ["未找到匹配行"]
        sections += ["GRADLE / FLUTTER"]
        sections += grab(r"FAILURE:|What went wrong|Execution failed|> Task .* FAILED|error:", 15) or ["未找到匹配行"]
        tails += [f"[{log.name}] TAIL", *lines[-40:]]
    return "\n".join([*sections, *tails])[:7500]


def escape_annotation(text: str, *, property_value: bool = False) -> str:
    text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    if property_value:
        text = text.replace(":", "%3A").replace(",", "%2C")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    idempotency = commands.add_parser("idempotency", help="再执行一次 codemod，断言应用和 manifest 字节不变")
    idempotency.add_argument("repo", type=Path)
    annotate = commands.add_parser("annotate", help="提取错误行和日志尾部，生成 GitHub annotation")
    annotate.add_argument("--title", default="构建失败")
    annotate.add_argument("logs", type=Path, nargs="+")
    args = parser.parse_args()
    if args.command == "idempotency":
        check_idempotency(args.repo)
    else:
        title = escape_annotation(args.title, property_value=True)
        message = escape_annotation(annotation_text(args.logs))
        print(f"::error title={title}::{message}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
