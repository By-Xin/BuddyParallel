"use strict";

const EDIT_ACTIVITY_WINDOW_MS = 15000;
const LONG_RUN_NOTICE_MS = 10000;

function buildRunSessionId(baseSessionId) {
  return `${String(baseSessionId || "vscode-window")}-run`;
}

function buildProblemsSessionId(baseSessionId) {
  return `${String(baseSessionId || "vscode-window")}-problems`;
}

function buildWorkspaceEntries(sample) {
  const entries = [];
  if (sample.recentlyEdited) {
    entries.push("recent edit");
  }
  if (sample.activeLabel) {
    entries.push(sample.activeLabel);
  }
  if (!sample.windowFocused) {
    entries.push("window in background");
  } else if (!sample.recentlyEdited) {
    entries.push("window focused");
  }
  return entries.slice(0, 4);
}

function buildWorkspacePresencePayload(sample, session) {
  const sessionId = String(session.id || "vscode-window");
  const sessionTitle = String(session.title || "VS Code");
  return {
    session_id: sessionId,
    session_title: sessionTitle,
    event: sample.recentlyEdited ? "UserPromptSubmit" : "SessionStart",
    state: sample.recentlyEdited ? "thinking" : "idle",
    running: Boolean(sample.recentlyEdited),
    waiting: false,
    completed: false,
    message: sample.recentlyEdited
      ? `${sessionTitle}: editing`
      : sample.windowFocused
        ? `${sessionTitle}: focused`
        : `${sessionTitle}: background`,
    entries: buildWorkspaceEntries(sample),
  };
}

function summarizeCommandLine(value, maxLength = 48) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) {
    return "command";
  }
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, Math.max(1, maxLength - 1))}\u2026`;
}

function buildRunEntries(activeRuns) {
  const runs = Array.isArray(activeRuns) ? activeRuns : [];
  const entries = [`${runs.length} command${runs.length === 1 ? "" : "s"} running`];
  const first = runs[0];
  if (first?.terminalName) {
    entries.push(first.terminalName);
  }
  if (first?.commandLabel) {
    entries.push(first.commandLabel);
  }
  return entries.slice(0, 4);
}

function buildRunPayload(activeRuns, session) {
  const runs = Array.isArray(activeRuns) ? activeRuns : [];
  const sessionId = buildRunSessionId(session.id);
  const sessionTitle = "Run";
  if (!runs.length) {
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

  const first = runs[0];
  const single = runs.length === 1;
  return {
    session_id: sessionId,
    session_title: sessionTitle,
    event: "PreToolUse",
    state: "working",
    running: true,
    waiting: false,
    completed: false,
    message: single ? `${sessionTitle}: ${first.commandLabel}` : `${sessionTitle}: ${runs.length} commands`,
    entries: buildRunEntries(runs),
  };
}

function buildRunCompletionNotice(result) {
  const commandLabel = result?.commandLabel || "command";
  const exitCode = Number.isInteger(result?.exitCode) ? result.exitCode : 0;
  const success = exitCode === 0;
  const durationMs = Number.isFinite(result?.durationMs) ? result.durationMs : 0;
  return {
    event: "Notification",
    message: success ? "Run completed" : "Run failed",
    entries: success
      ? [commandLabel, `${Math.round(durationMs / 1000)}s`]
      : [commandLabel, `exit ${exitCode}`],
    completed: false,
  };
}

function summarizeDiagnostics(diagnosticEntries) {
  const summary = {
    errors: 0,
    warnings: 0,
    informations: 0,
    hints: 0,
  };
  for (const [, diagnostics] of diagnosticEntries || []) {
    for (const diagnostic of diagnostics || []) {
      switch (diagnostic?.severity) {
        case 0:
          summary.errors += 1;
          break;
        case 1:
          summary.warnings += 1;
          break;
        case 2:
          summary.informations += 1;
          break;
        case 3:
          summary.hints += 1;
          break;
        default:
          break;
      }
    }
  }
  return summary;
}

function buildProblemsEntries(summary) {
  const entries = [];
  if (summary.errors) {
    entries.push(`${summary.errors} error${summary.errors === 1 ? "" : "s"}`);
  }
  if (summary.warnings) {
    entries.push(`${summary.warnings} warning${summary.warnings === 1 ? "" : "s"}`);
  }
  if (summary.informations) {
    entries.push(`${summary.informations} info`);
  }
  return entries.slice(0, 4);
}

function buildProblemsPayload(summary, session) {
  const sessionId = buildProblemsSessionId(session.id);
  const sessionTitle = "Problems";
  const hasErrors = summary.errors > 0;
  const hasWarnings = summary.warnings > 0;
  if (!hasErrors && !hasWarnings) {
    return {
      session_id: sessionId,
      session_title: sessionTitle,
      state: "idle",
      clear_session: true,
      running: false,
      waiting: false,
      completed: false,
      message: `${sessionTitle}: clear`,
    };
  }

  return {
    session_id: sessionId,
    session_title: sessionTitle,
    event: hasErrors ? "PostCompact" : "SessionStart",
    state: hasErrors ? "attention" : "idle",
    running: false,
    waiting: false,
    completed: false,
    message: hasErrors
      ? `${sessionTitle}: ${summary.errors} error${summary.errors === 1 ? "" : "s"}`
      : `${sessionTitle}: ${summary.warnings} warning${summary.warnings === 1 ? "" : "s"}`,
    entries: buildProblemsEntries(summary),
  };
}

function describeWorkspaceStatus(sample) {
  if (!sample.windowFocused) {
    return "VS Code window in background";
  }
  if (sample.recentlyEdited) {
    return sample.activeLabel ? `Editing ${sample.activeLabel}` : "Recent editing activity";
  }
  return "VS Code focused";
}

function describeRunStatus(activeRuns) {
  const runs = Array.isArray(activeRuns) ? activeRuns : [];
  if (!runs.length) {
    return "No running shell command";
  }
  if (runs.length === 1) {
    return `Running ${runs[0].commandLabel}`;
  }
  return `${runs.length} shell commands running`;
}

function describeProblemsStatus(summary) {
  if (!summary.errors && !summary.warnings) {
    return "No current errors or warnings";
  }
  if (summary.errors) {
    if (summary.warnings) {
      return `${summary.errors} error${summary.errors === 1 ? "" : "s"} and ${summary.warnings} warning${summary.warnings === 1 ? "" : "s"}`;
    }
    return `${summary.errors} error${summary.errors === 1 ? "" : "s"}`;
  }
  return `${summary.warnings} warning${summary.warnings === 1 ? "" : "s"}`;
}

module.exports = {
  EDIT_ACTIVITY_WINDOW_MS,
  LONG_RUN_NOTICE_MS,
  buildProblemsPayload,
  buildProblemsSessionId,
  buildRunCompletionNotice,
  buildRunPayload,
  buildRunSessionId,
  buildWorkspacePresencePayload,
  describeProblemsStatus,
  describeRunStatus,
  describeWorkspaceStatus,
  summarizeCommandLine,
  summarizeDiagnostics,
};
