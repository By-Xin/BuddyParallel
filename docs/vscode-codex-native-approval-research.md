# VS Code Codex Native Approval Research

Updated: 2026-04-23

Related issues:
- #12 Codex hooks integration: track official hooks path separately from Windows-safe VS Code presence adapter
- #13 Research Codex native approval bridging for VS Code

## Question

Can BuddyParallel surface **Codex native permission / approval prompts** on the hardware board when the user interacts with Codex inside VS Code?

This is narrower than general Codex presence mirroring. The question is specifically whether Codex's own approval flow can be captured and forwarded into the existing BuddyParallel permission bridge.

## Current state

What already works on Windows:
- BuddyParallel can mirror Codex presence to the board.
- BuddyParallel can distinguish Codex task open / focused / recent document update pulses.
- BuddyParallel can run its own board approval tests from the VS Code extension.

What does not yet work:
- Codex's own native permission prompts do not currently flow to the board through a supported Windows path.

## Primary-source findings

### 1. OpenAI Codex hooks are the correct long-term integration surface

OpenAI's official Codex hooks documentation includes lifecycle events we would want for BuddyParallel:
- `SessionStart`
- `PreToolUse`
- `PermissionRequest`
- `PostToolUse`
- `Stop`

Source:
- <https://developers.openai.com/codex/hooks>

However, the current official docs explicitly note that **Windows support is temporarily disabled** for this hooks path.

Implication:
- Codex hooks are the most correct long-term path.
- They are not a safe Windows-mainline dependency right now.

### 2. VS Code public APIs do not give us a stable way to subscribe to another extension's private approval lifecycle

VS Code does support one extension consuming another extension's exported API through `extensions.getExtension(...).exports`, but only if the other extension intentionally exposes a stable API.

Source:
- <https://code.visualstudio.com/api/references/vscode-api#extensions>

VS Code also documents proposed APIs separately, and proposed APIs are not appropriate as the foundation of a stable released product path.

Source:
- <https://code.visualstudio.com/api/advanced-topics/using-proposed-api>

Implication:
- If the Codex VS Code extension does not explicitly export a public approval API, we should not assume we can consume one safely.

### 3. The installed Codex extension uses proposed APIs and internal notifications, but not a documented public approval bridge

The locally installed Codex extension manifest shows:
- `enabledApiProposals` includes `chatSessionsProvider`
- `enabledApiProposals` includes `languageModelProxy`
- it contributes a `chatSessions` type `openai-codex`

Local references:
- [package.json](</C:/Users/xinby/.vscode/extensions/openai.chatgpt-26.417.40842-win32-x64/package.json:30>)
- [package.json](</C:/Users/xinby/.vscode/extensions/openai.chatgpt-26.417.40842-win32-x64/package.json:261>)

Its bundled extension code also shows internal notification handling such as `turn/completed`, but this appears to be for the extension's own internal use rather than a documented third-party integration point.

Local reference:
- [out/extension.js](</C:/Users/xinby/.vscode/extensions/openai.chatgpt-26.417.40842-win32-x64/out/extension.js:299>)

Implication:
- We can rely on public commands and observable public surfaces.
- We should not treat internal bundled notifications as a supported API.

### 4. The installed Codex extension already treats Windows and WSL separately

The local Codex extension exposes a Windows/WSL-related setting:
- `chatgpt.runCodexInWindowsSubsystemForLinux`

Local reference:
- [package.json](</C:/Users/xinby/.vscode/extensions/openai.chatgpt-26.417.40842-win32-x64/package.json:165>)

Implication:
- Even the official extension acknowledges Windows/WSL split behavior.
- This reinforces the need to keep Windows support claims conservative.

## Product decision for Windows mainline

For the current Windows-first BuddyParallel product path:

- Support **Codex presence / focus / activity mirroring** on the board.
- Do **not** claim native Codex approval bridging yet.
- Do **not** rely on private webview hooks or bundled internal notifications as the mainline path.
- Keep Codex native approval as a tracked research item until a stable, supported integration surface exists.

## Safe wording for current capability

On Windows, BuddyParallel currently supports:
- Codex task presence
- Codex focus awareness
- Codex recent document update pulses

On Windows, BuddyParallel does not currently support:
- Codex native permission / approval prompts on the board
- Codex internal turn / tool lifecycle mirroring through a supported API

## Recommended next step

Continue investing in:
- Codex status mirroring quality
- board-side UX for Codex presence
- clear product docs about the current Windows capability boundary

Do not build mainline product behavior on:
- reverse-engineered internal notification hooks
- proposed APIs as the only integration path
- unsupported Windows Codex hooks assumptions
