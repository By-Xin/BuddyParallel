from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from buddy_parallel.runtime.config import AppConfig, ConfigStore, validate_config


class SettingsWindow:
    def __init__(self, config_store: ConfigStore | None = None) -> None:
        self._config_store = config_store or ConfigStore()

    def show(self) -> None:
        config = self._config_store.load()
        root = tk.Tk()
        root.title("BuddyParallel Settings")
        root.geometry("920x700")
        root.minsize(860, 640)
        self._configure_style(root)

        fields = {
            "transport_mode": tk.StringVar(master=root, value=config.transport_mode),
            "serial_port": tk.StringVar(master=root, value=config.serial_port),
            "serial_baud": tk.StringVar(master=root, value=str(config.serial_baud)),
            "ble_device_name": tk.StringVar(master=root, value=config.ble_device_name),
            "notice_transport": tk.StringVar(master=root, value=config.notice_transport),
            "notice_mqtt_url": tk.StringVar(master=root, value=config.notice_mqtt_url),
            "notice_mqtt_topic": tk.StringVar(master=root, value=config.notice_mqtt_topic),
            "notice_mqtt_username": tk.StringVar(master=root, value=config.notice_mqtt_username),
            "notice_mqtt_password": tk.StringVar(master=root, value=config.notice_mqtt_password),
            "notice_mqtt_client_id": tk.StringVar(master=root, value=config.notice_mqtt_client_id),
            "notice_mqtt_keepalive_seconds": tk.StringVar(master=root, value=str(config.notice_mqtt_keepalive_seconds)),
            "weather_location_query": tk.StringVar(master=root, value=config.weather_location_query),
            "weather_refresh_minutes": tk.StringVar(master=root, value=str(config.weather_refresh_minutes)),
            "bot_token": tk.StringVar(master=root, value=config.bot_token),
            "allowed_chat_id": tk.StringVar(master=root, value=config.allowed_chat_id),
            "poll_interval_seconds": tk.StringVar(master=root, value=str(config.poll_interval_seconds)),
            "feishu_app_id": tk.StringVar(master=root, value=config.feishu_app_id),
            "feishu_app_secret": tk.StringVar(master=root, value=config.feishu_app_secret),
            "feishu_allowed_chat_id": tk.StringVar(master=root, value=config.feishu_allowed_chat_id),
            "hook_server_port": tk.StringVar(master=root, value=str(config.hook_server_port)),
            "api_server_port": tk.StringVar(master=root, value=str(config.api_server_port)),
            "owner_name": tk.StringVar(master=root, value=config.owner_name),
            "device_name": tk.StringVar(master=root, value=config.device_name),
            "birthday_mmdd": tk.StringVar(master=root, value=config.birthday_mmdd),
            "birthday_name": tk.StringVar(master=root, value=config.birthday_name),
            "update_manifest_url": tk.StringVar(master=root, value=config.update_manifest_url),
        }
        auto_start = tk.BooleanVar(master=root, value=config.auto_start)
        weather_enabled = tk.BooleanVar(master=root, value=config.weather_enabled)
        festive_themes_enabled = tk.BooleanVar(master=root, value=config.festive_themes_enabled)

        outer = ttk.Frame(root, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="BuddyParallel Settings", style="Heading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Traditional grouped settings only. Live status and quick actions stay in the separate BuddyParallel window.",
            style="Muted.TLabel",
            wraplength=760,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        notebook = ttk.Notebook(outer)
        notebook.grid(row=1, column=0, sticky="nsew")

        general_tab = ttk.Frame(notebook, padding=12)
        notifications_tab = ttk.Frame(notebook, padding=12)
        weather_tab = ttk.Frame(notebook, padding=12)
        advanced_tab = ttk.Frame(notebook, padding=12)
        for tab in (general_tab, notifications_tab, weather_tab, advanced_tab):
            tab.columnconfigure(0, weight=1)

        notebook.add(general_tab, text="General")
        notebook.add(notifications_tab, text="Notifications")
        notebook.add(weather_tab, text="Weather && Themes")
        notebook.add(advanced_tab, text="Advanced")

        transport_group = self._group(
            general_tab,
            0,
            "Device & Transport",
            "Choose the transport mode first, then fill only the serial or BLE details that mode uses.",
        )
        self._row(
            transport_group,
            0,
            "Transport Mode",
            ttk.Combobox(
                transport_group,
                textvariable=fields["transport_mode"],
                values=["auto", "serial", "ble", "mock"],
                state="readonly",
            ),
        )
        serial_group = ttk.LabelFrame(transport_group, text="Serial", padding=8)
        serial_group.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 8))
        serial_group.columnconfigure(1, weight=1)
        self._row(serial_group, 0, "Serial Port", ttk.Entry(serial_group, textvariable=fields["serial_port"]))
        self._row(serial_group, 1, "Serial Baud", ttk.Entry(serial_group, textvariable=fields["serial_baud"]))

        ble_group = ttk.LabelFrame(transport_group, text="Bluetooth", padding=8)
        ble_group.grid(row=3, column=0, columnspan=2, sticky="ew")
        ble_group.columnconfigure(1, weight=1)
        self._row(ble_group, 0, "BLE Device Name", ttk.Entry(ble_group, textvariable=fields["ble_device_name"]))

        identity_group = self._group(
            general_tab,
            1,
            "Identity",
            "These values are used in greetings, device handshakes, and companion labels.",
        )
        self._row(identity_group, 0, "Owner Name", ttk.Entry(identity_group, textvariable=fields["owner_name"]))
        self._row(identity_group, 1, "Device Name", ttk.Entry(identity_group, textvariable=fields["device_name"]))
        ttk.Checkbutton(identity_group, text="Launch at startup", variable=auto_start).grid(
            row=3,
            column=1,
            sticky="w",
            pady=(8, 0),
        )

        source_group = self._group(
            notifications_tab,
            0,
            "Notice Source",
            "Only the currently selected source stays visible below so the page remains compact.",
        )
        self._row(
            source_group,
            0,
            "Source",
            ttk.Combobox(
                source_group,
                textvariable=fields["notice_transport"],
                values=["telegram", "mqtt", "feishu"],
                state="readonly",
            ),
        )

        telegram_group = ttk.LabelFrame(source_group, text="Telegram", padding=8)
        telegram_group.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 8))
        telegram_group.columnconfigure(1, weight=1)
        self._row(telegram_group, 0, "Bot Token", ttk.Entry(telegram_group, textvariable=fields["bot_token"]))
        self._row(telegram_group, 1, "Allowed Chat ID", ttk.Entry(telegram_group, textvariable=fields["allowed_chat_id"]))
        self._row(
            telegram_group,
            2,
            "Poll Seconds",
            ttk.Entry(telegram_group, textvariable=fields["poll_interval_seconds"]),
        )

        feishu_group = ttk.LabelFrame(source_group, text="Feishu", padding=8)
        feishu_group.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        feishu_group.columnconfigure(1, weight=1)
        self._row(feishu_group, 0, "App ID", ttk.Entry(feishu_group, textvariable=fields["feishu_app_id"]))
        self._row(
            feishu_group,
            1,
            "App Secret",
            ttk.Entry(feishu_group, textvariable=fields["feishu_app_secret"], show="*"),
        )
        self._row(
            feishu_group,
            2,
            "Allowed Chat ID",
            ttk.Entry(feishu_group, textvariable=fields["feishu_allowed_chat_id"]),
        )

        mqtt_group = ttk.LabelFrame(source_group, text="MQTT", padding=8)
        mqtt_group.grid(row=4, column=0, columnspan=2, sticky="ew")
        mqtt_group.columnconfigure(1, weight=1)
        self._row(mqtt_group, 0, "Broker URL", ttk.Entry(mqtt_group, textvariable=fields["notice_mqtt_url"]))
        self._row(mqtt_group, 1, "Topic", ttk.Entry(mqtt_group, textvariable=fields["notice_mqtt_topic"]))
        self._row(mqtt_group, 2, "Username", ttk.Entry(mqtt_group, textvariable=fields["notice_mqtt_username"]))
        self._row(
            mqtt_group,
            3,
            "Password",
            ttk.Entry(mqtt_group, textvariable=fields["notice_mqtt_password"], show="*"),
        )
        self._row(mqtt_group, 4, "Client ID", ttk.Entry(mqtt_group, textvariable=fields["notice_mqtt_client_id"]))
        self._row(
            mqtt_group,
            5,
            "Keepalive Seconds",
            ttk.Entry(mqtt_group, textvariable=fields["notice_mqtt_keepalive_seconds"]),
        )

        weather_group = self._group(
            weather_tab,
            0,
            "Weather Sync",
            "Enable weather only if you want current conditions forwarded into the companion.",
        )
        ttk.Checkbutton(weather_group, text="Enable weather sync", variable=weather_enabled).grid(
            row=1,
            column=1,
            sticky="w",
        )
        weather_location_entry = ttk.Entry(weather_group, textvariable=fields["weather_location_query"])
        weather_refresh_entry = ttk.Entry(weather_group, textvariable=fields["weather_refresh_minutes"])
        self._row(weather_group, 1, "Weather Location", weather_location_entry)
        self._row(weather_group, 2, "Refresh Minutes", weather_refresh_entry)

        themes_group = self._group(
            weather_tab,
            1,
            "Themes & Celebrations",
            "Christmas and New Year are built in. Birthday accepts MM-DD or YYYY-MM-DD.",
        )
        ttk.Checkbutton(themes_group, text="Enable special day themes", variable=festive_themes_enabled).grid(
            row=1,
            column=1,
            sticky="w",
        )
        self._row(themes_group, 1, "Birthday", ttk.Entry(themes_group, textvariable=fields["birthday_mmdd"]))
        self._row(themes_group, 2, "Greeting Name", ttk.Entry(themes_group, textvariable=fields["birthday_name"]))

        updates_group = self._group(
            weather_tab,
            2,
            "Updates",
            "Leave the manifest URL blank if you are not using manual update checks yet.",
        )
        self._row(
            updates_group,
            0,
            "Update Manifest URL",
            ttk.Entry(updates_group, textvariable=fields["update_manifest_url"]),
        )

        ports_group = self._group(
            advanced_tab,
            0,
            "Local Services",
            "These ports are only for local bridges and hook traffic on this machine.",
        )
        self._row(ports_group, 0, "Hook Server Port", ttk.Entry(ports_group, textvariable=fields["hook_server_port"]))
        self._row(ports_group, 1, "API Server Port", ttk.Entry(ports_group, textvariable=fields["api_server_port"]))

        note_group = self._group(
            advanced_tab,
            1,
            "Boundary",
            "Settings stays as a grouped configuration form. Live status, pet selection, and hardware controls remain in BuddyParallel and tray.",
        )
        ttk.Label(note_group, text="This keeps the settings window short and predictable.", style="Muted.TLabel").grid(
            row=1,
            column=0,
            sticky="w",
        )

        footer = ttk.Frame(outer)
        footer.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(
            footer,
            text="Save writes config immediately. The tray companion will reload automatically.",
            style="Muted.TLabel",
        ).grid(row=0, column=0, sticky="w")

        def build_config() -> AppConfig:
            return validate_config(
                AppConfig(
                    transport_mode=fields["transport_mode"].get().strip() or "auto",
                    serial_port=fields["serial_port"].get().strip(),
                    serial_baud=int(fields["serial_baud"].get().strip() or "115200"),
                    ble_device_name=fields["ble_device_name"].get().strip(),
                    notice_transport=fields["notice_transport"].get().strip() or "telegram",
                    notice_mqtt_url=fields["notice_mqtt_url"].get().strip(),
                    notice_mqtt_topic=fields["notice_mqtt_topic"].get().strip() or "devices/mcu1/notice",
                    notice_mqtt_username=fields["notice_mqtt_username"].get().strip(),
                    notice_mqtt_password=fields["notice_mqtt_password"].get(),
                    notice_mqtt_client_id=fields["notice_mqtt_client_id"].get().strip(),
                    notice_mqtt_keepalive_seconds=max(10, int(fields["notice_mqtt_keepalive_seconds"].get().strip() or "60")),
                    weather_enabled=bool(weather_enabled.get()),
                    weather_location_query=fields["weather_location_query"].get().strip(),
                    weather_refresh_minutes=max(1, int(fields["weather_refresh_minutes"].get().strip() or "30")),
                    bot_token=fields["bot_token"].get().strip(),
                    allowed_chat_id=fields["allowed_chat_id"].get().strip(),
                    poll_interval_seconds=max(1, int(fields["poll_interval_seconds"].get().strip() or "3")),
                    feishu_app_id=fields["feishu_app_id"].get().strip(),
                    feishu_app_secret=fields["feishu_app_secret"].get().strip(),
                    feishu_allowed_chat_id=fields["feishu_allowed_chat_id"].get().strip(),
                    hook_server_port=int(fields["hook_server_port"].get().strip() or "43111"),
                    api_server_port=int(fields["api_server_port"].get().strip() or "43112"),
                    owner_name=fields["owner_name"].get().strip(),
                    device_name=fields["device_name"].get().strip() or "BuddyParallel",
                    festive_themes_enabled=bool(festive_themes_enabled.get()),
                    birthday_mmdd=fields["birthday_mmdd"].get().strip(),
                    birthday_name=fields["birthday_name"].get().strip(),
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

        ttk.Button(footer, text="Save", command=save).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(footer, text="Close", command=root.destroy).grid(row=0, column=2, padx=(8, 0))

        def sync_transport_fields(*_args) -> None:
            mode = fields["transport_mode"].get().strip() or "auto"
            if mode in {"auto", "serial"}:
                serial_group.grid()
            else:
                serial_group.grid_remove()
            if mode in {"auto", "ble"}:
                ble_group.grid()
            else:
                ble_group.grid_remove()

        def sync_notice_fields(*_args) -> None:
            current = fields["notice_transport"].get().strip() or "telegram"
            telegram_group.grid_remove()
            feishu_group.grid_remove()
            mqtt_group.grid_remove()
            if current == "telegram":
                telegram_group.grid()
            elif current == "feishu":
                feishu_group.grid()
            else:
                mqtt_group.grid()

        def sync_weather_fields(*_args) -> None:
            enabled = bool(weather_enabled.get())
            _set_widget_state(weather_location_entry, enabled)
            _set_widget_state(weather_refresh_entry, enabled)

        fields["transport_mode"].trace_add("write", sync_transport_fields)
        fields["notice_transport"].trace_add("write", sync_notice_fields)
        weather_enabled.trace_add("write", sync_weather_fields)

        sync_transport_fields()
        sync_notice_fields()
        sync_weather_fields()
        root.mainloop()

    @staticmethod
    def _group(parent: ttk.Frame, row: int, title: str, description: str) -> ttk.LabelFrame:
        group = ttk.LabelFrame(parent, text=title, padding=10)
        group.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        group.columnconfigure(1, weight=1)
        ttk.Label(group, text=description, style="Muted.TLabel", wraplength=760).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 8),
        )
        return group

    @staticmethod
    def _row(parent: ttk.Frame, row: int, label: str, widget: tk.Widget) -> None:
        ttk.Label(parent, text=label, width=18).grid(row=row + 1, column=0, sticky="w", padx=(0, 10), pady=4)
        widget.grid(row=row + 1, column=1, sticky="ew", pady=4)

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
        style.configure("Heading.TLabel", font=("Segoe UI Semibold", 14))
        style.configure("Muted.TLabel", foreground="#555555")


def _set_widget_state(widget: tk.Widget, enabled: bool) -> None:
    widget.configure(state="normal" if enabled else "disabled")


def main() -> None:
    SettingsWindow().show()


if __name__ == "__main__":
    main()
