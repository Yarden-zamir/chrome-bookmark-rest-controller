from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

import httpx
import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from .models import CommandStatus

BASE_URL = "http://127.0.0.1:8877"
HOST = "127.0.0.1"
PORT = 8877
TIMEOUT = 45.0

app = typer.Typer(help="Manage Chrome bookmarks through the local extension command queue.")
console = Console()


@app.command()
def server(host: str = HOST, port: int = PORT) -> None:
    uvicorn.run("bookmarkctl.api:app", host=host, port=port, log_level="info")


@app.command()
def tree(timeout: float = TIMEOUT, base_url: str = BASE_URL) -> None:
    print_json(fetch_tree(timeout, base_url))


@app.command("ls")
def ls(folder: Annotated[str, typer.Argument()] = "0", json_output: Annotated[bool, typer.Option("--json")] = False, timeout: float = TIMEOUT, base_url: str = BASE_URL) -> None:
    node = resolve(fetch_tree(timeout, base_url), folder, folder=True)
    rows = node.get("children") or []
    print_json(rows) if json_output else print_rows(rows)


@app.command()
def search(query: str, json_output: Annotated[bool, typer.Option("--json")] = False, timeout: float = TIMEOUT, base_url: str = BASE_URL) -> None:
    rows = run("search", {"query": query}, timeout=timeout, base_url=base_url).get("result")
    if not isinstance(rows, list):
        raise RuntimeError("Search result was not a list")
    print_json(rows) if json_output else print_rows(rows)


@app.command()
def path(target: str, json_output: Annotated[bool, typer.Option("--json")] = False, timeout: float = TIMEOUT, base_url: str = BASE_URL) -> None:
    matches = find(fetch_tree(timeout, base_url), target)
    print_json(matches) if json_output else print_paths(matches)


@app.command()
def backup(output: Path | None = None, timeout: float = TIMEOUT, base_url: str = BASE_URL) -> None:
    target = output or Path(f"bookmarks-backup-{time.strftime('%Y%m%d-%H%M%S')}.json")
    target.write_text(json.dumps(fetch_tree(timeout, base_url), indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"Wrote backup: [bold]{target}[/]")


@app.command()
def restore(backup_file: Path, parent: str = "Other Bookmarks", title: str | None = None, timeout: float = TIMEOUT, base_url: str = BASE_URL) -> None:
    nodes = json.loads(backup_file.read_text(encoding="utf-8"))
    if not isinstance(nodes, list):
        raise typer.BadParameter("Backup file must contain a tree list")
    parent_id = resolve_id(fetch_tree(timeout, base_url), parent, folder=True)
    root_title = title or f"Restored {time.strftime('%Y-%m-%d %H:%M:%S')}"
    result = run("create", {"parentId": parent_id, "title": root_title}, timeout=timeout, base_url=base_url)["result"]
    console.print(f"Restored [bold]{restore_children(nodes, str(result['id']), timeout, base_url)}[/] item(s).")
@app.command()
def add(title: str, url: str, parent: str = "1", timeout: float = TIMEOUT, base_url: str = BASE_URL) -> None:
    parent_id = resolve_id(fetch_tree(timeout, base_url), parent, folder=True)
    print_json(run("create", {"parentId": parent_id, "title": title, "url": url}, timeout=timeout, base_url=base_url)["result"])
@app.command("mkdir")
def mkdir(title: str, parent: str = "1", timeout: float = TIMEOUT, base_url: str = BASE_URL) -> None:
    parent_id = resolve_id(fetch_tree(timeout, base_url), parent, folder=True)
    print_json(run("create", {"parentId": parent_id, "title": title}, timeout=timeout, base_url=base_url)["result"])
@app.command("mv")
def mv(target: str, parent: Annotated[str | None, typer.Argument()] = None, index: int | None = None, timeout: float = TIMEOUT, base_url: str = BASE_URL) -> None:
    nodes = fetch_tree(timeout, base_url)
    dest = {"parentId": resolve_id(nodes, parent, folder=True)} if parent else {}
    if index is not None:
        dest["index"] = index
    if not dest:
        raise typer.BadParameter("Provide parent or index")
    print_json(run("move", {"id": resolve_id(nodes, target), "destination": dest}, timeout=timeout, base_url=base_url)["result"])
@app.command("rm")
def rm(target: str, recursive: Annotated[bool, typer.Option("-r", "--recursive")] = False, yes: bool = False, timeout: float = TIMEOUT, base_url: str = BASE_URL) -> None:
    if recursive and not yes:
        raise typer.BadParameter("Pass --yes for recursive removal")
    nodes = fetch_tree(timeout, base_url)
    print_json(run("removeTree" if recursive else "remove", {"id": resolve_id(nodes, target, folder=recursive)}, timeout=timeout, base_url=base_url)["result"])
def run(action: str, payload: dict[str, Any], *, wait: bool = True, timeout: float = TIMEOUT, base_url: str = BASE_URL) -> dict[str, Any]:
    with server_context(base_url) as active:
        response = httpx.post(f"{active}/commands", json={"action": action, "payload": payload}, timeout=10)
        response.raise_for_status()
        command = response.json()
        if not wait:
            return command
        return wait_command(active, command["id"], timeout)
def fetch_tree(timeout: float, base_url: str) -> list[dict[str, Any]]:
    result = run("tree", {}, timeout=timeout, base_url=base_url).get("result")
    if not isinstance(result, list):
        raise RuntimeError("Bookmark tree result was not a list")
    return result
@contextmanager
def server_context(base_url: str) -> Iterator[str]:
    active = base_url.rstrip("/")
    if ready(active):
        yield active
        return
    parsed = urlparse(active)
    host, port = parsed.hostname or HOST, parsed.port or PORT
    if host not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("Temporary server startup is only supported for localhost")
    with tempfile.TemporaryDirectory(prefix="bookmarkctl-") as temp_dir:
        env = os.environ.copy()
        env.setdefault("BOOKMARKCTL_STATE", str(Path(temp_dir) / "commands.json"))
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "bookmarkctl.api:app", "--host", host, "--port", str(port), "--log-level", "warning"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            wait_server(active, process)
            yield active
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
def ready(base_url: str) -> bool:
    try:
        response = httpx.get(f"{base_url}/health", timeout=1)
        return response.status_code == 200 and response.json().get("ok") is True
    except (httpx.HTTPError, ValueError):
        return False


def wait_server(base_url: str, process: subprocess.Popen[bytes]) -> None:
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("Temporary bookmark server exited before it became ready")
        if ready(base_url):
            return
        time.sleep(0.1)
    raise TimeoutError("Timed out waiting for temporary bookmark server")


def wait_command(base_url: str, command_id: str, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = httpx.get(f"{base_url}/commands/{command_id}", timeout=10)
        response.raise_for_status()
        command = response.json()
        if command.get("status") == CommandStatus.SUCCEEDED:
            return command
        if command.get("status") == CommandStatus.FAILED:
            raise RuntimeError(command.get("error") or "Bookmark command failed")
        time.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for command {command_id}. Is the extension enabled?")


def find(nodes: list[dict[str, Any]], target: str) -> list[dict[str, Any]]:
    exact: list[dict[str, Any]] = []
    fuzzy: list[dict[str, Any]] = []
    def walk(node: dict[str, Any], path: str) -> None:
        title = str(node.get("title") or "<root>")
        current = f"{path}/{title}".strip("/") if title != "<root>" else path
        match = {"node": node, "path": current or "<root>"}
        if target == str(node.get("id", "")) or norm(current) == norm(target):
            exact.append(match)
        elif not target.isdigit() and target.lower() in f"{current} {title} {node.get('url', '')}".lower():
            fuzzy.append(match)
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child, current)
    for node in nodes:
        walk(node, "")
    return exact or fuzzy


def resolve(nodes: list[dict[str, Any]], target: str, *, folder: bool = False) -> dict[str, Any]:
    matches = [item for item in find(nodes, target) if not folder or "children" in item["node"]]
    if len(matches) == 1:
        return matches[0]["node"]
    if not matches:
        raise typer.BadParameter(f"Could not find {'folder' if folder else 'bookmark/folder'}: {target}")
    raise typer.BadParameter(f"Ambiguous target '{target}'. Use an ID or exact path.")


def resolve_id(nodes: list[dict[str, Any]], target: str, *, folder: bool = False) -> str:
    return str(resolve(nodes, target, folder=folder).get("id"))


def restore_children(nodes: list[dict[str, Any]], parent_id: str, timeout: float, base_url: str) -> int:
    return sum(restore_node(child, parent_id, timeout, base_url) for node in nodes for child in node.get("children", []))


def restore_node(node: dict[str, Any], parent_id: str, timeout: float, base_url: str) -> int:
    if node.get("url"):
        run("create", {"parentId": parent_id, "title": node.get("title") or node["url"], "url": node["url"]}, timeout=timeout, base_url=base_url)
        return 1
    result = run("create", {"parentId": parent_id, "title": node.get("title") or "Untitled Folder"}, timeout=timeout, base_url=base_url)["result"]
    return 1 + sum(restore_node(child, str(result["id"]), timeout, base_url) for child in node.get("children", []))


def print_rows(rows: list[dict[str, Any]]) -> None:
    table = Table()
    for column in ["ID", "Type", "Title", "URL/Children"]:
        table.add_column(column)
    for row in rows:
        is_folder = "children" in row
        info = str(len(row["children"])) if is_folder and isinstance(row.get("children"), list) else str(row.get("url") or "")
        table.add_row(str(row.get("id", "")), "folder" if is_folder else "bookmark", str(row.get("title") or ""), info)
    console.print(table)


def print_paths(matches: list[dict[str, Any]]) -> None:
    table = Table()
    for column in ["ID", "Type", "Path", "URL"]:
        table.add_column(column)
    for match in matches:
        node = match["node"]
        table.add_row(str(node.get("id", "")), "folder" if "children" in node else "bookmark", match["path"], str(node.get("url", "")))
    console.print(table)


def norm(value: str) -> str:
    return "/".join(part.strip() for part in value.replace(" / ", "/").split("/") if part.strip())


def print_json(value: Any) -> None:
    console.print_json(json.dumps(value, ensure_ascii=False))
