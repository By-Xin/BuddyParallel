"use strict";

const CODEX_EXTENSION_ID = "openai.chatgpt";
const CODEX_URI_SCHEME = "openai-codex";
const ACTIVE_UPDATE_WINDOW_MS = 12000;

function slugifyWorkspaceName(value) {
  return String(value || "window")
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "") || "window";
}

function buildBaseSessionId(workspaceName) {
  return `vscode-${slugifyWorkspaceName(workspaceName)}`;
}

function buildCodexSessionId(baseSessionId) {
  return `${String(baseSessionId || "vscode-window")}-codex`;
}

function formatTaskCount(count) {
  return `${count} task${count === 1 ? "" : "s"} open`;
}

function buildCodexEntries(sample) {
  const entries = [formatTaskCount(sample.taskCount)];
  if (sample.recentlyUpdated) {
    entries.push("recent update");
  }
  if (sample.focused) {
    entries.push("focused in editor");
  }
  if (!sample.windowFocused) {
    entries.push("window in background");
  }
  if (sample.primaryLabel) {
    entries.push(sample.primaryLabel);
  }
  return entries.slice(0, 4);
}

function buildCodexPresencePayload(sample, session) {
  const sessionId = buildCodexSessionId(session.id);
  const sessionTitle = String(session.codexTitle || "Codex");
  if (!sample.hasTask) {
    return {
      session_id: sessionId,
      session_title: sessionTitle,
      state: "idle",
      clear_session: true,
      running: false,
      waiting: false,
      completed: false,
      message: `${sessionTitle}: idle`,
    };
  }

  const activelyUpdating = Boolean(sample.recentlyUpdated);
  const foregroundFocused = Boolean(sample.focused && sample.windowFocused);
  return {
    session_id: sessionId,
    session_title: sessionTitle,
    event: activelyUpdating ? "PreToolUse" : "SessionStart",
    state: activelyUpdating ? "working" : "idle",
    running: activelyUpdating,
    waiting: false,
    completed: false,
    message: activelyUpdating
      ? `${sessionTitle}: task updating`
      : foregroundFocused
        ? `${sessionTitle}: task focused`
        : `${sessionTitle}: task open`,
    entries: buildCodexEntries(sample),
  };
}

function describeCodexStatus(sample, errorText = "") {
  if (errorText) {
    return `BuddyParallel Codex monitor error: ${errorText}`;
  }
  if (!sample.installed) {
    return "Codex extension not installed.";
  }
  if (!sample.active) {
    return "Codex installed, waiting to activate.";
  }
  if (!sample.hasTask) {
    return "Codex active, no open task.";
  }
  if (sample.recentlyUpdated) {
    return `Codex updating, ${formatTaskCount(sample.taskCount)}.`;
  }
  if (sample.focused && sample.windowFocused) {
    return `Codex focused, ${formatTaskCount(sample.taskCount)}.`;
  }
  return sample.focused
    ? `Codex focused, ${formatTaskCount(sample.taskCount)}.`
    : `Codex open, ${formatTaskCount(sample.taskCount)}.`;
}

function buildCodexPayloadKey(payload) {
  return JSON.stringify(payload);
}

function isRecentCodexUpdate(lastUpdatedAt, now = Date.now()) {
  if (!Number.isFinite(lastUpdatedAt) || lastUpdatedAt <= 0) {
    return false;
  }
  return (now - lastUpdatedAt) <= ACTIVE_UPDATE_WINDOW_MS;
}

module.exports = {
  ACTIVE_UPDATE_WINDOW_MS,
  CODEX_EXTENSION_ID,
  CODEX_URI_SCHEME,
  buildBaseSessionId,
  buildCodexSessionId,
  buildCodexEntries,
  buildCodexPayloadKey,
  buildCodexPresencePayload,
  describeCodexStatus,
  formatTaskCount,
  isRecentCodexUpdate,
  slugifyWorkspaceName,
};
