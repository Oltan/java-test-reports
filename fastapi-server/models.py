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
    scenarios: List[ScenarioResult]