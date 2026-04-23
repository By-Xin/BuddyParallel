"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  buildBaseSessionId,
  buildCodexPresencePayload,
  buildCodexSessionId,
  describeCodexStatus,
} = require("./codex-monitor");

test("buildBaseSessionId normalizes workspace names", () => {
  assert.equal(buildBaseSessionId("My Cool Repo"), "vscode-my-cool-repo");
});

test("buildCodexSessionId appends codex suffix", () => {
  assert.equal(buildCodexSessionId("vscode-demo"), "vscode-demo-codex");
});

test("buildCodexPresencePayload clears the codex session when no task is open", () => {
  const payload = buildCodexPresencePayload(
    {
      installed: true,
      active: true,
      taskCount: 0,
      hasTask: false,
      focused: false,
      windowFocused: true,
      primaryLabel: "",
    },
    { id: "vscode-demo", codexTitle: "Codex" }
  );

  assert.equal(payload.clear_session, true);
  assert.equal(payload.session_id, "vscode-demo-codex");
  assert.equal(payload.message, "Codex: idle");
});

test("buildCodexPresencePayload emits a focused task summary", () => {
  const payload = buildCodexPresencePayload(
    {
      installed: true,
      active: true,
      taskCount: 2,
      hasTask: true,
      focused: true,
      windowFocused: true,
      primaryLabel: "task-123",
    },
    { id: "vscode-demo", codexTitle: "Codex" }
  );

  assert.equal(payload.clear_session, undefined);
  assert.equal(payload.state, "working");
  assert.equal(payload.running, true);
  assert.equal(payload.message, "Codex: task active");
  assert.deepEqual(payload.entries, ["2 tasks open", "focused in editor", "task-123"]);
});

test("buildCodexPresencePayload stays idle when the task is not actively focused", () => {
  const payload = buildCodexPresencePayload(
    {
      installed: true,
      active: true,
      taskCount: 1,
      hasTask: true,
      focused: false,
      windowFocused: true,
      primaryLabel: "task-456",
    },
    { id: "vscode-demo", codexTitle: "Codex" }
  );

  assert.equal(payload.state, "idle");
  assert.equal(payload.running, false);
  assert.equal(payload.message, "Codex: task open");
});

test("describeCodexStatus reports monitor errors first", () => {
  const text = describeCodexStatus(
    {
      installed: true,
      active: true,
      taskCount: 1,
      hasTask: true,
      focused: true,
      windowFocused: true,
      primaryLabel: "task-123",
    },
    "Cannot reach companion"
  );

  assert.match(text, /Cannot reach companion/);
});
