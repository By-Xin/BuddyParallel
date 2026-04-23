# BuddyParallel VS Code MVP

This extension is the first slice of the `M7 - VS Code Approval Bridge` milestone.

Current MVP commands:

- `BuddyParallel: Request Board Approval`
- `BuddyParallel: Insert Approved Comment`
- `BuddyParallel: Send Test Notice`

The extension talks to the local BuddyParallel companion over HTTP:

- `POST /events`
- `POST /vscode/permission`

Default companion URL:

- `http://127.0.0.1:43112`

## Local dev

1. Make sure the BuddyParallel tray companion is already running.
2. Open this folder in VS Code as an extension development target.
3. Run the `BuddyParallel: Request Board Approval` command.
4. Approve or deny on the hardware device.

If approved, the extension continues locally. If denied, it cancels the action.
