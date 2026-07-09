"""LLM-backed test repair (rulebook L2 infrastructure).

Flow: a failed run's context (failing scenario, error message, console log
tail, feature file and matching step-definition sources) is collected, sent to
an OpenAI-compatible chat-completions endpoint, and the model returns a
structured fix proposal. The proposal may only target files under
``test-core/src/test/`` — production and server code are out of bounds
(docs/OTOMASYON_KURALLARI.md §4).

Configuration (env):
  OPENAI_BASE_URL  chat-completions root, default https://api.openai.com/v1
                   (any OpenAI-compatible gateway works)
  OPENAI_API_KEY   bearer token; repair endpoints return 503 when unset
  OPENAI_MODEL     model name, default gpt-4o-mini
  OPENAI_TIMEOUT   request timeout in seconds, default 120
"""
import json
import os
import re
from pathlib import Path
from typing import Any, Optional

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_ROOT = REPO_ROOT / "test-core" / "src" / "test"
STEPS_DIR = ALLOWED_ROOT / "java"
CONSOLE_TAIL_LINES = 120
MAX_SOURCE_CHARS = 20_000


class OpenAIClient:
    """Minimal OpenAI-compatible chat-completions client (httpx, no SDK dep)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.api_key = api_key if api_key is not None else os.getenv("OPENAI_API_KEY", "")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.timeout = timeout if timeout is not None else float(os.getenv("OPENAI_TIMEOUT", "120"))

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def chat(self, messages: list[dict[str, str]]) -> str:
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "messages": messages, "temperature": 0},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


def collect_context(conn, run_id: str, manifests_dir: Path, scenario_uid: Optional[str] = None) -> dict[str, Any]:
    """Gather everything the model needs about a failed run.

    Returns {"failures": [...], "target": {...}|None, "console_tail": str,
    "feature_source": str, "step_sources": {path: content}}.
    """
    rows = conn.execute(
        """
        SELECT sr.scenario_uid, sr.name_at_run, sr.error_message,
               COALESCE(sr.doors_number_at_run, sd.doors_number) AS doors_number,
               sd.current_feature_file, sd.current_feature_line
        FROM scenario_results sr
        LEFT JOIN scenario_definitions sd ON sr.scenario_uid = sd.scenario_uid
        WHERE sr.run_id = ? AND sr.status IN ('FAILED', 'BROKEN')
        """,
        [run_id],
    ).fetchall()
    failures = [
        {
            "scenario_uid": r[0],
            "name": r[1],
            "error_message": r[2],
            "doors_number": r[3],
            "feature_file": r[4],
            "feature_line": r[5],
        }
        for r in rows
    ]

    target = None
    if scenario_uid:
        target = next((f for f in failures if f["scenario_uid"] == scenario_uid), None)
    elif failures:
        target = failures[0]

    console_tail = ""
    log_path = manifests_dir / run_id / "console.log"
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        console_tail = "\n".join(lines[-CONSOLE_TAIL_LINES:])

    feature_source = ""
    step_sources: dict[str, str] = {}
    if target and target["feature_file"]:
        feature_source = _read_feature(target["feature_file"])
        step_sources = _matching_step_sources(feature_source)

    return {
        "run_id": run_id,
        "failures": failures,
        "target": target,
        "console_tail": console_tail,
        "feature_source": feature_source,
        "step_sources": step_sources,
    }


def _read_feature(feature_file: str) -> str:
    """Resolve the feature path Allure recorded (absolute or classpath-relative)."""
    candidates = [
        Path(feature_file),
        ALLOWED_ROOT / "resources" / feature_file,
        ALLOWED_ROOT / "resources" / "features" / Path(feature_file).name,
    ]
    for path in candidates:
        if path.is_file():
            return path.read_text(encoding="utf-8", errors="replace")
    return ""


def _matching_step_sources(feature_source: str) -> dict[str, str]:
    """Step-definition java files that implement steps of the given feature.

    A file matches when it contains a significant word (>=4 chars) from any
    step line; if nothing matches, every step file is returned (bounded).
    """
    step_words = set()
    for line in feature_source.splitlines():
        text = line.strip()
        if text.split(" ", 1)[0] in ("Given", "When", "Then", "And", "But"):
            step_words.update(w.lower() for w in re.findall(r"[A-Za-z]{4,}", text))

    # only actual cucumber step-definition files, not hooks/runners/utilities
    step_files = []
    if STEPS_DIR.is_dir():
        for path in sorted(STEPS_DIR.rglob("*.java")):
            content = path.read_text(encoding="utf-8", errors="replace")
            if "io.cucumber.java" in content:
                step_files.append((path, content))

    matched: dict[str, str] = {}
    total = 0
    for path, content in step_files:
        if step_words and not any(w in content.lower() for w in step_words):
            continue
        rel = str(path.relative_to(REPO_ROOT))
        matched[rel] = content[:MAX_SOURCE_CHARS]
        total += len(matched[rel])
        if total > MAX_SOURCE_CHARS:
            break
    if not matched:
        for path, content in step_files[:5]:
            matched[str(path.relative_to(REPO_ROOT))] = content[:MAX_SOURCE_CHARS]
    return matched


SYSTEM_PROMPT = (
    "You are a test-automation repair agent for a Java Cucumber project. "
    "You receive a failing scenario, its error, the console log and the relevant sources. "
    "Propose a fix by rewriting exactly ONE file. Constraints: "
    "(1) you may only modify files under test-core/src/test/ (test code, step definitions, feature files); "
    "(2) never weaken an assertion just to make it pass unless the expected value is clearly a test-data mistake; "
    "(3) respond with ONLY a JSON object, no markdown fences, in the form "
    '{"file": "<path relative to repo root>", "new_content": "<full new file content>", '
    '"explanation": "<one short sentence>"}.'
)


def build_messages(context: dict[str, Any]) -> list[dict[str, str]]:
    target = context["target"] or {}
    sources = "\n\n".join(
        f"--- {path} ---\n{content}" for path, content in context["step_sources"].items()
    )
    user = (
        f"Run: {context['run_id']}\n"
        f"Failing scenario: {target.get('name')}\n"
        f"DOORS: {target.get('doors_number')}\n"
        f"Error message:\n{target.get('error_message') or 'N/A'}\n\n"
        f"Feature file ({target.get('feature_file')}):\n{context['feature_source']}\n\n"
        f"Step definition sources:\n{sources}\n\n"
        f"Console log tail:\n{context['console_tail']}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def parse_proposal(raw: str) -> dict[str, str]:
    """Parse the model reply into {file, new_content, explanation}; tolerant of fences."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text.strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM yanıtı JSON değil: {exc}") from exc
    missing = {"file", "new_content"} - set(data)
    if missing:
        raise ValueError(f"LLM yanıtında eksik alanlar: {sorted(missing)}")
    return {
        "file": str(data["file"]),
        "new_content": str(data["new_content"]),
        "explanation": str(data.get("explanation", "")),
    }


def validate_target(file: str) -> Path:
    """Only existing files under test-core/src/test/ may be patched."""
    path = (REPO_ROOT / file).resolve()
    try:
        path.relative_to(ALLOWED_ROOT.resolve())
    except ValueError:
        raise ValueError(
            f"'{file}' test-core/src/test/ altında değil — onarım yalnız test koduna uygulanabilir"
        )
    if not path.is_file():
        raise ValueError(f"'{file}' mevcut bir dosya değil (yeni dosya oluşturma L2 kapsamı dışında)")
    return path


def apply_proposal(proposal: dict[str, str]) -> str:
    path = validate_target(proposal["file"])
    path.write_text(proposal["new_content"], encoding="utf-8")
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:  # ALLOWED_ROOT outside the repo (test sandboxes)
        return str(path)
