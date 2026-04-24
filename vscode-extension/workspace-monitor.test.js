"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  buildProblemsPayload,
  buildRunCompletionNotice,
  buildRunPayload,
  buildWorkspacePresencePayload,
  describeProblemsStatus,
  summarizeCommandLine,
  summarizeDiagnostics,
} = require("./workspace-monitor");

test("buildWorkspacePresencePayload marks recent edits as thinking", () => {
  const payload = buildWorkspacePresencePayload(
    {
      windowFocused: true,
      recentlyEdited: true,
      activeLabel: "train.py",
    },
    { id: "vscode-demo", title: "VS Code" }
  );

  assert.equal(payload.session_id, "vscode-demo");
  assert.equal(payload.state, "thinking");
  assert.equal(payload.running, true);
  assert.equal(payload.message, "VS Code: editing");
  assert.deepEqual(payload.entries, ["recent edit", "train.py"]);
});

test("buildRunPayload clears the run session when nothing is active", () => {
  const payload = buildRunPayload([], { id: "vscode-demo" });

  assert.equal(payload.clear_session, true);
  assert.equal(payload.session_id, "vscode-demo-run");
});

test("buildRunPayload summarizes active commands", () => {
  const payload = buildRunPayload(
    [
      {
        commandLabel: "python train.py --epochs 20",
        terminalName: "Training",
      },
    ],
    { id: "vscode-demo" }
  );

  assert.equal(payload.state, "working");
  assert.equal(payload.running, true);
  assert.equal(payload.message, "Run: python train.py --epochs 20");
  assert.deepEqual(payload.entries, ["1 command running", "Training", "python train.py --epochs 20"]);
});

test("buildRunCompletionNotice distinguishes success and failure", () => {
  const success = buildRunCompletionNotice({ commandLabel: "python ok.py", exitCode: 0, durationMs: 12_300 });
  const failure = buildRunCompletionNotice({ commandLabel: "python fail.py", exitCode: 2 });

  assert.equal(success.message, "Run completed");
  assert.deepEqual(success.entries, ["python ok.py", "12s"]);
  assert.equal(success.completed, false);
  assert.equal(failure.message, "Run failed");
  assert.deepEqual(failure.entries, ["python fail.py", "exit 2"]);
  assert.equal(failure.completed, false);
});

test("summarizeDiagnostics counts severities", () => {
  const summary = summarizeDiagnostics([
    ["file:///demo.py", [{ severity: 0 }, { severity: 1 }, { severity: 1 }]],
    ["file:///other.py", [{ severity: 2 }, { severity: 3 }]],
  ]);

  assert.deepEqual(summary, {
    errors: 1,
    warnings: 2,
    informations: 1,
    hints: 1,
  });
});

test("buildProblemsPayload escalates errors and clears when clean", () => {
  const active = buildProblemsPayload(
    { errors: 2, warnings: 1, informations: 0, hints: 0 },
    { id: "vscode-demo" }
  );
  const cleared = buildProblemsPayload(
    { errors: 0, warnings: 0, informations: 0, hints: 0 },
    { id: "vscode-demo" }
  );

  assert.equal(active.session_id, "vscode-demo-problems");
  assert.equal(active.state, "attention");
  assert.equal(active.waiting, false);
  assert.deepEqual(active.entries, ["2 errors", "1 warning"]);
  assert.equal(cleared.clear_session, true);
});

test("helpers keep summaries compact", () => {
  assert.match(summarizeCommandLine("python very_long_command_name.py --with lots    of    args"), /python/);
  assert.equal(describeProblemsStatus({ errors: 0, warnings: 0, informations: 0, hints: 0 }), "No current errors or warnings");
});
