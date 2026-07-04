from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .models import DEFAULT_CLIENT_ID, Command, CommandCreate, CommandResult
from .store import CommandStore


store = CommandStore()
app = FastAPI(title="bookmarkctl")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["content-type"],
)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/commands", status_code=201)
def create_command(command: CommandCreate) -> Command:
    return store.create(command)


@app.get("/commands")
def claim_commands(clientId: Annotated[str, Query()] = DEFAULT_CLIENT_ID) -> list[dict[str, object]]:
    return [command.for_extension() for command in store.claim_pending(clientId)]


@app.get("/commands/all")
def list_commands() -> list[Command]:
    return store.list_all()


@app.get("/commands/{command_id}")
def get_command(command_id: str) -> Command:
    command = store.get(command_id)
    if command is None:
        raise HTTPException(status_code=404, detail="Command not found")
    return command


@app.post("/commands/{command_id}/result")
def complete_command(command_id: str, result: CommandResult) -> Command:
    command = store.complete(command_id, result)
    if command is None:
        raise HTTPException(status_code=404, detail="Command not found")
    return command


@app.delete("/commands")
def clear_commands(completed_only: bool = False) -> dict[str, int]:
    return {"deleted": store.clear(completed_only=completed_only)}
