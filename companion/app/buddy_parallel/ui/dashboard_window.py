from __future__ import annotations

import json
import os
import subprocess
import sys
import tkinter as tk
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk

from buddy_parallel.core.hardware_state import brightness_display, parse_hardware_snapshot, pet_choices, pet_display_name
from buddy_parallel.ingest.install_hooks import main as install_hooks_main
from buddy_parallel.runtime.config import CONFIG_PATH, LOG_PATH, RUNTIME_PATH, AppConfig, ConfigStore
from buddy_parallel.runtime.runtime_config import read_runtime_config
from buddy_parallel.runtime.state import RuntimeState, StateStore
from buddy_parallel.services.updates import UpdateChecker


@dataclass(frozen=True)
class DashboardModel:
    status_badge: str
    status_caption: str
    runtime_lines: tuple[str, ...]
    hardware_lines: tuple[str, ...]
    service_lines: tuple[str, ...]
    setup_lines: tuple[str, ...]


def build_dashboard_model(config: AppConfig, runtime: dict | None, state: RuntimeState) -> DashboardModel:
    runtime = runtime if isinstance(runtime, dict) else {}
    heartbeat = runtime.get("heartbeat") if isinstance(runtime.get("heartbeat"), dict) else {}
    transport = str(runtime.get("transport") or "idle")
    total = int(heartbeat.get("total") or 0)
    running = int(heartbeat.get("running") or 0)
    waiting = int(heartbeat.get("waiting") or 0)
    message = str(heartbeat.get("msg") or "No active companion message.")

    runtime_lines = (
        f"Transport: {transport}",
        f"Sessions: {total} total, {running} running, {waiting} waiting",
        f"Activity: {message[:96]}",
    )

    hardware = parse_hardware_snapshot(runtime.get("device_status"))
    if hardware.connected:
        battery = f"{hardware.battery_pct}%" if hardware.battery_pct is not None else "?"
        power = "USB powered" if hardware.usb_powered else "battery powered"
        hardware_lines = (
            f"Device: {hardware.name or config.device_name or 'BuddyParallel'}",
            f"Pet: {pet_display_name(hardware.pet_name)}",
            f"Battery: {battery} ({power})",
            f"Controls: brightness {brightness_display(hardware.brightness)}, sound {_on_off_label(hardware.sound_enabled)}, led {_on_off_label(hardware.led_enabled)}",
        )
    else:
        target_port = str(runtime.get("device_port") or config.serial_port or "auto")
        hardware_lines = (
            "Device: not connected",
            f"Mode: {config.transport_mode}",
            f"Target port: {target_port}",
            "Use the tray Hardware menu when you want to refresh or switch ports.",
        )

    notice_detail = _notice_status_line(config, state)
    if config.weather_enabled:
        location = state.weather_location_name or config.weather_location_query or "not set"
        weather_detail = state.last_weather_error or state.last_weather_summary or "idle"
        weather_prefix = "Weather error" if state.last_weather_error else "Weather"
        weather_line = f"{weather_prefix}: {location} | {weather_detail}"
    else:
        weather_line = "Weather: off"

    service_lines = (
        notice_detail,
        weather_line,
        f"Local API: 127.0.0.1:{config.api_server_port} | Hook server: 127.0.0.1:{config.hook_server_port}",
    )

    setup_lines = (
        f"Transport preference: {config.transport_mode}",
        f"Notice source: {config.notice_transport}",
        f"Weather sync: {'on' if config.weather_enabled else 'off'}",
        f"Launch at startup: {'on' if config.auto_start else 'off'}",
    )

    active = transport not in {"", "idle", "mock"} or total > 0 or hardware.connected
    status_badge = "Live" if active else "Idle"
    if hardware.connected:
        status_caption = "Device connected and companion status is streaming."
    elif active:
        status_caption = "Companion is active, but hardware is not currently connected."
    else:
        status_caption = "Companion is idle. Open Settings if you want to change transport or notice sources."

    return DashboardModel(
        status_badge=status_badge,
        status_caption=status_caption,
        runtime_lines=runtime_lines,
        hardware_lines=hardware_lines,
        service_lines=service_lines,
        setup_lines=setup_lines,
    )


class DashboardWindow:
    def __init__(self, config_store: ConfigStore | None = None, state_store: StateStore | None = None) -> None:
        self._config_store = config_store or ConfigStore()
        self._state_store = state_store or StateStore()
        self._update_checker = UpdateChecker()
        self._root: tk.Tk | None = None
        self._refresh_job: str | None = None
        self._settings_process: subprocess.Popen | None = None
        self._vars: dict[str, tk.StringVar] = {}
        self._hardware_snapshot = parse_hardware_snapshot(None)
        self._brightness_var: tk.StringVar | None = None
        self._pet_var: tk.StringVar | None = None
        self._brightness_box: ttk.Combobox | None = None
        self._pet_box: ttk.Combobox | None = None
        self._apply_brightness_button: ttk.Button | None = None
        self._apply_pet_button: ttk.Button | None = None
        self._toggle_led_button: ttk.Button | None = None
        self._toggle_sound_button: ttk.Button | None = None

    def show(self) -> None:
        root = tk.Tk()
        self._root = root
        self._vars = {
            "status_badge": tk.StringVar(master=root, value="Idle"),
            "status_caption": tk.StringVar(master=root, value="Loading BuddyParallel status..."),
            "summary": tk.StringVar(master=root, value=""),
            "runtime": tk.StringVar(master=root, value=""),
            "hardware": tk.StringVar(master=root, value=""),
            "services": tk.StringVar(master=root, value=""),
            "setup": tk.StringVar(master=root, value=""),
            "refreshed": tk.StringVar(master=root, value="Refreshing..."),
            "controls_note": tk.StringVar(master=root, value="Hardware controls appear here when a device is reachable."),
        }
        self._brightness_var = tk.StringVar(master=root, value="")
        self._pet_var = tk.StringVar(master=root, value="")
        root.title("BuddyParallel")
        root.geometry("940x680")
        root.minsize(860, 620)
        self._configure_style(root)
        self._build_ui(root)
        self._refresh()
        root.protocol("WM_DELETE_WINDOW", self._close)
        root.mainloop()

    def _build_ui(self, root: tk.Tk) -> None:
        outer = ttk.Frame(root, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=3)
        outer.columnconfigure(1, weight=2)
        outer.rowconfigure(1, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)

        ttk.Label(header, text="BuddyParallel", style="Heading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Separated from Settings. This window is only for live status and quick actions.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 2))
        ttk.Label(header, textvariable=self._vars["status_caption"], wraplength=620).grid(row=2, column=0, sticky="w")
        ttk.Label(header, textvariable=self._vars["summary"], style="Muted.TLabel", wraplength=620).grid(
            row=3,
            column=0,
            sticky="w",
            pady=(6, 0),
        )
        ttk.Label(header, textvariable=self._vars["status_badge"], style="Status.TLabel").grid(
            row=0,
            column=1,
            rowspan=2,
            sticky="e",
        )

        left = ttk.Frame(outer)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)

        right = ttk.Frame(outer)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)

        self._build_group(left, 0, "Runtime", "What the companion is doing right now.", self._vars["runtime"])
        self._build_group(left, 1, "Hardware", "Current device connection and control snapshot.", self._vars["hardware"])
        self._build_group(left, 2, "Services", "Notice and weather bridge health.", self._vars["services"])

        self._build_group(right, 0, "Current Setup", "The configuration currently steering the companion.", self._vars["setup"])
        self._build_hardware_controls(right, 1)
        self._build_actions(right, 2)

        footer = ttk.Frame(outer)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Label(footer, textvariable=self._vars["refreshed"], style="Muted.TLabel").pack(anchor="w")

    def _build_group(
        self,
        parent: ttk.Frame,
        row: int,
        title: str,
        description: str,
        variable: tk.StringVar,
    ) -> None:
        group = ttk.LabelFrame(parent, text=title, padding=10)
        group.grid(row=row, column=0, sticky="nsew", pady=(0, 8))
        group.columnconfigure(0, weight=1)
        ttk.Label(group, text=description, style="Muted.TLabel", wraplength=470).grid(row=0, column=0, sticky="w")
        ttk.Separator(group).grid(row=1, column=0, sticky="ew", pady=8)
        ttk.Label(group, textvariable=variable, justify="left", wraplength=500).grid(row=2, column=0, sticky="w")

    def _build_actions(self, parent: ttk.Frame, row: int) -> None:
        actions = ttk.LabelFrame(parent, text="Quick Actions", padding=10)
        actions.grid(row=row, column=0, sticky="nsew")
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        ttk.Label(
            actions,
            text="Simple shortcuts only. Settings, files, and maintenance stay grouped here.",
            style="Muted.TLabel",
            wraplength=320,
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        specs = [
            ("Open Settings", self._open_settings),
            ("Refresh Now", self._refresh),
            ("Open Config", lambda: self._open_path(CONFIG_PATH)),
            ("Open Log", lambda: self._open_path(LOG_PATH)),
            ("Open Runtime", lambda: self._open_path(RUNTIME_PATH)),
            ("Install Hooks", self._install_hooks),
            ("Check Updates", self._check_updates),
            ("Close", self._close),
        ]
        for index, (label, command) in enumerate(specs):
            ttk.Button(actions, text=label, command=command).grid(
                row=(index // 2) + 1,
                column=index % 2,
                sticky="ew",
                padx=(0, 6) if index % 2 == 0 else (6, 0),
                pady=(8, 0),
            )

    def _build_hardware_controls(self, parent: ttk.Frame, row: int) -> None:
        controls = ttk.LabelFrame(parent, text="Hardware Controls", padding=10)
        controls.grid(row=row, column=0, sticky="nsew", pady=(0, 8))
        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(2, weight=0)

        ttk.Label(
            controls,
            text="Live device controls belong here, not in Settings. Use Refresh Hardware Status first if the device was just connected.",
            style="Muted.TLabel",
            wraplength=320,
        ).grid(row=0, column=0, columnspan=3, sticky="w")

        ttk.Button(controls, text="Refresh Hardware Status", command=self._refresh_hardware_status).grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(8, 8),
        )

        brightness_box, apply_brightness_button = self._row_with_button(
            controls,
            2,
            "Brightness",
            self._brightness_var,
            [f"{level}/4" for level in range(5)],
            self._apply_brightness,
            "Apply",
        )
        self._brightness_box = brightness_box
        self._apply_brightness_button = apply_brightness_button

        pet_box, apply_pet_button = self._row_with_button(
            controls,
            3,
            "Pet",
            self._pet_var,
            [],
            self._apply_pet,
            "Apply",
        )
        self._pet_box = pet_box
        self._apply_pet_button = apply_pet_button

        self._toggle_led_button = ttk.Button(controls, text="Toggle LED", command=self._toggle_led)
        self._toggle_led_button.grid(row=4, column=0, sticky="ew", pady=(8, 0), padx=(0, 6))
        self._toggle_sound_button = ttk.Button(controls, text="Toggle Sound", command=self._toggle_sound)
        self._toggle_sound_button.grid(row=4, column=1, sticky="ew", pady=(8, 0))
        ttk.Label(controls, textvariable=self._vars["controls_note"], style="Muted.TLabel", wraplength=320).grid(
            row=5,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(8, 0),
        )

    def _row_with_button(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        variable: tk.StringVar | None,
        values: list[str],
        command,
        button_text: str,
    ) -> tuple[ttk.Combobox, ttk.Button]:
        ttk.Label(parent, text=label, width=12).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
        combo = ttk.Combobox(parent, textvariable=variable, values=values, state="readonly")
        combo.grid(row=row, column=1, sticky="ew", pady=4)
        button = ttk.Button(parent, text=button_text, command=command)
        button.grid(row=row, column=2, sticky="ew", padx=(8, 0), pady=4)
        return combo, button

    def _refresh(self) -> None:
        config = self._config_store.load()
        runtime = read_runtime_config()
        state = self._state_store.load()
        model = build_dashboard_model(config, runtime, state)
        self._hardware_snapshot = parse_hardware_snapshot(runtime.get("device_status") if isinstance(runtime, dict) else None)

        runtime_data = runtime if isinstance(runtime, dict) else {}
        heartbeat = runtime_data.get("heartbeat") if isinstance(runtime_data.get("heartbeat"), dict) else {}
        transport = str(runtime_data.get("transport") or "idle")
        total = int(heartbeat.get("total") or 0)
        notice_compact = _compact_notice_label(config, state)
        weather_compact = _compact_weather_label(config, state)

        self._vars["status_badge"].set(f"Status: {model.status_badge}")
        self._vars["status_caption"].set(model.status_caption)
        self._vars["summary"].set(f"Transport {transport} | Sessions {total} | Notice {notice_compact} | Weather {weather_compact}")
        self._vars["runtime"].set("\n".join(model.runtime_lines))
        self._vars["hardware"].set("\n".join(model.hardware_lines))
        self._vars["services"].set("\n".join(model.service_lines))
        self._vars["setup"].set("\n".join(model.setup_lines))
        self._vars["refreshed"].set("Reads live runtime, state, and config files every 1.5 seconds.")
        self._sync_hardware_controls()

        if self._root is not None:
            if self._refresh_job is not None:
                self._root.after_cancel(self._refresh_job)
            self._refresh_job = self._root.after(1500, self._refresh)

    def _sync_hardware_controls(self) -> None:
        hardware = self._hardware_snapshot
        connected = hardware.connected

        if self._brightness_var is not None:
            self._brightness_var.set(brightness_display(hardware.brightness) if hardware.brightness is not None else "")
        if self._brightness_box is not None:
            self._brightness_box.configure(values=[f"{level}/4" for level in range(5)])
            self._brightness_box.configure(state="readonly" if connected else "disabled")

        pet_options = pet_choices(hardware if connected else None)
        pet_labels = [label for _index, label in pet_options]
        if self._pet_box is not None:
            self._pet_box.configure(values=pet_labels)
            self._pet_box.configure(state="readonly" if connected else "disabled")
        if self._pet_var is not None:
            current_pet = pet_display_name(hardware.pet_name) if hardware.pet_name else ""
            if current_pet and current_pet in pet_labels:
                self._pet_var.set(current_pet)
            elif not current_pet and pet_labels:
                self._pet_var.set(pet_labels[0] if connected else "")
            elif not connected:
                self._pet_var.set("")

        if self._apply_brightness_button is not None:
            self._apply_brightness_button.configure(state="normal" if connected else "disabled")
        if self._apply_pet_button is not None:
            self._apply_pet_button.configure(state="normal" if connected else "disabled")
        if self._toggle_led_button is not None:
            led_text = "Toggle LED" if hardware.led_enabled is None else ("Turn LED Off" if hardware.led_enabled else "Turn LED On")
            self._toggle_led_button.configure(text=led_text, state="normal" if connected else "disabled")
        if self._toggle_sound_button is not None:
            sound_text = "Toggle Sound" if hardware.sound_enabled is None else ("Mute Sound" if hardware.sound_enabled else "Enable Sound")
            self._toggle_sound_button.configure(text=sound_text, state="normal" if connected else "disabled")

        if connected:
            self._vars["controls_note"].set("Device connected. Pet, brightness, LED, and sound can be changed here.")
        else:
            self._vars["controls_note"].set("No live device right now. Connect the device and press Refresh Hardware Status.")

    def _refresh_hardware_status(self) -> None:
        try:
            self._post_api("/hardware/refresh", {})
        except RuntimeError as exc:
            messagebox.showerror("BuddyParallel", str(exc))
            return
        self._refresh()

    def _apply_brightness(self) -> None:
        if self._brightness_var is None:
            return
        text = self._brightness_var.get().strip()
        if not text or "/" not in text:
            messagebox.showerror("BuddyParallel", "Choose a brightness level first.")
            return
        level = int(text.split("/", 1)[0])
        self._send_hardware_command({"cmd": "brightness", "level": level}, f"Brightness set to {text}.")

    def _apply_pet(self) -> None:
        if self._pet_var is None:
            return
        label = self._pet_var.get().strip()
        if not label:
            messagebox.showerror("BuddyParallel", "Choose a pet first.")
            return
        pet_index = None
        for option_index, option_label in pet_choices(self._hardware_snapshot if self._hardware_snapshot.connected else None):
            if option_label == label:
                pet_index = option_index
                break
        if pet_index is None:
            messagebox.showerror("BuddyParallel", "That pet option is not available right now.")
            return
        self._send_hardware_command({"cmd": "species", "idx": pet_index}, f"Pet switched to {label}.")

    def _toggle_led(self) -> None:
        current = self._hardware_snapshot.led_enabled
        if current is None:
            messagebox.showerror("BuddyParallel", "LED state is unavailable right now.")
            return
        self._send_hardware_command({"cmd": "led", "on": not current}, f"LED {'enabled' if not current else 'disabled'}.")

    def _toggle_sound(self) -> None:
        current = self._hardware_snapshot.sound_enabled
        if current is None:
            messagebox.showerror("BuddyParallel", "Sound state is unavailable right now.")
            return
        self._send_hardware_command({"cmd": "sound", "on": not current}, f"Sound {'enabled' if not current else 'muted'}.")

    def _send_hardware_command(self, payload: dict, success_message: str) -> None:
        try:
            self._post_api("/hardware/command", {"command": payload, "refresh": True})
        except RuntimeError as exc:
            messagebox.showerror("BuddyParallel", str(exc))
            return
        self._refresh()
        messagebox.showinfo("BuddyParallel", success_message)

    def _post_api(self, route: str, payload: dict) -> dict:
        config = self._config_store.load()
        url = f"http://127.0.0.1:{config.api_server_port}{route}"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                result = json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not reach the local BuddyParallel API on port {config.api_server_port}.") from exc
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc
        if not isinstance(result, dict):
            raise RuntimeError("Invalid response from local BuddyParallel API.")
        if not result.get("ok", False):
            raise RuntimeError(str(result.get("error") or "Hardware action failed."))
        return result

    def _open_settings(self) -> None:
        if self._settings_process and self._settings_process.poll() is None:
            return
        script = Path(__file__).resolve().parents[3] / "scripts" / "run_settings.py"
        self._settings_process = subprocess.Popen([sys.executable, str(script)])

    def _install_hooks(self) -> None:
        try:
            install_hooks_main()
            messagebox.showinfo("BuddyParallel", "Hooks installed into ~/.claude/settings.json.")
        except Exception as exc:
            messagebox.showerror("BuddyParallel", str(exc))

    def _check_updates(self) -> None:
        info = self._update_checker.check(self._config_store.load())
        if info.error:
            messagebox.showinfo("BuddyParallel", self._update_checker.build_error_message(info.error))
            return
        if not info.available:
            messagebox.showinfo("BuddyParallel", self._update_checker.build_up_to_date_message())
            return
        messagebox.showinfo("BuddyParallel", self._update_checker.build_available_message(info))
        if info.open_url:
            webbrowser.open(info.open_url)

    def _close(self) -> None:
        if self._root is None:
            return
        if self._refresh_job is not None:
            self._root.after_cancel(self._refresh_job)
            self._refresh_job = None
        self._root.destroy()
        self._root = None

    @staticmethod
    def _open_path(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()
        if hasattr(os, "startfile"):
            os.startfile(path)
        else:
            webbrowser.open(path.as_uri())

    @staticmethod
    def _configure_style(root: tk.Tk) -> None:
        style = ttk.Style(root)
        try:
            if "vista" in style.theme_names():
                style.theme_use("vista")
            elif "xpnative" in style.theme_names():
                style.theme_use("xpnative")
        except tk.TclError:
            pass
        style.configure("Heading.TLabel", font=("Segoe UI Semibold", 16))
        style.configure("Muted.TLabel", foreground="#555555")
        style.configure("Status.TLabel", font=("Segoe UI Semibold", 10))


def _notice_status_line(config: AppConfig, state: RuntimeState) -> str:
    if config.notice_transport == "mqtt":
        if state.last_mqtt_error:
            return f"Notice: MQTT error | {state.last_mqtt_error}"
        if state.mqtt_connected or state.last_mqtt_delivery_at > 0:
            detail = state.last_mqtt_message_summary or "connected"
            return f"Notice: MQTT active | {detail}"
        return "Notice: MQTT idle"

    if config.notice_transport == "feishu":
        if state.last_feishu_error:
            return f"Notice: Feishu error | {state.last_feishu_error}"
        if state.feishu_connected or state.last_feishu_delivery_at > 0:
            detail = state.last_feishu_message_summary or "connected"
            return f"Notice: Feishu active | {detail}"
        return "Notice: Feishu idle"

    if state.last_telegram_error:
        return f"Notice: Telegram error | {state.last_telegram_error}"
    if state.last_telegram_delivery_at > 0:
        detail = state.last_telegram_message_summary or "connected"
        return f"Notice: Telegram active | {detail}"
    return "Notice: Telegram idle"


def _compact_notice_label(config: AppConfig, state: RuntimeState) -> str:
    if config.notice_transport == "mqtt":
        if state.last_mqtt_error:
            return "mqtt error"
        return "mqtt active" if state.mqtt_connected or state.last_mqtt_delivery_at > 0 else "mqtt idle"
    if config.notice_transport == "feishu":
        if state.last_feishu_error:
            return "feishu error"
        return "feishu active" if state.feishu_connected or state.last_feishu_delivery_at > 0 else "feishu idle"
    if state.last_telegram_error:
        return "telegram error"
    return "telegram active" if state.last_telegram_delivery_at > 0 else "telegram idle"


def _compact_weather_label(config: AppConfig, state: RuntimeState) -> str:
    if not config.weather_enabled:
        return "off"
    if state.last_weather_error:
        return "error"
    return state.weather_location_name or config.weather_location_query or "enabled"


def _on_off_label(value: bool | None) -> str:
    if value is None:
        return "?"
    return "on" if value else "off"


def main() -> None:
    DashboardWindow().show()


if __name__ == "__main__":
    main()
