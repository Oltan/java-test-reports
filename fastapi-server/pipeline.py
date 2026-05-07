import asyncio
import os
import shlex
import shutil
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Awaitable, Callable

from db import get_connection, init_schema


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class StageSkipped(Exception):
    """Raised when a stage is intentionally skipped because it is not configured."""


StageCallable = Callable[[], Awaitable[None]]

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent


class PipelineRunner:
    def __init__(self, run_id: str, db_path: str = "reports.duckdb"):
        self.run_id = run_id
        self.db_path = db_path

    async def run_stage(self, name: str, critical: bool, fn: StageCallable):
        """Run single stage. critical=False means error doesn't stop pipeline."""
        conn = get_connection()
        try:
            init_schema(conn)
            self._ensure_run(conn)
            self._update_stage(conn, name, StageStatus.RUNNING)
            await fn()
            self._update_stage(conn, name, StageStatus.SUCCESS)
        except StageSkipped as exc:
            self._update_stage(conn, name, StageStatus.SKIPPED, str(exc))
        except Exception as exc:
            self._update_stage(conn, name, StageStatus.FAILED, str(exc))
            if critical:
                raise
        finally:
            conn.close()

    def mark_skipped(self, name: str, reason: str):
        conn = get_connection()
        try:
            init_schema(conn)
            self._ensure_run(conn)
            self._update_stage(conn, name, StageStatus.SKIPPED, reason)
        finally:
            conn.close()

    def _ensure_run(self, conn):
        conn.execute(
            """
            INSERT INTO runs (id, version, environment, started_at)
            VALUES (?, ?, ?, current_timestamp)
            ON CONFLICT (id) DO NOTHING
            """,
            [
                self.run_id,
                os.getenv("PIPELINE_VERSION", "pipeline"),
                os.getenv("PIPELINE_ENVIRONMENT", os.getenv("ENVIRONMENT", "local")),
            ],
        )

    def _update_stage(self, conn, stage: str, status: StageStatus, error: str | None = None):
        now = datetime.utcnow()
        row = conn.execute(
            "SELECT started_at FROM pipeline_status WHERE run_id=? AND stage=?",
            [self.run_id, stage],
        ).fetchone()
        started_at = row[0] if row and row[0] is not None else now
        finished_at = None if status == StageStatus.RUNNING else now
        if row:
            conn.execute(
                """
                UPDATE pipeline_status
                SET status=?, started_at=?, finished_at=?, error_message=?
                WHERE run_id=? AND stage=?
                """,
                [status.value, started_at, finished_at, error, self.run_id, stage],
            )
        else:
            conn.execute(
                """
                INSERT INTO pipeline_status (run_id, stage, status, started_at, finished_at, error_message)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [self.run_id, stage, status.value, started_at, finished_at, error],
            )

    async def run_maven_tests(self):
        command = os.getenv("PIPELINE_MAVEN_COMMAND")
        if command:
            await self._run_shell_command(command)
            return

        mvn = os.getenv("MAVEN_CMD") or self._find_maven()
        module = os.getenv("MAVEN_MODULE", "test-core")
        await self._run_exec_command([mvn, "-pl", module, "test"])

    @staticmethod
    def _find_maven() -> str:
        bundled = Path("/home/ol_ta/tools/apache-maven-3.9.9/bin/mvn")
        if bundled.exists():
            return str(bundled)
        return shutil.which("mvn.cmd") or shutil.which("mvn") or "mvn"

    async def write_manifest(self):
        command = os.getenv("PIPELINE_MANIFEST_COMMAND")
        if command:
            await self._run_shell_command(command)

    async def generate_allure(self):
        command = os.getenv("PIPELINE_ALLURE_COMMAND")
        if command:
            await self._run_shell_command(command)
            return

        results_dir = Path(
            os.getenv("ALLURE_RESULTS_DIR", str(PROJECT_ROOT / "test-core" / "target" / "allure-results"))
        )
        report_dir = Path(
            os.getenv("ALLURE_REPORT_DIR", str(PROJECT_ROOT / "test-core" / "target" / "allure-report"))
        )
        if not results_dir.exists() or not any(results_dir.iterdir()):
            raise StageSkipped(f"Allure results not found: {results_dir}")

        allure_bin = os.getenv("ALLURE_BIN", "allure")
        await self._run_exec_command([allure_bin, "generate", "--clean", str(results_dir), "-o", str(report_dir)])

    async def create_jira_bugs(self):
        command = os.getenv("PIPELINE_JIRA_COMMAND")
        if not command:
            raise StageSkipped("PIPELINE_JIRA_COMMAND is not configured")
        await self._run_shell_command(command)

    async def run_doors_dxl(self):
        command = os.getenv("PIPELINE_DOORS_COMMAND")
        if not command:
            raise StageSkipped("PIPELINE_DOORS_COMMAND is not configured")
        await self._run_shell_command(command)

    async def send_email(self):
        command = os.getenv("PIPELINE_EMAIL_COMMAND")
        if not command:
            raise StageSkipped("PIPELINE_EMAIL_COMMAND is not configured")
        await self._run_shell_command(command)

    async def _run_shell_command(self, command: str):
        await self._run_exec_command(shlex.split(command))

    async def _run_exec_command(self, command: list[str]):
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(PROJECT_ROOT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            message = stderr.decode(errors="replace").strip() or stdout.decode(errors="replace").strip()
            raise RuntimeError(message or f"Command failed with exit code {process.returncode}: {command[0]}")


async def execute_pipeline(run_id: str):
    runner = PipelineRunner(run_id)
    stages: list[tuple[str, bool, StageCallable]] = [
        ("maven_test", False, runner.run_maven_tests),
        ("manifest", True, runner.write_manifest),
        ("allure", False, runner.generate_allure),
        ("jira", False, runner.create_jira_bugs),
        ("doors", False, runner.run_doors_dxl),
        ("email", True, runner.send_email),
    ]
    for index, (name, critical, fn) in enumerate(stages):
        try:
            await runner.run_stage(name, critical, fn)
        except Exception:
            reason = f"Skipped after critical stage failed: {name}"
            for skipped_name, _, _ in stages[index + 1 :]:
                runner.mark_skipped(skipped_name, reason)
            break
