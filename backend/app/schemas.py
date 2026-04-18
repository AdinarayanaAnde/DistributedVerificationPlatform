
from datetime import datetime
from typing import List
from pydantic import BaseModel, ConfigDict, Field

class ResourceCreate(BaseModel):
    name: str
    description: str | None = None


class ClientCreate(BaseModel):
    name: str = Field(..., description="Client display name")
    email: str | None = None
    webhook_url: str | None = None


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_key: str
    name: str
    email: str | None
    webhook_url: str | None
    created_at: datetime


class ResourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    active: bool


class TestItem(BaseModel):
    nodeid: str
    path: str
    function: str


class RunCreate(BaseModel):
    client_key: str
    selected_tests: List[str]
    resource_name: str | None = None
    cli_command: str | None = None
    suite_ids: List[str] | None = None
    setup_config_id: int | None = None
    teardown_config_id: int | None = None


class TestSuite(BaseModel):
    id: str
    name: str
    description: str
    tests: List[str]
    tags: List[str] = []
    source: str = "auto"  # auto, custom, marker
    estimated_duration: float | None = None
    last_run: dict | None = None


class CustomSuiteCreate(BaseModel):
    name: str
    description: str = ""
    tests: List[str]
    tags: List[str] = []


class CustomSuiteUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    tests: List[str] | None = None
    tags: List[str] | None = None


class CustomSuiteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    tests: List[str]
    tags: List[str]
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class SetupStepCreate(BaseModel):
    name: str
    step_type: str = "command"
    command: str
    timeout: int = 300
    on_failure: str = "fail"
    env_vars: dict | None = None


class SetupStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    step_type: str
    command: str
    timeout: int
    order: int
    on_failure: str
    env_vars: dict | None


class SetupConfigCreate(BaseModel):
    name: str
    description: str = ""
    steps: List[SetupStepCreate]


class SetupConfigUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: List[SetupStepCreate] | None = None


class SetupConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    steps: List[SetupStepOut]
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class TeardownStepCreate(BaseModel):
    name: str
    step_type: str = "command"
    command: str
    timeout: int = 300
    on_failure: str = "continue"
    env_vars: dict | None = None


class TeardownStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    step_type: str
    command: str
    timeout: int
    order: int
    on_failure: str
    env_vars: dict | None


class TeardownConfigCreate(BaseModel):
    name: str
    description: str = ""
    steps: List[TeardownStepCreate]


class TeardownConfigUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: List[TeardownStepCreate] | None = None


class TeardownConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    steps: List[TeardownStepOut]
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_name: str | None = None
    client_id: int
    resource_id: int | None
    selected_tests: List[str]
    setup_config_id: int | None = None
    setup_status: str | None = None
    teardown_config_id: int | None = None
    teardown_status: str | None = None
    status: str
    note: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class LogEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    level: str
    source: str
    message: str


class QueueEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    resource_id: int
    run_id: int
    client_id: int
    position: int
    status: str
    requested_at: datetime
