const vscode = require("vscode");
const http = require("http");
const https = require("https");

const {
  CODEX_EXTENSION_ID,
  CODEX_URI_SCHEME,
  buildBaseSessionId,
  buildCodexPayloadKey,
  buildCodexPresencePayload,
  describeCodexStatus,
  isRecentCodexUpdate,
} = require("./codex-monitor");
const {
  EDIT_ACTIVITY_WINDOW_MS,
  LONG_RUN_NOTICE_MS,
  buildProblemsPayload,
  buildRunCompletionNotice,
  buildRunPayload,
  buildWorkspacePresencePayload,
  describeProblemsStatus,
  describeRunStatus,
  describeWorkspaceStatus,
  summarizeCommandLine,
  summarizeDiagnostics,
} = require("./workspace-monitor");

function activate(context) {
  const state = {
    statusItem: vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100),
    output: vscode.window.createOutputChannel("BuddyParallel"),
    participant: null,
    codexInterval: null,
    codexDebounce: null,
    codexSyncInFlight: false,
    codexResyncRequested: false,
    lastCodexPayloadKey: "",
    lastCodexError: "",
    lastCodexUpdateAt: 0,
    lastCodexSample: emptyCodexSample(),
    workspaceInterval: null,
    workspaceDebounce: null,
    workspaceSyncInFlight: false,
    workspaceResyncRequested: false,
    lastWorkspacePayloadKey: "",
    lastWorkspaceActivityAt: 0,
    lastWorkspaceSample: emptyWorkspaceSample(),
    runsSyncInFlight: false,
    runsResyncRequested: false,
    activeRuns: new Map(),
    lastRunPayloadKey: "",
    lastProblemsPayloadKey: "",
    problemsDebounce: null,
    lastProblemsSummary: emptyProblemsSummary(),
  };

  state.statusItem.command = "buddyParallel.requestBoardApproval";
  state.statusItem.show();
  logOutput(state, "BuddyParallel extension activated.");
  updateStatusItem(state);

  registerChatParticipant(context, state);

  context.subscriptions.push(
    state.statusItem,
    state.output,
    vscode.commands.registerCommand("buddyParallel.requestBoardApproval", async () => {
      await runManualApproval(state);
    }),
    vscode.commands.registerCommand("buddyParallel.insertApprovedComment", async () => {
      await runApprovedCommentInsert(state);
    }),
    vscode.commands.registerCommand("buddyParallel.sendTestNotice", async () => {
      await sendBuddyEvent({
        event: "Notification",
        message: "VS Code: test notice",
        entries: ["BuddyParallel VS Code bridge"],
        completed: false,
      });
      logOutput(state, "Sent BuddyParallel test notice.");
      vscode.window.showInformationMessage("BuddyParallel test notice sent.");
    }),
    vscode.commands.registerCommand("buddyParallel.openCodexSidebar", async () => {
      await runCodexCommand(state, "chatgpt.openSidebar", "Opened Codex sidebar.");
      queueCodexSync(state, "command");
    }),
    vscode.commands.registerCommand("buddyParallel.newCodexTask", async () => {
      await runCodexCommand(state, "chatgpt.newCodexPanel", "Opened a new Codex task.");
      queueCodexSync(state, "command");
    }),
    vscode.commands.registerCommand("buddyParallel.showCodexMonitorStatus", async () => {
      showCodexMonitorStatus(state);
    }),
    vscode.commands.registerCommand("buddyParallel.showLogs", async () => {
      state.output.show(true);
    }),
    vscode.workspace.onDidOpenTextDocument(() => {
      queueCodexSync(state, "open-doc");
    }),
    vscode.workspace.onDidCloseTextDocument(() => {
      queueCodexSync(state, "close-doc");
    }),
    vscode.workspace.onDidChangeTextDocument((event) => {
      if (event.document?.uri?.scheme === CODEX_URI_SCHEME) {
        state.lastCodexUpdateAt = Date.now();
        queueCodexSync(state, "doc-update");
        return;
      }
      if (event.contentChanges?.length && isWorkspaceDocument(event.document)) {
        state.lastWorkspaceActivityAt = Date.now();
        queueWorkspaceSync(state, "text-edit");
      }
    }),
    typeof vscode.workspace.onDidChangeNotebookDocument === "function"
      ? vscode.workspace.onDidChangeNotebookDocument((event) => {
        if (event.contentChanges?.length || event.cellChanges?.length) {
          state.lastWorkspaceActivityAt = Date.now();
          queueWorkspaceSync(state, "notebook-edit");
        }
      })
      : { dispose() {} },
    vscode.window.onDidChangeVisibleTextEditors(() => {
      queueCodexSync(state, "visible-editors");
    }),
    vscode.window.onDidChangeActiveTextEditor(() => {
      queueCodexSync(state, "active-editor");
      queueWorkspaceSync(state, "active-editor");
    }),
    vscode.window.onDidChangeWindowState(() => {
      queueCodexSync(state, "window-focus");
      queueWorkspaceSync(state, "window-focus");
    }),
    vscode.window.tabGroups.onDidChangeTabs(() => {
      queueCodexSync(state, "tabs");
    }),
    vscode.languages.onDidChangeDiagnostics(() => {
      queueProblemsSync(state, "diagnostics");
    }),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration("buddyParallel")) {
        restartCodexMonitoring(state);
        restartWorkspaceMonitoring(state);
        queueProblemsSync(state, "config");
        void syncRunPresence(state);
      }
    }),
    ...registerTerminalLifecycle(context, state),
    {
      dispose() {
        stopCodexMonitoring(state);
        stopWorkspaceMonitoring(state);
        state.participant?.dispose?.();
      },
    }
  );

  restartCodexMonitoring(state);
  restartWorkspaceMonitoring(state);
  queueProblemsSync(state, "activate");
}

function deactivate() {}

async function runManualApproval(state) {
  logOutput(state, "Requesting manual board approval.");
  const allowed = await requestBoardApproval({
    state,
    toolName: "VS Code action",
    toolInput: { command: "manual test approval" },
    completionLabel: "manual approval",
  });

  if (allowed) {
    vscode.window.showInformationMessage("BuddyParallel board approved the request.");
  } else {
    vscode.window.showWarningMessage("BuddyParallel board denied the request.");
  }
}

async function runApprovedCommentInsert(state) {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("Open a file first to insert an approved comment.");
    return;
  }

  const document = editor.document;
  const comment = buildCommentForDocument(document);
  logOutput(state, `Requesting board approval for workspace edit on ${document.uri.fsPath}`);
  const allowed = await requestBoardApproval({
    state,
    toolName: "Workspace Edit",
    toolInput: { file_path: document.uri.fsPath },
    completionLabel: "workspace edit",
  });

  if (!allowed) {
    vscode.window.showWarningMessage("BuddyParallel board denied the workspace edit.");
    return;
  }

  const edit = new vscode.WorkspaceEdit();
  edit.insert(document.uri, new vscode.Position(0, 0), comment + "\n");
  await vscode.workspace.applyEdit(edit);
  vscode.window.showInformationMessage("BuddyParallel approved and inserted the comment.");
}

async function runCodexCommand(state, command, successMessage) {
  const extension = vscode.extensions.getExtension(CODEX_EXTENSION_ID);
  if (!extension) {
    logOutput(state, "Codex command skipped because the extension is not installed.");
    vscode.window.showWarningMessage("OpenAI Codex extension is not installed.");
    return;
  }
  logOutput(state, `Executing Codex command: ${command}`);
  await vscode.commands.executeCommand(command);
  vscode.window.showInformationMessage(successMessage);
}

async function requestBoardApproval({ state, toolName, toolInput, completionLabel }) {
  const requestId = buildRequestId();
  const startedAt = Date.now();
  let decision;
  try {
    logOutput(
      state,
      `Board approval request issued request_id=${requestId} tool=${toolName}`
    );
    const response = await postJson("/vscode/permission", {
      request_id: requestId,
      session_id: getSessionInfo().id,
      tool_name: toolName,
      tool_input: toolInput,
      timeout_seconds: getConfiguration().get("requestTimeoutSeconds", 590),
    });
    decision = String(response.decision || "ask");
    const elapsedMs = Date.now() - startedAt;
    logOutput(
      state,
      `Board approval response request_id=${requestId} decision=${decision} elapsed_ms=${elapsedMs}`
    );
  } catch (error) {
    await sendBuddyEvent({
      event: "Notification",
      message: "VS Code: approval failed",
      entries: [String(error.message || error)],
      completed: false,
    });
    const elapsedMs = Date.now() - startedAt;
    logOutput(
      state,
      `Board approval request failed request_id=${requestId} elapsed_ms=${elapsedMs} error=${String(error.message || error)}`
    );
    throw error;
  }

  await sendBuddyEvent({
    event: "Notification",
    message: decision === "allow" ? `VS Code: approved ${completionLabel}` : `VS Code: denied ${completionLabel}`,
    entries: [toolName],
    completed: false,
  });
  await sendBuddyEvent({
    event: "Stop",
    state: "idle",
    message: "VS Code: idle",
    running: false,
    completed: false,
  });
  queueWorkspaceSync(state);

  return decision === "allow";
}

function registerChatParticipant(context, state) {
  if (!vscode.chat || typeof vscode.chat.createChatParticipant !== "function") {
    logOutput(state, "Chat Participant API is unavailable in this VS Code build.");
    return;
  }

  const handler = createChatHandler(state);
  const participant = vscode.chat.createChatParticipant("buddyparallel.chat", handler);
  participant.followupProvider = {
    provideFollowups() {
      return [
        { prompt: "show BuddyParallel status", label: "Show status" },
        { prompt: "open the Codex sidebar", label: "Open Codex" },
        { prompt: "request a board approval test", label: "Board approval test" },
      ];
    },
  };
  state.participant = participant;
  context.subscriptions.push(participant);
  logOutput(state, "Registered BuddyParallel chat participant.");
}

function createChatHandler(state) {
  return async (request, chatContext, stream) => {
    const promptText = String(request.prompt || "").trim();
    logOutput(state, `Chat participant request received${request.command ? ` (${request.command})` : ""}: ${promptText || "<empty>"}`);

    if (request.command === "status" || /status|monitor|codex/i.test(promptText)) {
      stream.progress("Collecting BuddyParallel status...");
      stream.markdown(renderStatusMarkdown(state));
      stream.button({
        command: "buddyParallel.showCodexMonitorStatus",
        title: "Show detailed status",
        arguments: [],
      });
      stream.button({
        command: "buddyParallel.showLogs",
        title: "Open BuddyParallel logs",
        arguments: [],
      });
      return { metadata: { command: "status" } };
    }

    if (request.command === "codex" || /open.*codex|new.*codex|codex.*task/i.test(promptText)) {
      stream.markdown([
        "BuddyParallel can work alongside Codex in VS Code.",
        "",
        "- Use **Open Codex sidebar** to focus the Codex panel.",
        "- Use **New Codex task** to create a fresh task document.",
        "- While Codex task documents stay open, BuddyParallel mirrors that presence to the board.",
      ].join("\n"));
      stream.button({
        command: "buddyParallel.openCodexSidebar",
        title: "Open Codex sidebar",
        arguments: [],
      });
      stream.button({
        command: "buddyParallel.newCodexTask",
        title: "New Codex task",
        arguments: [],
      });
      return { metadata: { command: "codex" } };
    }

    if (request.command === "board" || /approval|approve|board/i.test(promptText)) {
      stream.progress("Requesting board approval...");
      const allowed = await requestBoardApproval({
        state,
        toolName: "VS Code chat request",
        toolInput: { prompt: promptText || "board approval test" },
        completionLabel: "chat approval",
      });
      stream.markdown(allowed
        ? "BuddyParallel board approved the request."
        : "BuddyParallel board denied the request.");
      stream.button({
        command: "buddyParallel.requestBoardApproval",
        title: "Run approval test again",
        arguments: [],
      });
      return { metadata: { command: "board", allowed } };
    }

    stream.markdown([
      "BuddyParallel is connected as a hardware approval bridge for VS Code.",
      "",
      "I can help with:",
      "- `/status` to inspect Codex monitor and companion status",
      "- `/codex` to open Codex surfaces and mirror their presence to the board",
      "- `/board` to run a board approval test",
    ].join("\n"));
    stream.button({
      command: "buddyParallel.showCodexMonitorStatus",
      title: "Show status",
      arguments: [],
    });
    stream.button({
      command: "buddyParallel.requestBoardApproval",
      title: "Board approval test",
      arguments: [],
    });
    return { metadata: { command: "help" } };
  };
}

function restartCodexMonitoring(state) {
  stopCodexMonitoring(state);
  state.lastCodexError = "";
  logOutput(state, "Restarting Codex monitoring.");
  updateStatusItem(state);

  if (!getConfiguration().get("codexMonitoringEnabled", true)) {
    void clearCodexPresence(state);
    return;
  }

  const pollSeconds = Math.max(1, Number(getConfiguration().get("codexPollingIntervalSeconds", 3)));
  state.codexInterval = setInterval(() => {
    void syncCodexPresence(state);
  }, pollSeconds * 1000);

  queueCodexSync(state, "restart");
}

function stopCodexMonitoring(state) {
  if (state.codexInterval) {
    clearInterval(state.codexInterval);
    state.codexInterval = null;
  }
  if (state.codexDebounce) {
    clearTimeout(state.codexDebounce);
    state.codexDebounce = null;
  }
}

function queueCodexSync(state) {
  if (state.codexDebounce) {
    clearTimeout(state.codexDebounce);
  }
  state.codexDebounce = setTimeout(() => {
    state.codexDebounce = null;
    void syncCodexPresence(state);
  }, 80);
}

function restartWorkspaceMonitoring(state) {
  stopWorkspaceMonitoring(state);
  logOutput(state, "Restarting workspace monitoring.");

  if (!getConfiguration().get("workspaceMonitoringEnabled", true)) {
    void clearWorkspacePresence(state);
    return;
  }

  state.workspaceInterval = setInterval(() => {
    void syncWorkspacePresence(state);
  }, 3000);

  queueWorkspaceSync(state);
}

function stopWorkspaceMonitoring(state) {
  if (state.workspaceInterval) {
    clearInterval(state.workspaceInterval);
    state.workspaceInterval = null;
  }
  if (state.workspaceDebounce) {
    clearTimeout(state.workspaceDebounce);
    state.workspaceDebounce = null;
  }
  if (state.problemsDebounce) {
    clearTimeout(state.problemsDebounce);
    state.problemsDebounce = null;
  }
}

function queueWorkspaceSync(state) {
  if (state.workspaceDebounce) {
    clearTimeout(state.workspaceDebounce);
  }
  state.workspaceDebounce = setTimeout(() => {
    state.workspaceDebounce = null;
    void syncWorkspacePresence(state);
  }, 80);
}

async function syncWorkspacePresence(state) {
  if (state.workspaceSyncInFlight) {
    state.workspaceResyncRequested = true;
    return;
  }
  state.workspaceSyncInFlight = true;

  try {
    const sample = collectWorkspaceSample(state);
    state.lastWorkspaceSample = sample;
    updateStatusItem(state);
    const payload = buildWorkspacePresencePayload(sample, getSessionInfo());
    const payloadKey = JSON.stringify(payload);
    if (payloadKey !== state.lastWorkspacePayloadKey) {
      await sendBuddyEvent(payload);
      state.lastWorkspacePayloadKey = payloadKey;
      logOutput(state, `Synced workspace status: ${describeWorkspaceStatus(sample)}`);
    }
  } catch (error) {
    logOutput(state, `Workspace sync failed: ${String(error.message || error)}`);
  } finally {
    state.workspaceSyncInFlight = false;
    if (state.workspaceResyncRequested) {
      state.workspaceResyncRequested = false;
      void syncWorkspacePresence(state);
    }
  }
}

async function clearWorkspacePresence(state) {
  const payload = {
    session_id: getSessionInfo().id,
    session_title: getSessionInfo().title,
    state: "idle",
    clear_session: true,
    running: false,
    waiting: false,
    completed: false,
    message: "VS Code: idle",
  };
  const payloadKey = JSON.stringify(payload);
  if (payloadKey === state.lastWorkspacePayloadKey) {
    return;
  }
  await sendBuddyEvent(payload);
  state.lastWorkspacePayloadKey = payloadKey;
  state.lastWorkspaceSample = emptyWorkspaceSample();
  updateStatusItem(state);
}

function queueProblemsSync(state) {
  if (state.problemsDebounce) {
    clearTimeout(state.problemsDebounce);
  }
  state.problemsDebounce = setTimeout(() => {
    state.problemsDebounce = null;
    void syncProblemsPresence(state);
  }, 120);
}

async function syncProblemsPresence(state) {
  if (!getConfiguration().get("problemsMonitoringEnabled", true)) {
    await clearProblemsPresence(state);
    return;
  }
  const summary = summarizeDiagnostics(vscode.languages.getDiagnostics());
  state.lastProblemsSummary = summary;
  updateStatusItem(state);
  const payload = buildProblemsPayload(summary, getSessionInfo());
  const payloadKey = JSON.stringify(payload);
  if (payloadKey === state.lastProblemsPayloadKey) {
    return;
  }
  await sendBuddyEvent(payload);
  state.lastProblemsPayloadKey = payloadKey;
  logOutput(state, `Synced problem status: ${describeProblemsStatus(summary)}`);
}

async function clearProblemsPresence(state) {
  const payload = buildProblemsPayload(emptyProblemsSummary(), getSessionInfo());
  const payloadKey = JSON.stringify(payload);
  if (payloadKey === state.lastProblemsPayloadKey) {
    return;
  }
  await sendBuddyEvent(payload);
  state.lastProblemsPayloadKey = payloadKey;
  state.lastProblemsSummary = emptyProblemsSummary();
  updateStatusItem(state);
}

function registerTerminalLifecycle(context, state) {
  if (typeof vscode.window.onDidStartTerminalShellExecution !== "function" ||
      typeof vscode.window.onDidEndTerminalShellExecution !== "function") {
    logOutput(state, "Terminal shell integration events are unavailable in this VS Code build.");
    return [];
  }

  return [
    vscode.window.onDidStartTerminalShellExecution((event) => {
      state.activeRuns.set(event.terminal, {
        terminalName: event.terminal?.name || "Terminal",
        commandLabel: summarizeCommandLine(resolveCommandLine(event.execution)),
        startedAt: Date.now(),
      });
      void syncRunPresence(state);
    }),
    vscode.window.onDidEndTerminalShellExecution((event) => {
      const run = state.activeRuns.get(event.terminal) || {
        terminalName: event.terminal?.name || "Terminal",
        commandLabel: summarizeCommandLine(resolveCommandLine(event.execution)),
        startedAt: Date.now(),
      };
      state.activeRuns.delete(event.terminal);
      void handleRunFinished(state, run, event.exitCode);
    }),
  ];
}

async function handleRunFinished(state, run, exitCode) {
  const durationMs = Math.max(0, Date.now() - Number(run.startedAt || Date.now()));
  if (
    getConfiguration().get("terminalMonitoringEnabled", true) &&
    (exitCode !== 0 || durationMs >= LONG_RUN_NOTICE_MS)
  ) {
    await sendBuddyEvent(buildRunCompletionNotice({
      commandLabel: run.commandLabel,
      exitCode,
      durationMs,
    }));
  }
  await syncRunPresence(state);
}

async function syncRunPresence(state) {
  if (state.runsSyncInFlight) {
    state.runsResyncRequested = true;
    return;
  }
  state.runsSyncInFlight = true;

  try {
    if (!getConfiguration().get("terminalMonitoringEnabled", true)) {
      await clearRunPresence(state);
      return;
    }
    const activeRuns = [...state.activeRuns.values()];
    updateStatusItem(state);
    const payload = buildRunPayload(activeRuns, getSessionInfo());
    const payloadKey = JSON.stringify(payload);
    if (payloadKey !== state.lastRunPayloadKey) {
      await sendBuddyEvent(payload);
      state.lastRunPayloadKey = payloadKey;
      logOutput(state, `Synced run status: ${describeRunStatus(activeRuns)}`);
    }
  } catch (error) {
    logOutput(state, `Run sync failed: ${String(error.message || error)}`);
  } finally {
    state.runsSyncInFlight = false;
    if (state.runsResyncRequested) {
      state.runsResyncRequested = false;
      void syncRunPresence(state);
    }
  }
}

async function clearRunPresence(state) {
  const payload = buildRunPayload([], getSessionInfo());
  const payloadKey = JSON.stringify(payload);
  if (payloadKey === state.lastRunPayloadKey) {
    return;
  }
  await sendBuddyEvent(payload);
  state.lastRunPayloadKey = payloadKey;
  updateStatusItem(state);
}

async function syncCodexPresence(state) {
  if (state.codexSyncInFlight) {
    state.codexResyncRequested = true;
    return;
  }
  state.codexSyncInFlight = true;

  try {
    const sample = collectCodexSample(state);
    state.lastCodexSample = sample;
    const payload = buildCodexPresencePayload(sample, getSessionInfo());
    const payloadKey = buildCodexPayloadKey(payload);
    updateStatusItem(state);
    if (payloadKey !== state.lastCodexPayloadKey) {
      await sendBuddyEvent(payload);
      state.lastCodexPayloadKey = payloadKey;
      logOutput(state, `Synced Codex presence: ${describeCodexStatus(sample)}`);
    }
    state.lastCodexError = "";
    updateStatusItem(state);
  } catch (error) {
    state.lastCodexError = String(error.message || error);
    logOutput(state, `Codex sync failed: ${state.lastCodexError}`);
    updateStatusItem(state);
  } finally {
    state.codexSyncInFlight = false;
    if (state.codexResyncRequested) {
      state.codexResyncRequested = false;
      void syncCodexPresence(state);
    }
  }
}

async function clearCodexPresence(state) {
  const payload = buildCodexPresencePayload(emptyCodexSample(state), getSessionInfo());
  const payloadKey = buildCodexPayloadKey(payload);
  try {
    if (payloadKey !== state.lastCodexPayloadKey) {
      await sendBuddyEvent(payload);
      state.lastCodexPayloadKey = payloadKey;
      logOutput(state, "Cleared mirrored Codex session.");
    }
  } catch (error) {
    state.lastCodexError = String(error.message || error);
    logOutput(state, `Failed to clear Codex session: ${state.lastCodexError}`);
  }
  state.lastCodexSample = emptyCodexSample(state);
  updateStatusItem(state);
}

function collectCodexSample(state) {
  const extension = vscode.extensions.getExtension(CODEX_EXTENSION_ID);
  const documents = vscode.workspace.textDocuments.filter((document) => document.uri.scheme === CODEX_URI_SCHEME);
  const tabUris = collectCodexTabUris();
  const allUris = dedupeUris([...documents.map((document) => document.uri), ...tabUris]);
  const activeUri = findActiveCodexUri();

  return {
    installed: Boolean(extension),
    active: Boolean(extension && extension.isActive),
    taskCount: allUris.length,
    hasTask: allUris.length > 0,
    focused: Boolean(activeUri),
    recentlyUpdated: isRecentCodexUpdate(state.lastCodexUpdateAt),
    windowFocused: Boolean(vscode.window.state?.focused),
    primaryLabel: activeUri ? basename(activeUri.path || activeUri.toString()) : "",
  };
}

function collectCodexTabUris() {
  const uris = [];
  for (const group of vscode.window.tabGroups.all) {
    for (const tab of group.tabs) {
      for (const uri of extractUrisFromTabInput(tab.input)) {
        if (uri && uri.scheme === CODEX_URI_SCHEME) {
          uris.push(uri);
        }
      }
    }
  }
  return uris;
}

function findActiveCodexUri() {
  const activeEditorUri = vscode.window.activeTextEditor?.document?.uri;
  if (activeEditorUri && activeEditorUri.scheme === CODEX_URI_SCHEME) {
    return activeEditorUri;
  }

  const activeGroup = vscode.window.tabGroups.activeTabGroup;
  const activeTab = activeGroup?.activeTab;
  if (!activeTab) {
    return null;
  }
  for (const uri of extractUrisFromTabInput(activeTab.input)) {
    if (uri && uri.scheme === CODEX_URI_SCHEME) {
      return uri;
    }
  }
  return null;
}

function extractUrisFromTabInput(input) {
  if (!input || typeof input !== "object") {
    return [];
  }
  const candidates = [];
  if (input.uri) {
    candidates.push(input.uri);
  }
  if (input.modified) {
    candidates.push(input.modified);
  }
  if (input.original) {
    candidates.push(input.original);
  }
  return candidates.filter(Boolean);
}

function dedupeUris(uris) {
  const seen = new Set();
  const ordered = [];
  for (const uri of uris) {
    const key = uri.toString();
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    ordered.push(uri);
  }
  return ordered;
}

function emptyCodexSample(state = null) {
  return {
    installed: Boolean(vscode.extensions.getExtension(CODEX_EXTENSION_ID)),
    active: Boolean(vscode.extensions.getExtension(CODEX_EXTENSION_ID)?.isActive),
    taskCount: 0,
    hasTask: false,
    focused: false,
    recentlyUpdated: Boolean(state && isRecentCodexUpdate(state.lastCodexUpdateAt)),
    windowFocused: Boolean(vscode.window.state?.focused),
    primaryLabel: "",
  };
}

function emptyWorkspaceSample() {
  return {
    windowFocused: Boolean(vscode.window.state?.focused),
    recentlyEdited: false,
    activeLabel: "",
  };
}

function emptyProblemsSummary() {
  return {
    errors: 0,
    warnings: 0,
    informations: 0,
    hints: 0,
  };
}

function collectWorkspaceSample(state) {
  const activeEditor = vscode.window.activeTextEditor;
  const activeDocument = activeEditor?.document;
  const activeNotebook = vscode.window.activeNotebookEditor?.notebook;
  const pulseWindowMs = Math.max(
    1000,
    Number(getConfiguration().get("workspaceEditPulseWindowSeconds", EDIT_ACTIVITY_WINDOW_MS / 1000)) * 1000
  );
  const activeLabel = activeDocument && isWorkspaceDocument(activeDocument)
    ? basename(activeDocument.uri.fsPath || activeDocument.uri.path || activeDocument.uri.toString())
    : activeNotebook
      ? basename(activeNotebook.uri.fsPath || activeNotebook.uri.path || activeNotebook.uri.toString())
      : "";
  return {
    windowFocused: Boolean(vscode.window.state?.focused),
    recentlyEdited: (Date.now() - state.lastWorkspaceActivityAt) <= pulseWindowMs,
    activeLabel,
  };
}

function isWorkspaceDocument(document) {
  const scheme = document?.uri?.scheme;
  return Boolean(document) && scheme !== CODEX_URI_SCHEME && scheme !== "output";
}

function resolveCommandLine(execution) {
  if (!execution) {
    return "";
  }
  if (typeof execution.commandLine === "string") {
    return execution.commandLine;
  }
  if (execution.commandLine && typeof execution.commandLine.value === "string") {
    return execution.commandLine.value;
  }
  return "";
}

function updateStatusItem(state) {
  const codexMonitoringEnabled = getConfiguration().get("codexMonitoringEnabled", true);
  const sample = state.lastCodexSample || emptyCodexSample(state);
  const workspace = state.lastWorkspaceSample || emptyWorkspaceSample();
  const problems = state.lastProblemsSummary || emptyProblemsSummary();
  const activeRuns = [...state.activeRuns.values()];
  const codexBadge = sample.hasTask ? ` Codex ${sample.taskCount}` : "";
  const prefix = state.lastCodexError ? "$(warning)" : "$(device-camera-video)";
  state.statusItem.text = `${prefix} BuddyParallel${codexMonitoringEnabled ? codexBadge : ""}`;
  state.statusItem.tooltip = [
    "BuddyParallel hardware approval bridge",
    `Workspace: ${describeWorkspaceStatus(workspace)}`,
    `Run: ${describeRunStatus(activeRuns)}`,
    `Problems: ${describeProblemsStatus(problems)}`,
    codexMonitoringEnabled
      ? `Codex: ${describeCodexStatus(sample, state.lastCodexError)}`
      : "Codex monitoring: off",
  ].join("\n");
}

function showCodexMonitorStatus(state) {
  const text = renderStatusMarkdown(state);
  logOutput(state, "Showing Codex monitor status.");
  state.output.show(true);
  state.output.appendLine("--- Status snapshot ---");
  for (const line of text.replace(/\*\*/g, "").split("\n")) {
    state.output.appendLine(line);
  }
  vscode.window.showInformationMessage("BuddyParallel status written to the BuddyParallel output channel.");
}

function renderStatusMarkdown(state) {
  const sample = state.lastCodexSample || emptyCodexSample(state);
  const workspace = state.lastWorkspaceSample || emptyWorkspaceSample();
  const problems = state.lastProblemsSummary || emptyProblemsSummary();
  const activeRuns = [...state.activeRuns.values()];
  const session = getSessionInfo();
  const lines = [
    `**BuddyParallel**`,
    ``,
    `- Companion API: ${getConfiguration().get("apiBaseUrl", "http://127.0.0.1:43112")}`,
    `- Session title: ${session.title}`,
    `- Codex session title: ${session.codexTitle}`,
    `- Codex extension installed: ${sample.installed ? "yes" : "no"}`,
    `- Codex extension active: ${sample.active ? "yes" : "no"}`,
    `- Open Codex tasks: ${sample.taskCount}`,
    `- Focused Codex task: ${sample.focused ? (sample.primaryLabel || "yes") : "no"}`,
    `- Recent Codex document update: ${sample.recentlyUpdated ? "yes" : "no"}`,
    `- VS Code window focused: ${sample.windowFocused ? "yes" : "no"}`,
    `- Monitor summary: ${describeCodexStatus(sample, state.lastCodexError)}`,
    `- Workspace summary: ${describeWorkspaceStatus(workspace)}`,
    `- Run summary: ${describeRunStatus(activeRuns)}`,
    `- Problems summary: ${describeProblemsStatus(problems)}`,
  ];
  if (state.lastCodexPayloadKey) {
    lines.push(`- Last payload synced: yes`);
  }
  return lines.join("\n");
}

function logOutput(state, message) {
  const stamp = new Date().toLocaleTimeString();
  state.output.appendLine(`[${stamp}] ${message}`);
}

async function sendBuddyEvent(payload) {
  const session = getSessionInfo();
  return postJson("/events", {
    source: "vscode",
    session_id: session.id,
    session_title: session.title,
    ...payload,
  });
}

function getSessionInfo() {
  const title = getConfiguration().get("sessionTitle", "VS Code");
  const workspaceName = vscode.workspace.name || "window";
  return {
    id: buildBaseSessionId(workspaceName),
    title,
    codexTitle: getConfiguration().get("codexSessionTitle", "Codex"),
  };
}

function getConfiguration() {
  return vscode.workspace.getConfiguration("buddyParallel");
}

function postJson(path, payload) {
  const baseUrl = getConfiguration().get("apiBaseUrl", "http://127.0.0.1:43112");
  const target = new URL(path, normalizeBaseUrl(baseUrl));
  const body = JSON.stringify(payload);
  const transport = target.protocol === "https:" ? https : http;

  return new Promise((resolve, reject) => {
    const request = transport.request(
      target,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(body),
        },
      },
      (response) => {
        let raw = "";
        response.setEncoding("utf8");
        response.on("data", (chunk) => {
          raw += chunk;
        });
        response.on("end", () => {
          if ((response.statusCode || 500) >= 400) {
            reject(new Error(`BuddyParallel companion returned HTTP ${response.statusCode}`));
            return;
          }
          try {
            resolve(raw ? JSON.parse(raw) : { ok: true });
          } catch (error) {
            reject(new Error(`Invalid JSON from BuddyParallel companion: ${error.message}`));
          }
        });
      }
    );

    request.on("error", (error) => {
      reject(new Error(`Cannot reach BuddyParallel companion at ${target.origin}: ${error.message}`));
    });
    request.write(body);
    request.end();
  });
}

function normalizeBaseUrl(value) {
  return value.endsWith("/") ? value : `${value}/`;
}

function basename(filePath) {
  const parts = String(filePath || "").split(/[\\/]/);
  return parts[parts.length - 1] || filePath;
}

function buildRequestId() {
  return `vscode-${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 8)}`;
}

function buildCommentForDocument(document) {
  const stamp = new Date().toLocaleString();
  const line = `Approved by BuddyParallel on ${stamp}`;
  const languageId = document.languageId;
  if (["javascript", "typescript", "javascriptreact", "typescriptreact", "java", "c", "cpp", "csharp", "rust", "go", "swift", "kotlin"].includes(languageId)) {
    return `// ${line}`;
  }
  if (["python", "shellscript", "yaml", "toml", "ruby", "perl", "makefile"].includes(languageId)) {
    return `# ${line}`;
  }
  if (["html", "xml", "markdown"].includes(languageId)) {
    return `<!-- ${line} -->`;
  }
  return `// ${line}`;
}

module.exports = {
  activate,
  deactivate,
};
