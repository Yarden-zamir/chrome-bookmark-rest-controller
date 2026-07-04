from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .models import Command, CommandCreate, CommandResult, CommandStatus, now_iso


def default_state_path() -> Path:
    override = os.environ.get("BOOKMARKCTL_STATE")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "state" / "bookmarkctl" / "commands.json"


class CommandStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_state_path()
        self._lock = threading.Lock()
        self._commands: dict[str, Command] = {}
        self._load()

    def create(self, command_create: CommandCreate) -> Command:
        with self._lock:
            command = Command.new(command_create)
            self._commands[command.id] = command
            self._save_locked()
            return command

    def list_all(self) -> list[Command]:
        with self._lock:
            return sorted(self._commands.values(), key=lambda command: command.createdAt)

    def get(self, command_id: str) -> Command | None:
        with self._lock:
            return self._commands.get(command_id)

    def claim_pending(self, client_id: str) -> list[Command]:
        with self._lock:
            pending = [
                command
                for command in self._commands.values()
                if command.clientId == client_id and command.status == CommandStatus.PENDING
            ]
            for command in pending:
                command.status = CommandStatus.CLAIMED
                command.claimedAt = now_iso()
            self._save_locked()
            return pending

    def complete(self, command_id: str, result: CommandResult) -> Command | None:
        with self._lock:
            command = self._commands.get(command_id)
            if command is None:
                return None
            command.status = CommandStatus.SUCCEEDED if result.ok else CommandStatus.FAILED
            command.result = result.result
            command.error = result.error
            command.completedAt = now_iso()
            self._save_locked()
            return command

    def retry_claimed(self, older_than_seconds: int) -> int:
        with self._lock:
            count = 0
            for command in self._commands.values():
                if command.status == CommandStatus.CLAIMED and command.completedAt is None:
                    command.status = CommandStatus.PENDING
                    command.claimedAt = None
                    count += 1
            if count:
                self._save_locked()
            return count

    def clear(self, completed_only: bool = False) -> int:
        with self._lock:
            if completed_only:
                removable = {
                    command_id
                    for command_id, command in self._commands.items()
                    if command.status in {CommandStatus.SUCCEEDED, CommandStatus.FAILED}
                }
                for command_id in removable:
                    del self._commands[command_id]
                count = len(removable)
            else:
                count = len(self._commands)
                self._commands.clear()
            self._save_locked()
            return count

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(f"Command state must be a list: {self.path}")
        self._commands = {command.id: command for command in (Command.model_validate(item) for item in raw)}

    def _save_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        payload = [command.model_dump(mode="json") for command in self.list_all_unlocked()]
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_path.replace(self.path)

    def list_all_unlocked(self) -> list[Command]:
        return sorted(self._commands.values(), key=lambda command: command.createdAt)
