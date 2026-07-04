const DEFAULT_SETTINGS = {
  apiBaseUrl: "http://127.0.0.1:8877",
  clientId: "bookmarkctl",
  enabled: true,
  pollIntervalSeconds: 5,
};

const COMMAND_ALARM = "poll-bookmark-commands";

chrome.runtime.onInstalled.addListener(async () => {
  const existing = await chrome.storage.local.get(Object.keys(DEFAULT_SETTINGS));
  await chrome.storage.local.set({ ...DEFAULT_SETTINGS, ...withoutUndefined(existing) });
  await schedulePolling();
});

chrome.runtime.onStartup.addListener(schedulePolling);

chrome.storage.onChanged.addListener((changes, areaName) => {
  if (areaName !== "local") {
    return;
  }

  if (changes.enabled || changes.pollIntervalSeconds) {
    void schedulePolling();
  }
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === COMMAND_ALARM) {
    void pollCommands();
  }
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "poll-now") {
    return false;
  }

  pollCommands()
    .then((result) => sendResponse({ ok: true, result }))
    .catch((error) => sendResponse({ ok: false, error: error.message }));
  return true;
});

async function schedulePolling() {
  const settings = await getSettings();
  await chrome.alarms.clear(COMMAND_ALARM);

  if (!settings.enabled) {
    return;
  }

  const interval = Math.max(1, Number(settings.pollIntervalSeconds) || DEFAULT_SETTINGS.pollIntervalSeconds);
  await chrome.alarms.create(COMMAND_ALARM, { periodInMinutes: interval / 60 });
  await pollCommands();
}

async function pollCommands() {
  const settings = await getSettings();
  if (!settings.enabled) {
    return { processed: 0, skipped: "disabled" };
  }

  const baseUrl = normalizeBaseUrl(settings.apiBaseUrl);
  const url = `${baseUrl}/commands?clientId=${encodeURIComponent(settings.clientId)}`;
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to fetch commands: ${response.status} ${response.statusText}`);
  }

  const commands = await response.json();
  if (!Array.isArray(commands)) {
    throw new Error("Command endpoint must return an array");
  }

  let processed = 0;
  for (const command of commands) {
    await handleCommand(baseUrl, command);
    processed += 1;
  }

  await chrome.storage.local.set({ lastPollAt: new Date().toISOString(), lastPollProcessed: processed });
  return { processed };
}

async function handleCommand(baseUrl, command) {
  const id = assertString(command?.id, "command.id");
  let result;
  let error;

  try {
    result = await executeBookmarkCommand(command);
  } catch (caught) {
    error = caught instanceof Error ? caught.message : String(caught);
  }

  const response = await fetch(`${baseUrl}/commands/${encodeURIComponent(id)}/result`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ok: !error, result, error }),
  });

  if (!response.ok) {
    throw new Error(`Failed to post result for ${id}: ${response.status} ${response.statusText}`);
  }
}

async function executeBookmarkCommand(command) {
  const action = assertString(command.action, "command.action");
  const payload = command.payload ?? {};

  switch (action) {
    case "tree":
      return chrome.bookmarks.getTree();
    case "children":
      return chrome.bookmarks.getChildren(assertString(payload.parentId, "payload.parentId"));
    case "get":
      return chrome.bookmarks.get(assertString(payload.id, "payload.id"));
    case "search":
      return chrome.bookmarks.search(assertSearchQuery(payload.query));
    case "create":
      return chrome.bookmarks.create(assertCreatePayload(payload));
    case "update":
      return chrome.bookmarks.update(assertString(payload.id, "payload.id"), assertUpdateChanges(payload.changes));
    case "move":
      return chrome.bookmarks.move(assertString(payload.id, "payload.id"), assertMoveDestination(payload.destination));
    case "remove":
      await chrome.bookmarks.remove(assertString(payload.id, "payload.id"));
      return { removed: payload.id };
    case "removeTree":
      await chrome.bookmarks.removeTree(assertString(payload.id, "payload.id"));
      return { removedTree: payload.id };
    default:
      throw new Error(`Unsupported action: ${action}`);
  }
}

function assertCreatePayload(payload) {
  const createPayload = {};
  if (payload.parentId !== undefined) {
    createPayload.parentId = assertString(payload.parentId, "payload.parentId");
  }
  if (payload.index !== undefined) {
    createPayload.index = assertNonNegativeInteger(payload.index, "payload.index");
  }
  if (payload.title !== undefined) {
    createPayload.title = assertString(payload.title, "payload.title");
  }
  if (payload.url !== undefined) {
    createPayload.url = assertHttpUrl(payload.url, "payload.url");
  }
  if (!createPayload.title && !createPayload.url) {
    throw new Error("payload.title or payload.url is required for create");
  }
  return createPayload;
}

function assertUpdateChanges(changes) {
  if (!changes || typeof changes !== "object" || Array.isArray(changes)) {
    throw new Error("payload.changes must be an object");
  }

  const safeChanges = {};
  if (changes.title !== undefined) {
    safeChanges.title = assertString(changes.title, "payload.changes.title");
  }
  if (changes.url !== undefined) {
    safeChanges.url = assertHttpUrl(changes.url, "payload.changes.url");
  }
  if (Object.keys(safeChanges).length === 0) {
    throw new Error("payload.changes must include title or url");
  }
  return safeChanges;
}

function assertMoveDestination(destination) {
  if (!destination || typeof destination !== "object" || Array.isArray(destination)) {
    throw new Error("payload.destination must be an object");
  }

  const safeDestination = {};
  if (destination.parentId !== undefined) {
    safeDestination.parentId = assertString(destination.parentId, "payload.destination.parentId");
  }
  if (destination.index !== undefined) {
    safeDestination.index = assertNonNegativeInteger(destination.index, "payload.destination.index");
  }
  if (Object.keys(safeDestination).length === 0) {
    throw new Error("payload.destination must include parentId or index");
  }
  return safeDestination;
}

function assertSearchQuery(query) {
  if (typeof query === "string") {
    return query;
  }

  if (!query || typeof query !== "object" || Array.isArray(query)) {
    throw new Error("payload.query must be a string or object");
  }

  const safeQuery = {};
  if (query.title !== undefined) {
    safeQuery.title = assertString(query.title, "payload.query.title");
  }
  if (query.url !== undefined) {
    safeQuery.url = assertString(query.url, "payload.query.url");
  }
  return safeQuery;
}

function assertString(value, name) {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value;
}

function assertHttpUrl(value, name) {
  const url = assertString(value, name);
  const parsed = new URL(url);
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error(`${name} must use http or https`);
  }
  return url;
}

function assertNonNegativeInteger(value, name) {
  if (!Number.isInteger(value) || value < 0) {
    throw new Error(`${name} must be a non-negative integer`);
  }
  return value;
}

async function getSettings() {
  const settings = await chrome.storage.local.get(Object.keys(DEFAULT_SETTINGS));
  return { ...DEFAULT_SETTINGS, ...withoutUndefined(settings) };
}

function normalizeBaseUrl(value) {
  const parsed = new URL(assertString(value, "apiBaseUrl"));
  if (parsed.protocol !== "http:") {
    throw new Error("apiBaseUrl must use http for local development");
  }
  return parsed.toString().replace(/\/$/, "");
}

function withoutUndefined(value) {
  return Object.fromEntries(Object.entries(value).filter((entry) => entry[1] !== undefined));
}
