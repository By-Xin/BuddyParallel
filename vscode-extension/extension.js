const vscode = require("vscode");
const http = require("http");
const https = require("https");

function activate(context) {
  const statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusItem.text = "$(device-camera-video) BuddyParallel";
  statusItem.tooltip = "BuddyParallel hardware approval bridge";
  statusItem.command = "buddyParallel.requestBoardApproval";
  statusItem.show();

  context.subscriptions.push(
    statusItem,
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
        completed: true
      });
      vscode.window.showInformationMessage("BuddyParallel test notice sent.");
    })
  );
}

function deactivate() {}

async function runManualApproval() {
  const allowed = await requestBoardApproval({
    toolName: "VS Code action",
    toolInput: { command: "manual test approval" },
    pendingMessage: "VS Code: waiting approval",
    completionLabel: "manual approval"
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
    pendingMessage: `VS Code: edit ${basename(document.uri.fsPath)}`,
    completionLabel: "workspace edit"
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

async function requestBoardApproval({ toolName, toolInput, pendingMessage, completionLabel }) {
  const session = getSessionInfo();

  await sendBuddyEvent({
    event: "PreToolUse",
    state: "working",
    message: pendingMessage,
    entries: [toolName],
    running: true,
    completed: false
  });

  let decision;
  try {
    const response = await postJson("/vscode/permission", {
      session_id: session.id,
      tool_name: toolName,
      tool_input: toolInput,
      timeout_seconds: getConfiguration().get("requestTimeoutSeconds", 590)
    });
    decision = String(response.decision || "ask");
  } catch (error) {
    await sendBuddyEvent({
      event: "Notification",
      message: `VS Code: approval failed`,
      entries: [String(error.message || error)],
      completed: true
    });
    throw error;
  }

  await sendBuddyEvent({
    event: "Notification",
    message: decision === "allow" ? `VS Code: approved ${completionLabel}` : `VS Code: denied ${completionLabel}`,
    entries: [toolName],
    completed: true
  });
  await sendBuddyEvent({
    event: "Stop",
    state: "idle",
    message: "VS Code: idle",
    running: false,
    completed: false
  });

  return decision === "allow";
}

async function sendBuddyEvent(payload) {
  const session = getSessionInfo();
  return postJson("/events", {
    source: "vscode",
    session_id: session.id,
    session_title: session.title,
    ...payload
  });
}

function getSessionInfo() {
  const title = getConfiguration().get("sessionTitle", "VS Code");
  const workspaceName = vscode.workspace.name || "window";
  return {
    id: `vscode-${workspaceName.toLowerCase().replace(/[^a-z0-9_-]+/g, "-")}`,
    title
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
          "Content-Length": Buffer.byteLength(body)
        }
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
  deactivate
};
