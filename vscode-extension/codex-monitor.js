"use strict";

const CODEX_EXTENSION_ID = "openai.chatgpt";
const CODEX_URI_SCHEME = "openai-codex";

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
  if (sample.focused) {
    entries.push("focused in editor");
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

  return {
    session_id: sessionId,
    session_title: sessionTitle,
    event: "SessionStart",
    state: "idle",
    running: false,
    waiting: false,
    completed: false,
    message: sample.focused ? `${sessionTitle}: task focused` : `${sessionTitle}: task open`,
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
  return sample.focused
    ? `Codex focused, ${formatTaskCount(sample.taskCount)}.`
    : `Codex open, ${formatTaskCount(sample.taskCount)}.`;
}

function buildCodexPayloadKey(payload) {
  return JSON.stringify(payload);
}

module.exports = {
  CODEX_EXTENSION_ID,
  CODEX_URI_SCHEME,
  buildBaseSessionId,
  buildCodexSessionId,
  buildCodexEntries,
  buildCodexPayloadKey,
  buildCodexPresencePayload,
  describeCodexStatus,
  formatTaskCount,
  slugifyWorkspaceName,
};
