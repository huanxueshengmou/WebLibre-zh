#!/usr/bin/env python3
"""
Build i18n/zh.json: the English -> Chinese table the app ships.

Three sources, in strict priority order:

  1. glossary.json   hand-written, always wins. A few hundred entries cover the
                     words users actually see most, so their quality matters far
                     more than the engine used for the rest.
  2. cache (zh.json) already-translated strings, reused verbatim. Because this
                     file is committed, a CI run after an upstream update only
                     pays for the handful of strings that are genuinely new.
  3. machine translation
                     the long tail. Default engine is Argos Translate: pure
                     Python, fully offline, no API key, no account, MIT-ish
                     licensing - the simplest open-source option that works in
                     CI. An LLM backend is available when a key is present,
                     because it produces noticeably better prose.

Nothing is ever guessed silently. Every string that fails to translate is left
out of the table, which makes the app fall back to English - a visible,
harmless outcome - and is listed in the report so it can be added to the
glossary by hand.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Private-use characters wrapping a placeholder index. MT models copy these
# through untouched, whereas `{0}` is often "helpfully" rewritten.
PH_OPEN = "\ue000"
PH_CLOSE = "\ue001"

RE_PLACEHOLDER = re.compile(r"\{(\d+)\}")
RE_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

# Chinese uses full-width punctuation. Offline MT models happily emit
# "从你的设备?" instead, which reads as a foreign accent in an otherwise
# translated UI. These substitutions only fire when a CJK character is
# adjacent, so URLs, version numbers and decimals are left alone.
_PUNCT_AFTER_CJK = (("?", "？"), ("!", "！"), (";", "；"), (":", "："), (",", "，"))
_CJK_CLASS = r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"


def normalize_punctuation(text: str) -> str:
    """
    Convert half-width punctuation to full-width where Chinese requires it.

    Deliberately conservative: only touches `? ! ; : ,` next to a CJK
    character, and a sentence-final `.` that follows CJK. A decimal point or a
    version number never has CJK immediately before it, so `3.14` and `v1.2`
    are safe.
    """
    out = text
    for half, full in _PUNCT_AFTER_CJK:
        h = re.escape(half)
        out = re.sub(rf"(?<={_CJK_CLASS}){h}", full, out)
        out = re.sub(rf"{h}(?={_CJK_CLASS})", full, out)
    # Sentence-final period, including one followed by more text after a space.
    out = re.sub(rf"(?<={_CJK_CLASS})\.(?=\s|$)", "。", out)
    return out


# --------------------------------------------------------------------------
# placeholder protection
# --------------------------------------------------------------------------

def protect(text: str) -> tuple[str, list[str]]:
    """Replace {n} with opaque sentinels. Returns (masked, original tokens)."""
    tokens: list[str] = []

    def sub(m: re.Match) -> str:
        tokens.append(m.group(0))
        return f"{PH_OPEN}{len(tokens) - 1}{PH_CLOSE}"

    return RE_PLACEHOLDER.sub(sub, text), tokens


def restore(text: str, tokens: list[str]) -> str:
    def sub(m: re.Match) -> str:
        i = int(m.group(1))
        return tokens[i] if 0 <= i < len(tokens) else m.group(0)

    return re.sub(re.escape(PH_OPEN) + r"(\d+)" + re.escape(PH_CLOSE), sub, text)


def placeholders_ok(src: str, out: str) -> bool:
    return sorted(RE_PLACEHOLDER.findall(src)) == sorted(RE_PLACEHOLDER.findall(out))


# --------------------------------------------------------------------------
# engines
# --------------------------------------------------------------------------

class Engine:
    name = "none"

    def translate(self, text: str) -> str | None:
        raise NotImplementedError

    def close(self) -> None:
        pass


class NullEngine(Engine):
    """Glossary-only. Useful offline and for tests."""
    name = "none"

    def translate(self, text: str) -> str | None:
        return None


class ArgosEngine(Engine):
    """
    Argos Translate: offline neural MT, pip-installable, no credentials.

    This is the "simple open-source" answer - one dependency, no server, no
    key. The en->zh model is ~100 MB and is fetched once per CI run.
    """

    name = "argos"

    def __init__(self, from_code: str = "en", to_code: str = "zh"):
        import argostranslate.package as pkg
        import argostranslate.translate as translate

        self._translate = translate

        installed = {p.from_code + "->" + p.to_code
                     for p in pkg.get_installed_packages()}
        pair = f"{from_code}->{to_code}"
        if pair not in installed:
            print(f"[argos] installing {pair} model ...", flush=True)
            pkg.update_package_index()
            available = pkg.get_available_packages()
            match = next(
                (p for p in available
                 if p.from_code == from_code and p.to_code == to_code),
                None,
            )
            if match is None:
                raise RuntimeError(f"no Argos model for {pair}")
            pkg.install_from_path(match.download())

        self.from_code = from_code
        self.to_code = to_code

    def translate(self, text: str) -> str | None:
        try:
            return self._translate.translate(text, self.from_code, self.to_code)
        except Exception as e:  # noqa: BLE001 - engine failures must not kill the build
            print(f"[argos] error: {e}", file=sys.stderr)
            return None


class LlmEngine(Engine):
    """
    Optional OpenAI-compatible backend. Better prose than offline MT, but needs
    a key, so it is opt-in via environment variables:

        I18N_LLM_BASE_URL   default https://api.openai.com/v1
        I18N_LLM_API_KEY    required to enable
        I18N_LLM_MODEL      default gpt-4o-mini
    """

    name = "llm"

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def _chat(self, payload: dict) -> dict:
        import urllib.request

        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read().decode("utf-8"))

    def translate_many(self, texts: list[str]) -> list[str | None]:
        """Translate a batch in one request. Falls back to per-item on error."""
        system = (
            "You localise a privacy-focused Android browser from English to "
            "Simplified Chinese. Reply with a JSON array of strings, same "
            "length and order as the input. Rules: keep placeholders like {0} "
            "exactly as-is; do not translate product names (WebLibre, GeckoView, "
            "Tor, sing-box, UnifiedPush, DNS, HTTPS, Cookie); use the "
            "terminology of mainstream Chinese browsers; keep it short enough "
            "to fit a button or a list row; no explanations, JSON only."
        )
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(texts, ensure_ascii=False)},
            ],
        }
        try:
            data = self._chat(payload)
            content = data["choices"][0]["message"]["content"].strip()
            content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.M).strip()
            out = json.loads(content)
            if isinstance(out, list) and len(out) == len(texts):
                return [str(x) for x in out]
        except Exception as e:  # noqa: BLE001
            print(f"[llm] batch failed ({e}); falling back to single calls",
                  file=sys.stderr)
        return [self.translate(t) for t in texts]

    def translate(self, text: str) -> str | None:
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system",
                 "content": "Translate to Simplified Chinese. Keep {0}-style "
                            "placeholders. Output only the translation."},
                {"role": "user", "content": text},
            ],
        }
        try:
            data = self._chat(payload)
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:  # noqa: BLE001
            print(f"[llm] error: {e}", file=sys.stderr)
            return None


def pick_engine(choice: str) -> Engine:
    if choice == "none":
        return NullEngine()
    if choice == "argos":
        return ArgosEngine()
    if choice == "llm":
        key = os.environ.get("I18N_LLM_API_KEY")
        if not key:
            print("[llm] I18N_LLM_API_KEY not set; falling back to argos",
                  file=sys.stderr)
            return ArgosEngine()
        return LlmEngine(
            os.environ.get("I18N_LLM_BASE_URL", "https://api.openai.com/v1"),
            key,
            os.environ.get("I18N_LLM_MODEL", "gpt-4o-mini"),
        )
    if choice == "auto":
        if os.environ.get("I18N_LLM_API_KEY"):
            return pick_engine("llm")
        try:
            return ArgosEngine()
        except Exception as e:  # noqa: BLE001
            print(f"[auto] argos unavailable ({e}); glossary only", file=sys.stderr)
            return NullEngine()
    raise SystemExit(f"unknown engine: {choice}")


# --------------------------------------------------------------------------
# quality gate
# --------------------------------------------------------------------------

def acceptable(src: str, out: str | None) -> tuple[bool, str]:
    """Reject translations that are obviously broken."""
    if out is None:
        return False, "engine-failed"
    out = out.strip()
    if not out:
        return False, "empty"
    if out == src.strip():
        return False, "untranslated"
    if not RE_CJK.search(out):
        return False, "no-chinese"
    if not placeholders_ok(src, out):
        return False, "placeholder-mismatch"
    # A wildly longer string almost always means the model ran on.
    if len(out) > max(40, len(src) * 4):
        return False, "too-long"
    # Chinese is far denser than English - roughly 0.4-0.6 the character count -
    # so the floor has to be low. An earlier 0.15 cut off perfectly good short
    # translations like 'Bang Frequencies' -> 'Bang 频率'.
    if len(src) > 12 and len(out) < max(2, len(src) * 0.08):
        return False, "too-short"
    return True, "ok"


def translate_one(engine: Engine, src: str) -> tuple[str | None, str]:
    """
    Translate one string, defending its placeholders.

    Two strategies, because offline MT models differ in how they treat
    placeholders:

      A. Mask `{0}` behind private-use sentinels. Models that respect unknown
         characters leave them alone, and the braces cannot be "corrected".
      B. Translate the raw text with `{0}` in place. Many models pass it
         straight through, since it looks like a format specifier.

    Argos silently drops the sentinels from strategy A, which was costing ~100
    strings per run; strategy B recovers nearly all of them. Returns
    (translation, reason) with translation None when both strategies fail.
    """
    best_reason = "engine-failed"
    best: str | None = None

    masked, tokens = protect(src)
    raw = engine.translate(masked)
    if raw:
        cand = restore(raw, tokens)
        ok, why = acceptable(src, cand)
        if ok:
            return cand, "ok"
        best, best_reason = cand, why

    raw2 = engine.translate(src)
    if raw2:
        cand2 = raw2.strip()
        ok2, why2 = acceptable(src, cand2)
        if ok2:
            return cand2, "ok"
        if best is None:
            best, best_reason = cand2, why2

    return None, best_reason


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--manifest", default="i18n/strings.json")
    ap.add_argument("--cache", default="i18n/zh.json")
    ap.add_argument("--glossary", default=str(HERE / "glossary.json"))
    ap.add_argument("--engine", default="auto",
                    choices=["auto", "argos", "llm", "none"])
    ap.add_argument("--limit", type=int, default=0,
                    help="translate at most N new strings (for testing)")
    ap.add_argument("--refresh", action="store_true",
                    help="ignore the cache and retranslate everything")
    ap.add_argument("--min-coverage", type=float, default=50.0,
                    help="exit non-zero below this coverage percentage")
    ap.add_argument("--report", default="i18n/translation-report.json")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    man_path = repo / args.manifest
    cache_path = repo / args.cache

    if not man_path.exists():
        raise SystemExit(f"missing manifest {man_path} - run codemod.py first")

    manifest = json.loads(man_path.read_text(encoding="utf-8"))
    keys = sorted(manifest.keys())

    cache: dict[str, str] = {}
    if cache_path.exists() and not args.refresh:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
        cache.pop("_comment", None)

    glossary_raw = json.loads(Path(args.glossary).read_text(encoding="utf-8"))
    glossary = {k: v for k, v in glossary_raw.items() if not k.startswith("_")}

    print(f"keys in manifest : {len(keys)}")
    print(f"glossary entries : {len(glossary)}")
    print(f"cached           : {len(cache)}")

    table: dict[str, str] = {}
    failed: list[dict] = []
    stats = {"glossary": 0, "cache": 0, "translated": 0, "dropped": 0}

    # ---- 1. glossary wins over everything -------------------------------
    for k in keys:
        if k in glossary:
            table[k] = glossary[k]
            stats["glossary"] += 1

    # ---- 2. reuse the cache ---------------------------------------------
    todo: list[str] = []
    for k in keys:
        if k in table:
            continue
        if k in cache and acceptable(k, cache[k])[0]:
            table[k] = cache[k]
            stats["cache"] += 1
        else:
            todo.append(k)

    print(f"to translate     : {len(todo)}")
    if args.limit:
        todo = todo[: args.limit]

    # ---- 3. machine translation -----------------------------------------
    if todo:
        engine = pick_engine(args.engine)
        print(f"engine           : {engine.name}")
        started = time.time()

        try:
            if isinstance(engine, LlmEngine):
                batch = 40
                for i in range(0, len(todo), batch):
                    chunk = todo[i:i + batch]
                    masked = [protect(c)[0] for c in chunk]
                    results = engine.translate_many(masked)
                    for src, out in zip(chunk, results):
                        tokens = protect(src)[1]
                        cand = restore(out or "", tokens) if out else None
                        ok, why = acceptable(src, cand)
                        if ok:
                            table[src] = cand
                            stats["translated"] += 1
                            continue
                        # Batch results are sentinel-masked; retry this one on
                        # its own, which also tries the raw-text strategy.
                        cand2, why2 = translate_one(engine, src)
                        if cand2 is not None:
                            table[src] = cand2
                            stats["translated"] += 1
                        else:
                            failed.append({"key": src, "reason": why2,
                                           "got": (cand or "")[:120]})
                    done = min(i + batch, len(todo))
                    print(f"  [{done}/{len(todo)}] {time.time() - started:.0f}s",
                          flush=True)
            else:
                for n, src in enumerate(todo, 1):
                    cand, why = translate_one(engine, src)
                    if cand is not None:
                        table[src] = cand
                        stats["translated"] += 1
                    else:
                        failed.append({"key": src, "reason": why, "got": ""})
                    if n % 50 == 0 or n == len(todo):
                        print(f"  [{n}/{len(todo)}] {time.time() - started:.0f}s",
                              flush=True)
        finally:
            engine.close()

    # ---- 4. persist ------------------------------------------------------
    # Normalise punctuation once over the finished table. Doing it here rather
    # than at translation time means cached and glossary values get the same
    # treatment, and re-running is a no-op because full-width input is already
    # full-width.
    table = {k: normalize_punctuation(v) for k, v in table.items()}

    stats["dropped"] = len(failed)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    out = {"_comment": [
        "Generated by tools/i18n/translate.py - do not edit by hand unless you",
        "are fixing a specific translation, in which case prefer glossary.json",
        "so the fix survives a retranslation.",
    ]}
    out.update({k: table[k] for k in sorted(table)})
    cache_path.write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    rep = {
        "keys": len(keys),
        "translated_total": len(table),
        "coverage": round(len(table) / max(1, len(keys)) * 100, 1),
        "by_source": stats,
        "failed": failed,
    }
    (repo / args.report).write_text(
        json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")

    print()
    print(f"table entries    : {len(table)} / {len(keys)} "
          f"({rep['coverage']}%)")
    print(f"  from glossary  : {stats['glossary']}")
    print(f"  from cache     : {stats['cache']}")
    print(f"  newly machine  : {stats['translated']}")
    print(f"  dropped        : {stats['dropped']}")
    if failed:
        print()
        print("--- left as English (add to glossary.json to fix) ---")
        for f in failed[:20]:
            print(f"  [{f['reason']}] {f['key'][:80]!r}")
        if len(failed) > 20:
            print(f"  ... and {len(failed) - 20} more (see {args.report})")
    print()
    print(f"wrote {args.cache}")

    # Coverage below the floor means the pipeline is not really working. This
    # exits non-zero so the problem is visible, but the workflow treats it as a
    # warning rather than a failure: a partially translated app is still worth
    # building, and silently shipping English would be worse than either.
    if rep["coverage"] < args.min_coverage:
        print(f"WARNING: coverage {rep['coverage']}% is below the "
              f"{args.min_coverage}% floor", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
