from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict, Field


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


class TestSuite(BaseModel):
    id: str
    name: str
    description: str
    tests: List[str]
    tags: List[str] = []


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    resource_id: int | None
    selected_tests: List[str]
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
