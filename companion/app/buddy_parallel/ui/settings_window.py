from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from buddy_parallel.ingest.install_hooks import main as install_hooks_main
from buddy_parallel.runtime.config import AppConfig, ConfigStore, validate_config


class SettingsWindow:
    def __init__(self, config_store: ConfigStore | None = None) -> None:
        self._config_store = config_store or ConfigStore()

    def show(self) -> None:
        config = self._config_store.load()
        root = tk.Tk()
        root.title("BuddyParallel Settings")
        root.geometry("540x520")
        root.resizable(False, False)

        fields = {
            "transport_mode": tk.StringVar(value=config.transport_mode),
            "serial_port": tk.StringVar(value=config.serial_port),
            "serial_baud": tk.StringVar(value=str(config.serial_baud)),
            "ble_device_name": tk.StringVar(value=config.ble_device_name),
            "bot_token": tk.StringVar(value=config.bot_token),
            "allowed_chat_id": tk.StringVar(value=config.allowed_chat_id),
            "poll_interval_seconds": tk.StringVar(value=str(config.poll_interval_seconds)),
            "hook_server_port": tk.StringVar(value=str(config.hook_server_port)),
            "api_server_port": tk.StringVar(value=str(config.api_server_port)),
            "owner_name": tk.StringVar(value=config.owner_name),
            "device_name": tk.StringVar(value=config.device_name),
            "update_manifest_url": tk.StringVar(value=config.update_manifest_url),
        }
        auto_start = tk.BooleanVar(value=config.auto_start)

        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)

        labels = [
            ("Transport Mode", "transport_mode"),
            ("Serial Port", "serial_port"),
            ("Serial Baud", "serial_baud"),
            ("BLE Device Name", "ble_device_name"),
            ("Telegram Bot Token", "bot_token"),
            ("Allowed Chat ID", "allowed_chat_id"),
            ("Poll Seconds", "poll_interval_seconds"),
            ("Hook Server Port", "hook_server_port"),
            ("API Server Port", "api_server_port"),
            ("Owner Name", "owner_name"),
            ("Device Name", "device_name"),
            ("Update Manifest URL", "update_manifest_url"),
        ]

        for row, (label, key) in enumerate(labels):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
            if key == "transport_mode":
                widget = ttk.Combobox(
                    frame,
                    textvariable=fields[key],
                    values=["auto", "serial", "ble", "mock"],
                    state="readonly",
                )
            else:
                widget = ttk.Entry(frame, textvariable=fields[key], width=42)
            widget.grid(row=row, column=1, sticky="ew", pady=4)

        ttk.Label(
            frame,
            text="Leave Update Manifest URL blank to disable manual update checks for now.",
            wraplength=340,
            justify="left",
        ).grid(row=len(labels), column=1, sticky="w", pady=(8, 4))

        ttk.Checkbutton(frame, text="Launch at startup (reserved)", variable=auto_start).grid(
            row=len(labels) + 1, column=1, sticky="w", pady=(4, 12)
        )

        button_row = ttk.Frame(frame)
        button_row.grid(row=len(labels) + 2, column=0, columnspan=2, sticky="ew")

        def build_config() -> AppConfig:
            return validate_config(
                AppConfig(
                    transport_mode=fields["transport_mode"].get().strip() or "auto",
                    serial_port=fields["serial_port"].get().strip(),
                    serial_baud=int(fields["serial_baud"].get().strip() or "115200"),
                    ble_device_name=fields["ble_device_name"].get().strip(),
                    bot_token=fields["bot_token"].get().strip(),
                    allowed_chat_id=fields["allowed_chat_id"].get().strip(),
                    poll_interval_seconds=max(1, int(fields["poll_interval_seconds"].get().strip() or "3")),
                    hook_server_port=int(fields["hook_server_port"].get().strip() or "43111"),
                    api_server_port=int(fields["api_server_port"].get().strip() or "43112"),
                    owner_name=fields["owner_name"].get().strip(),
                    device_name=fields["device_name"].get().strip() or "BuddyParallel",
                    auto_start=bool(auto_start.get()),
                    update_manifest_url=fields["update_manifest_url"].get().strip(),
                )
            )

        def save() -> None:
            try:
                cfg = build_config()
                self._config_store.save(cfg)
                messagebox.showinfo("BuddyParallel", "Settings saved. The tray companion will reload automatically.")
            except Exception as exc:
                messagebox.showerror("BuddyParallel", str(exc))

        def install_hooks() -> None:
            try:
                install_hooks_main()
                messagebox.showinfo("BuddyParallel", "Hooks installed into ~/.claude/settings.json.")
            except Exception as exc:
                messagebox.showerror("BuddyParallel", str(exc))

        ttk.Button(button_row, text="Save", command=save).pack(side="left")
        ttk.Button(button_row, text="Install Hooks", command=install_hooks).pack(side="left", padx=8)
        ttk.Button(button_row, text="Close", command=root.destroy).pack(side="right")

        frame.columnconfigure(1, weight=1)
        root.mainloop()


def main() -> None:
    SettingsWindow().show()


if __name__ == "__main__":
    main()
