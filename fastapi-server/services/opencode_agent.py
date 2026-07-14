"""OpenCode sidecar integration for repair and Jira-decision advice.

This module intentionally keeps OpenCode as an external, sandboxable helper. It
returns advice/proposals; it does not create Jira issues and does not apply file
changes directly. Backend guardrails and human approval stay in FastAPI.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class OpenCodeResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    parsed: dict[str, Any] | None = None


class OpenCodeAgent:
    def __init__(
        self,
        command: Optional[str] = None,
        timeout: Optional[float] = None,
        workdir: Optional[Path] = None,
    ) -> None:
        self.command = command or os.getenv("OPENCODE_CMD", "opencode")
        self.timeout = timeout if timeout is not None else float(os.getenv("OPENCODE_TIMEOUT", "900"))
        self.workdir = workdir or Path(os.getenv("OPENCODE_WORKDIR", Path(__file__).resolve().parents[2]))

    def executable(self) -> str | None:
        return shutil.which(self.command)

    def is_configured(self) -> bool:
        return self.executable() is not None

    def status(self) -> dict[str, Any]:
        exe = self.executable()
        return {
            "configured": exe is not None,
            "command": self.command,
            "executable": exe,
            "timeout": self.timeout,
            "workdir": str(self.workdir),
        }

    def run(self, prompt: str, *, agent: str = "repair") -> OpenCodeResult:
        exe = self.executable()
        if not exe:
            raise RuntimeError(f"OpenCode executable not found: {self.command}")
        cmd = [exe, "run", "--format", "json", "--agent", agent, "--dir", str(self.workdir), prompt]
        proc = subprocess.run(
            cmd,
            cwd=str(self.workdir),
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
        )
        return OpenCodeResult(
            command=cmd,
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=_parse_last_json(proc.stdout),
        )


def _parse_last_json(text: str) -> dict[str, Any] | None:
    """Best-effort parser for JSON/JSONL output from agent CLIs."""
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def build_failure_advice_prompt(context: dict[str, Any], *, intent: str = "both") -> str:
    """Build a bounded instruction for OpenCode repair/Jira advice.

    Expected model output is JSON so FastAPI can display and audit it without
    trusting free-form text for actions.
    """
    target = context.get("target") or {}
    failures = context.get("failures") or []
    console_tail = context.get("console_tail") or ""
    feature_source = context.get("feature_source") or ""
    step_sources = context.get("step_sources") or {}
    step_excerpt = "\n\n".join(
        f"## {path}\n{source[:4000]}" for path, source in list(step_sources.items())[:4]
    )
    return f"""
You are an autonomous test-repair and Jira-triage sidecar for this Java Cucumber/Selenium project.

Intent: {intent}

Hard rules:
- Do not weaken assertions just to make tests pass.
- Do not propose changes outside test-core/src/test/**.
- Do not create Jira issues yourself. Only advise whether Jira should be created.
- Return a single JSON object only.

Required JSON schema:
{{
  "decision": "REPAIR" | "CREATE_JIRA" | "LINK_JIRA" | "NEEDS_HUMAN" | "NO_ACTION",
  "confidence": 0.0,
  "reasoning": "short reason",
  "repair": {{"file": "relative/path or null", "summary": "repair summary", "risk": "low|medium|high"}},
  "jira": {{"should_create": false, "summary": "", "description": "", "duplicate_hint": ""}},
  "next_steps": ["..."]
}}

Target failure:
{json.dumps(target, ensure_ascii=False, indent=2)}

All failures in run:
{json.dumps(failures, ensure_ascii=False, indent=2)[:6000]}

Console tail:
```text
{console_tail[-6000:]}
```

Feature source:
```gherkin
{feature_source[:6000]}
```

Related step/helper sources:
```java
{step_excerpt}
```
""".strip()
