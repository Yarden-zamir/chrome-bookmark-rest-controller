# bookmarkctl

```bash
brew install Yarden-zamir/tap/bookmarkctl
```

A Manifest V3 Chrome extension controlled by a local FastAPI command queue and a Typer CLI.

Chrome extensions cannot host a REST API directly, so this project uses polling:

1. `bookmarkctl` starts or uses a local FastAPI server.
2. The CLI queues bookmark commands through REST.
3. The extension polls `http://127.0.0.1:8877/commands`.
4. The extension executes commands with `chrome.bookmarks`.
5. The extension posts results back to the server.
6. For one-shot CLI commands, `bookmarkctl` waits for the result and then stops the temporary server it started.

## Security

The API is intentionally unauthenticated for local automation.

Keep it bound to `127.0.0.1`. Binding to `0.0.0.0` lets anyone who can reach the port create, move, update, and delete your bookmarks.

## Install Dependencies

```bash
uv sync
```

## Load The Extension

1. Open `chrome://extensions`.
2. Enable `Developer mode`.
3. Click `Load unpacked`.
4. Select `extension` from this repo.

The popup defaults should work:

- API base URL: `http://127.0.0.1:8877`
- Client ID: `bookmarkctl`
- Poll interval: `5`
- Enabled: checked

If the server is dormant, extension polling may fail quietly. That is expected. Run a CLI command, and the CLI can bring up a temporary server for the extension to pick up.

## Common CLI Usage

Backup before bulk changes:

```bash
uv run bookmarkctl backup
```

Print the full bookmark tree:

```bash
uv run bookmarkctl tree
```

Search bookmarks:

```bash
uv run bookmarkctl search github
```

List a folder by ID or path:

```bash
uv run bookmarkctl ls "Other Bookmarks"
uv run bookmarkctl ls "Other Bookmarks/Dev Tools and Programming"
```

Find bookmark paths:

```bash
uv run bookmarkctl path data-app-design
uv run bookmarkctl path 302
```

Create a folder on the bookmarks bar:

```bash
uv run bookmarkctl mkdir "Dev Tools" --parent "Other Bookmarks"
```

Create a bookmark:

```bash
uv run bookmarkctl add "data-app-design" "https://github.com/qlik-trial/data-app-design" --parent 1
uv run bookmarkctl add "Example" "https://example.com" --parent "Other Bookmarks/Dev Tools"
```

Move or reorder a bookmark:

```bash
uv run bookmarkctl mv 123 "Other Bookmarks/Dev Tools" --index 0
```

Remove a bookmark:

```bash
uv run bookmarkctl rm 123
```

Remove a folder tree:

```bash
uv run bookmarkctl rm 123 --recursive --yes
```

Restore a backup under a new folder instead of overwriting your current tree:

```bash
uv run bookmarkctl restore bookmarks-backup-YYYYMMDD-HHMMSS.json --parent "Other Bookmarks"
```

Most list/search commands print human tables by default. Add `--json` for scripting.

## Server Modes

One-shot CLI commands automatically use an existing server if one is already running. If no server is running, the CLI starts a temporary uvicorn server, waits for the extension to complete the command, then shuts that temporary server down.

You can also run a persistent server manually:

```bash
uv run bookmarkctl server
```

Then run commands from another shell:

```bash
uv run bookmarkctl ls "Other Bookmarks"
```

## Raw REST API

Queue any raw command:

```bash
curl -X POST http://127.0.0.1:8877/commands \
  -H 'content-type: application/json' \
  -d '{"action":"tree","payload":{}}'
```

Check command status:

```bash
curl http://127.0.0.1:8877/commands/<command-id>
```

List command history:

```bash
curl http://127.0.0.1:8877/commands/all
```

## Supported Extension Actions

- `tree`
- `children`
- `get`
- `search`
- `create`
- `update`
- `move`
- `remove`
- `removeTree`

## Bookmark Root IDs

Chrome commonly uses:

- `0`: root
- `1`: bookmarks bar
- `2`: other bookmarks

Use `uv run bookmarkctl tree` to verify IDs in your profile.

## Development

```bash
uv run bookmarkctl --help
uvx ruff check
node --check extension/service-worker.js
node --check extension/popup.js
```
