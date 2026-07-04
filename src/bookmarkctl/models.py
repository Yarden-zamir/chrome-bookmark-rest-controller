from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


DEFAULT_CLIENT_ID = "bookmarkctl"


class CommandStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class CommandCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    clientId: str = DEFAULT_CLIENT_ID
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "clientId", "action")
    @classmethod
    def non_empty_string(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("must be a non-empty string")
        return value


class CommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    result: Any = None
    error: str | None = None


class Command(BaseModel):
    id: str
    clientId: str = DEFAULT_CLIENT_ID
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)
    status: CommandStatus = CommandStatus.PENDING
    result: Any = None
    error: str | None = None
    createdAt: str
    claimedAt: str | None = None
    completedAt: str | None = None

    @classmethod
    def new(cls, command: CommandCreate) -> "Command":
        return cls(
            id=command.id or str(uuid4()),
            clientId=command.clientId,
            action=command.action,
            payload=command.payload,
            createdAt=now_iso(),
        )

    def for_extension(self) -> dict[str, Any]:
        return {"id": self.id, "action": self.action, "payload": self.payload}


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
