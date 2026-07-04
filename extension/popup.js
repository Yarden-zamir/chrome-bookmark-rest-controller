const DEFAULT_SETTINGS = {
  apiBaseUrl: "http://127.0.0.1:8877",
  clientId: "bookmarkctl",
  enabled: true,
  pollIntervalSeconds: 5,
};

const fields = {
  apiBaseUrl: document.querySelector("#apiBaseUrl"),
  clientId: document.querySelector("#clientId"),
  enabled: document.querySelector("#enabled"),
  pollIntervalSeconds: document.querySelector("#pollIntervalSeconds"),
  save: document.querySelector("#save"),
  pollNow: document.querySelector("#pollNow"),
  status: document.querySelector("#status"),
};

loadSettings().catch(showError);

fields.save.addEventListener("click", () => {
  saveSettings().catch(showError);
});

fields.pollNow.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "poll-now" }, (response) => {
    const error = chrome.runtime.lastError?.message || response?.error;
    if (error) {
      showError(new Error(error));
      return;
    }
    fields.status.textContent = `Processed ${response?.result?.processed ?? 0} command(s).`;
  });
});

async function loadSettings() {
  const settings = { ...DEFAULT_SETTINGS, ...(await chrome.storage.local.get(Object.keys(DEFAULT_SETTINGS))) };
  fields.apiBaseUrl.value = settings.apiBaseUrl;
  fields.clientId.value = settings.clientId;
  fields.enabled.checked = Boolean(settings.enabled);
  fields.pollIntervalSeconds.value = String(settings.pollIntervalSeconds);
}

async function saveSettings() {
  const pollIntervalSeconds = Number(fields.pollIntervalSeconds.value);
  if (!Number.isInteger(pollIntervalSeconds) || pollIntervalSeconds < 1) {
    throw new Error("Poll interval must be a positive integer");
  }

  await chrome.storage.local.set({
    apiBaseUrl: fields.apiBaseUrl.value,
    clientId: fields.clientId.value,
    enabled: fields.enabled.checked,
    pollIntervalSeconds,
  });
  fields.status.textContent = "Saved.";
}

function showError(error) {
  fields.status.textContent = error.message;
}
