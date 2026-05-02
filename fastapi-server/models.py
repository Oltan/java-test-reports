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
    status: str = Field(pattern=r"^(passed|failed|skipped)$")
    timestamp: str
    errorMessage: Optional[str] = None


class ScenarioResult(BaseModel):
    id: str
    name: str
    status: str = Field(pattern=r"^(passed|failed|skipped)$")
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
