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
} = require("./codex-monitor");

function activate(context) {
  const state = {
    statusItem: vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100),
    codexInterval: null,
    codexDebounce: null,
    codexSyncInFlight: false,
    codexResyncRequested: false,
    lastCodexPayloadKey: "",
    lastCodexError: "",
    lastCodexSample: emptyCodexSample(),
  };

  state.statusItem.command = "buddyParallel.requestBoardApproval";
  state.statusItem.show();
  updateStatusItem(state);

  context.subscriptions.push(
    state.statusItem,
    vscode.commands.registerCommand("buddyParallel.requestBoardApproval", async () => {
      await runManualApproval();
    }),
    vscode.commands.registerCommand("buddyParallel.insertApprovedComment", async () => {
      await runApprovedCommentInsert();
    }),
    vscode.commands.registerCommand("buddyParallel.sendTestNotice", async () => {
      await sendBuddyEvent({
        event: "Notification",
        message: "VS Code: test notice",
        entries: ["BuddyParallel VS Code bridge"],
        completed: true,
      });
      vscode.window.showInformationMessage("BuddyParallel test notice sent.");
    }),
    vscode.commands.registerCommand("buddyParallel.openCodexSidebar", async () => {
      await runCodexCommand("chatgpt.openSidebar", "Opened Codex sidebar.");
      queueCodexSync(state, "command");
    }),
    vscode.commands.registerCommand("buddyParallel.newCodexTask", async () => {
      await runCodexCommand("chatgpt.newCodexPanel", "Opened a new Codex task.");
      queueCodexSync(state, "command");
    }),
    vscode.workspace.onDidOpenTextDocument(() => {
      queueCodexSync(state, "open-doc");
    }),
    vscode.workspace.onDidCloseTextDocument(() => {
      queueCodexSync(state, "close-doc");
    }),
    vscode.window.onDidChangeVisibleTextEditors(() => {
      queueCodexSync(state, "visible-editors");
    }),
    vscode.window.onDidChangeActiveTextEditor(() => {
      queueCodexSync(state, "active-editor");
    }),
    vscode.window.tabGroups.onDidChangeTabs(() => {
      queueCodexSync(state, "tabs");
    }),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration("buddyParallel")) {
        restartCodexMonitoring(state);
      }
    }),
    {
      dispose() {
        stopCodexMonitoring(state);
      },
    }
  );

  restartCodexMonitoring(state);
}

function deactivate() {}

async function runManualApproval() {
  const allowed = await requestBoardApproval({
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

async function runApprovedCommentInsert() {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("Open a file first to insert an approved comment.");
    return;
  }

  const document = editor.document;
  const comment = buildCommentForDocument(document);
  const allowed = await requestBoardApproval({
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

async function runCodexCommand(command, successMessage) {
  const extension = vscode.extensions.getExtension(CODEX_EXTENSION_ID);
  if (!extension) {
    vscode.window.showWarningMessage("OpenAI Codex extension is not installed.");
    return;
  }
  await vscode.commands.executeCommand(command);
  vscode.window.showInformationMessage(successMessage);
}

async function requestBoardApproval({ toolName, toolInput, completionLabel }) {
  let decision;
  try {
    const response = await postJson("/vscode/permission", {
      session_id: getSessionInfo().id,
      tool_name: toolName,
      tool_input: toolInput,
      timeout_seconds: getConfiguration().get("requestTimeoutSeconds", 590),
    });
    decision = String(response.decision || "ask");
  } catch (error) {
    await sendBuddyEvent({
      event: "Notification",
      message: "VS Code: approval failed",
      entries: [String(error.message || error)],
      completed: true,
    });
    throw error;
  }

  await sendBuddyEvent({
    event: "Notification",
    message: decision === "allow" ? `VS Code: approved ${completionLabel}` : `VS Code: denied ${completionLabel}`,
    entries: [toolName],
    completed: true,
  });
  await sendBuddyEvent({
    event: "Stop",
    state: "idle",
    message: "VS Code: idle",
    running: false,
    completed: false,
  });

  return decision === "allow";
}

function restartCodexMonitoring(state) {
  stopCodexMonitoring(state);
  state.lastCodexError = "";
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

async function syncCodexPresence(state) {
  if (state.codexSyncInFlight) {
    state.codexResyncRequested = true;
    return;
  }
  state.codexSyncInFlight = true;

  try {
    const sample = collectCodexSample();
    state.lastCodexSample = sample;
    const payload = buildCodexPresencePayload(sample, getSessionInfo());
    const payloadKey = buildCodexPayloadKey(payload);
    updateStatusItem(state);
    if (payloadKey !== state.lastCodexPayloadKey) {
      await sendBuddyEvent(payload);
      state.lastCodexPayloadKey = payloadKey;
    }
    state.lastCodexError = "";
    updateStatusItem(state);
  } catch (error) {
    state.lastCodexError = String(error.message || error);
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
  const payload = buildCodexPresencePayload(emptyCodexSample(), getSessionInfo());
  const payloadKey = buildCodexPayloadKey(payload);
  try {
    if (payloadKey !== state.lastCodexPayloadKey) {
      await sendBuddyEvent(payload);
      state.lastCodexPayloadKey = payloadKey;
    }
  } catch (error) {
    state.lastCodexError = String(error.message || error);
  }
  state.lastCodexSample = emptyCodexSample();
  updateStatusItem(state);
}

function collectCodexSample() {
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

function emptyCodexSample() {
  return {
    installed: Boolean(vscode.extensions.getExtension(CODEX_EXTENSION_ID)),
    active: Boolean(vscode.extensions.getExtension(CODEX_EXTENSION_ID)?.isActive),
    taskCount: 0,
    hasTask: false,
    focused: false,
    primaryLabel: "",
  };
}

function updateStatusItem(state) {
  const monitoringEnabled = getConfiguration().get("codexMonitoringEnabled", true);
  if (!monitoringEnabled) {
    state.statusItem.text = "$(device-camera-video) BuddyParallel";
    state.statusItem.tooltip = "BuddyParallel hardware approval bridge\nCodex monitoring: off";
    return;
  }

  const sample = state.lastCodexSample || emptyCodexSample();
  const codexBadge = sample.hasTask ? ` Codex ${sample.taskCount}` : "";
  state.statusItem.text = `$(device-camera-video) BuddyParallel${codexBadge}`;
  state.statusItem.tooltip = `BuddyParallel hardware approval bridge\n${describeCodexStatus(sample, state.lastCodexError)}`;
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
