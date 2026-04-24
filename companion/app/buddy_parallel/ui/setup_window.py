from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from buddy_parallel.services.board_setup import (
    BoardCandidate,
    FirmwareBundle,
    FlashResult,
    AUTO_BOARD_ID,
    board_label,
    choose_board_profile,
    find_firmware_bundle,
    flash_board,
    list_board_candidates,
    normalize_board_id,
    save_board_port,
    supported_board_profiles,
)


class SetupWindow:
    def __init__(self) -> None:
        self._root: tk.Tk | None = None
        self._port_var: tk.StringVar | None = None
        self._board_var: tk.StringVar | None = None
        self._status_var: tk.StringVar | None = None
        self._firmware_var: tk.StringVar | None = None
        self._candidate_by_label: dict[str, BoardCandidate] = {}
        self._profile_by_label: dict[str, str] = {}
        self._bundle: FirmwareBundle | None = None
        self._queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._busy = False
        self._refresh_button: ttk.Button | None = None
        self._flash_button: ttk.Button | None = None
        self._save_button: ttk.Button | None = None
        self._port_combo: ttk.Combobox | None = None
        self._log: tk.Text | None = None

    def show(self) -> None:
        root = tk.Tk()
        self._root = root
        root.title("BuddyParallel Board Setup")
        root.geometry("760x520")
        root.minsize(700, 460)
        self._configure_style(root)

        self._port_var = tk.StringVar(master=root, value="")
        self._board_var = tk.StringVar(master=root, value="Auto Detect")
        self._status_var = tk.StringVar(master=root, value="Looking for a board...")
        self._firmware_var = tk.StringVar(master=root, value="Checking bundled firmware...")

        outer = ttk.Frame(root, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="BuddyParallel Board Setup", style="Heading.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Connect the board over USB, then save an existing BuddyParallel board or flash this beta firmware.",
            style="Muted.TLabel",
            wraplength=680,
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        device_group = ttk.LabelFrame(outer, text="Device", padding=10)
        device_group.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        device_group.columnconfigure(1, weight=1)
        self._profile_by_label = {"Auto Detect": AUTO_BOARD_ID}
        self._profile_by_label.update({profile.display_name: profile.id for profile in supported_board_profiles()})
        ttk.Label(device_group, text="Board Type", width=14).grid(row=0, column=0, sticky="w", padx=(0, 10))
        board_combo = ttk.Combobox(device_group, textvariable=self._board_var, values=list(self._profile_by_label), state="readonly")
        board_combo.grid(row=0, column=1, sticky="ew")
        board_combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh())
        ttk.Label(device_group, text="Serial Port", width=14).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(8, 0))
        self._port_combo = ttk.Combobox(device_group, textvariable=self._port_var, state="readonly")
        self._port_combo.grid(row=1, column=1, sticky="ew", pady=(8, 0))
        self._refresh_button = ttk.Button(device_group, text="Refresh", command=self._refresh)
        self._refresh_button.grid(row=1, column=2, padx=(8, 0), pady=(8, 0))
        ttk.Label(device_group, textvariable=self._status_var, style="Muted.TLabel", wraplength=640).grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(8, 0),
        )

        firmware_group = ttk.LabelFrame(outer, text="Firmware", padding=10)
        firmware_group.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        firmware_group.columnconfigure(0, weight=1)
        ttk.Label(firmware_group, textvariable=self._firmware_var, style="Muted.TLabel", wraplength=680).grid(
            row=0,
            column=0,
            sticky="w",
        )

        log_group = ttk.LabelFrame(outer, text="Progress", padding=10)
        log_group.grid(row=3, column=0, sticky="nsew")
        log_group.columnconfigure(0, weight=1)
        log_group.rowconfigure(0, weight=1)
        self._log = tk.Text(log_group, height=12, wrap="word", state="disabled")
        self._log.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_group, orient="vertical", command=self._log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._log.configure(yscrollcommand=scrollbar.set)

        footer = ttk.Frame(outer)
        footer.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        footer.columnconfigure(0, weight=1)
        self._save_button = ttk.Button(footer, text="Save Port", command=self._save_selected_port)
        self._save_button.grid(row=0, column=1, padx=(8, 0))
        self._flash_button = ttk.Button(footer, text="Flash Firmware", command=self._confirm_flash)
        self._flash_button.grid(row=0, column=2, padx=(8, 0))
        ttk.Button(footer, text="Close", command=root.destroy).grid(row=0, column=3, padx=(8, 0))

        self._set_busy(False)
        self._refresh()
        root.after(100, self._drain_queue)
        root.mainloop()

    def _refresh(self) -> None:
        board_id = self._selected_board_id()
        self._run_background("refresh", lambda: self._load_setup_state(board_id))

    def _load_setup_state(self, board_id: str) -> tuple[list[BoardCandidate], FirmwareBundle, str]:
        candidates = list_board_candidates(probe_status=True)
        profile = choose_board_profile(board_id, candidates=candidates)
        bundle = find_firmware_bundle(board_id=profile.id)
        return candidates, bundle, profile.id

    def _apply_setup_state(self, result: tuple[list[BoardCandidate], FirmwareBundle, str]) -> None:
        candidates, bundle, resolved_board_id = result
        self._bundle = bundle
        self._candidate_by_label = {candidate.label: candidate for candidate in candidates}
        labels = list(self._candidate_by_label)

        assert self._port_combo is not None
        assert self._port_var is not None
        self._port_combo.configure(values=labels)
        if labels and not self._port_var.get():
            buddy = next((candidate for candidate in candidates if candidate.is_buddy_parallel), None)
            self._port_var.set((buddy.label if buddy is not None else labels[0]))

        assert self._status_var is not None
        resolved_label = board_label(resolved_board_id)
        if not candidates:
            self._status_var.set("No serial board found. Try another USB cable or install the board's USB serial driver.")
        elif any(candidate.is_buddy_parallel for candidate in candidates):
            self._status_var.set(f"BuddyParallel firmware is already responding. Save the port and start using the app. Board type: {resolved_label}.")
        else:
            self._status_var.set(f"A serial board was found, but it is not answering as BuddyParallel yet. Flash target: {resolved_label}.")

        assert self._firmware_var is not None
        if bundle.available:
            self._firmware_var.set(f"{bundle.profile.display_name} firmware bundle ready: {bundle.root}")
        else:
            missing = ", ".join(path.name for path in bundle.missing_files)
            self._firmware_var.set(f"{bundle.profile.display_name} firmware bundle is incomplete: {missing}")

        self._update_actions()

    def _save_selected_port(self) -> None:
        candidate = self._selected_candidate()
        port = candidate.port if candidate is not None else self._selected_label().strip()
        if not port:
            messagebox.showerror("BuddyParallel", "Select a serial port first.")
            return
        board_id = self._selected_board_id()
        save_board_port(port, board_id=board_id)
        self._append_log(f"Saved {port} ({board_id}) to BuddyParallel config.")
        messagebox.showinfo("BuddyParallel", f"Saved {port}.")

    def _confirm_flash(self) -> None:
        candidate = self._selected_candidate()
        port = candidate.port if candidate is not None else self._selected_label().strip()
        if not port:
            messagebox.showerror("BuddyParallel", "Select a serial port first.")
            return
        if self._bundle is None or not self._bundle.available:
            messagebox.showerror("BuddyParallel", "The firmware bundle is incomplete.")
            return
        confirmed = messagebox.askyesno(
            "BuddyParallel",
            "This will replace the firmware on the connected board. Continue?",
        )
        if not confirmed:
            return
        board_id = self._selected_board_id()
        self._run_background("flash", lambda: flash_board(port=port, board_id=board_id, progress=self._queue_progress))

    def _handle_flash_result(self, result: FlashResult) -> None:
        self._append_log(result.message)
        if result.ok:
            save_board_port(result.port, board_id=result.board_id or self._selected_board_id())
            messagebox.showinfo("BuddyParallel", "Board flashed and saved.")
            self._refresh()
            return
        messagebox.showwarning("BuddyParallel", result.message)

    def _selected_label(self) -> str:
        assert self._port_var is not None
        return self._port_var.get()

    def _selected_candidate(self) -> BoardCandidate | None:
        return self._candidate_by_label.get(self._selected_label())

    def _selected_board_id(self) -> str:
        if self._board_var is None:
            return AUTO_BOARD_ID
        return normalize_board_id(self._profile_by_label.get(self._board_var.get(), AUTO_BOARD_ID))

    def _run_background(self, kind: str, work) -> None:
        if self._busy:
            return
        self._set_busy(True)

        def target() -> None:
            try:
                self._queue.put((kind, work()))
            except Exception as exc:
                self._queue.put(("error", exc))

        threading.Thread(target=target, name=f"bp-setup-{kind}", daemon=True).start()

    def _queue_progress(self, message: str) -> None:
        self._queue.put(("progress", message))

    def _drain_queue(self) -> None:
        while True:
            try:
                kind, payload = self._queue.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                self._append_log(str(payload))
                continue
            if kind == "refresh":
                self._apply_setup_state(payload)  # type: ignore[arg-type]
                self._set_busy(False)
                continue
            if kind == "flash":
                self._set_busy(False)
                self._handle_flash_result(payload)  # type: ignore[arg-type]
                continue
            if kind == "error":
                self._append_log(str(payload))
                messagebox.showerror("BuddyParallel", str(payload))
                self._set_busy(False)
        if self._root is not None:
            self._root.after(100, self._drain_queue)

    def _append_log(self, message: str) -> None:
        if self._log is None:
            return
        self._log.configure(state="normal")
        self._log.insert("end", message.rstrip() + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._update_actions()

    def _update_actions(self) -> None:
        has_port = bool(self._selected_label()) if self._port_var is not None else False
        has_bundle = self._bundle is not None and self._bundle.available
        state = "disabled" if self._busy else "normal"
        if self._refresh_button is not None:
            self._refresh_button.configure(state=state)
        if self._save_button is not None:
            self._save_button.configure(state=state if has_port else "disabled")
        if self._flash_button is not None:
            self._flash_button.configure(state=state if has_port and has_bundle else "disabled")

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


def main() -> None:
    SetupWindow().show()


if __name__ == "__main__":
    main()
