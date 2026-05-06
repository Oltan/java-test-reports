from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class StepResult(BaseModel):
    name: str
    status: str
    errorMessage: Optional[str] = None


class Attachment(BaseModel):
    name: str
    type: str = Field(pattern=r"^(image/png|video/mp4|text/plain)$")
    path: str


class AttemptResult(BaseModel):
    status: str = Field(pattern=r"^(passed|failed|skipped|broken)$")
    timestamp: str
    errorMessage: Optional[str] = None


class ScenarioResult(BaseModel):
    id: str
    name: str
    status: str = Field(pattern=r"^(passed|failed|skipped|broken)$")
    duration: str
    doorsAbsNumber: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    steps: List[StepResult] = Field(default_factory=list)
    attachments: List[Attachment] = Field(default_factory=list)
    attempts: List[AttemptResult] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)


class RunManifest(BaseModel):
    runId: str
    timestamp: datetime
    totalScenarios: int
    passed: int
    failed: int
    skipped: int
    duration: str
    version: Optional[str] = None
    environment: Optional[str] = None
    scenarios: List[ScenarioResult]


class PublicScenario(BaseModel):
    name: str
    status: str


class PublicReportSnapshot(BaseModel):
    run_summary: dict
    scenario_list: List[PublicScenario]
    generated_timestamp: str
    total_passed: int
    total_failed: int
    total_skipped: int

    @classmethod
    def from_internal(cls, internal_report: dict) -> "PublicReportSnapshot":
        from datetime import datetime
        scenarios_internal = internal_report.get("scenarios", [])
        scenario_list = [
            {"name": s.get("name", ""), "status": s.get("status", "")}
            for s in scenarios_internal
        ]
        ts_val = internal_report.get("generated_timestamp")
        if isinstance(ts_val, datetime):
            ts_str = ts_val.strftime("%Y-%m-%dT%H:%M:%SZ")
        elif isinstance(ts_val, str):
            ts_str = ts_val
        else:
            ts_str = ""
        return cls(
            run_summary={
                "total_scenarios": internal_report.get("totalScenarios", 0),
                "passed": internal_report.get("passed", 0),
                "failed": internal_report.get("failed", 0),
                "skipped": internal_report.get("skipped", 0),
            },
            scenario_list=[PublicScenario(**s) for s in scenario_list],
            generated_timestamp=ts_str,
            total_passed=internal_report.get("passed", 0),
            total_failed=internal_report.get("failed", 0),
            total_skipped=internal_report.get("skipped", 0),
        )


class TestRunOptions(BaseModel):
    tags: str = Field(
        default="@smoke",
        pattern=r"^@[\w,\-]+$",
        description="Cucumber tag filter",
    )
    retry_count: int = Field(default=0, ge=0, le=10)
    browser: str = Field(default="chrome", pattern=r"^(chrome|firefox|edge)$")
    parallel: int = Field(default=1, ge=1, le=5, description="Number of parallel test executions")
    environment: str = Field(default="staging", pattern=r"^(staging|prod|dev)$")
    notify_email: Optional[str] = None
    version: Optional[str] = None
    visibility: str = Field(default="internal", pattern=r"^(internal|public)$")
