from __future__ import annotations

import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from .artifact import CapabilityArtifact
from .llm import LLMClient
from .recorder import DesktopRecorder
from .replay import DesktopReplayer


ROOT = Path(__file__).resolve().parent.parent
CAPABILITIES_DIR = ROOT / "artifacts/capabilities"


class CustomerDesk(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Desktop Agent")
        self.geometry("1040x700")
        self.minsize(780, 560)
        self.configure(bg="#e8ece9")
        self.values: dict[str, str] = {}
        self.selected_capability: Path | None = None
        self.recorder: DesktopRecorder | None = None
        self.recording_window: tk.Toplevel | None = None
        self._build_styles()
        self._build_ui()

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("App.TFrame", background="#e8ece9")
        style.configure("Header.TFrame", background="#13212a")
        style.configure("Panel.TFrame", background="#fbfaf6")
        style.configure("Title.TLabel", background="#13212a", foreground="#ffffff", font=("Arial", 19, "bold"))
        style.configure("Kicker.TLabel", background="#13212a", foreground="#f2a07d", font=("Arial", 9, "bold"))
        style.configure("Muted.TLabel", background="#13212a", foreground="#b8c6c5", font=("Arial", 10))
        style.configure("Panel.TLabel", background="#fbfaf6", foreground="#17211b", font=("Arial", 15, "bold"))
        style.configure("Field.TLabel", background="#fbfaf6", foreground="#657268", font=("Arial", 9, "bold"))
        style.configure("Dialog.TFrame", background="#fbfaf6")
        style.configure("DialogHeader.TFrame", background="#13212a")
        style.configure("DialogTitle.TLabel", background="#13212a", foreground="#ffffff", font=("Arial", 16, "bold"))
        style.configure("DialogMuted.TLabel", background="#13212a", foreground="#b8c6c5", font=("Arial", 9))
        style.configure("DialogLabel.TLabel", background="#fbfaf6", foreground="#657268", font=("Arial", 9, "bold"))
        style.configure("Primary.TButton", background="#e36f4f", foreground="#ffffff", padding=(16, 10), font=("Arial", 10, "bold"), borderwidth=0)
        style.configure("Record.TButton", background="#e36f4f", foreground="#ffffff", padding=(14, 8), font=("Arial", 10, "bold"), borderwidth=0)
        style.map("Primary.TButton", background=[("active", "#c95238"), ("disabled", "#9ca8a5")])
        style.map("Record.TButton", background=[("active", "#c95238")])

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, style="App.TFrame", padding=24)
        outer.pack(fill="both", expand=True)
        header = ttk.Frame(outer, style="Header.TFrame", padding=(24, 20))
        header.pack(fill="x", pady=(0, 18))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="DESKTOP WORKFLOW CONSOLE", style="Kicker.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Operate through conversation.", style="Title.TLabel").grid(row=1, column=0, sticky="w", pady=(5, 2))
        ttk.Label(header, text="Choose a recorded capability, provide its inputs, and keep the live desktop in view.", style="Muted.TLabel").grid(row=2, column=0, sticky="w")
        ttk.Button(header, text="Record capability", style="Record.TButton", command=self.open_recording_window).grid(row=0, column=1, rowspan=3, padx=(20, 0))

        content = ttk.Frame(outer, style="App.TFrame")
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)

        chat_panel = ttk.Frame(content, style="Panel.TFrame", padding=22)
        chat_panel.grid(row=0, column=0, sticky="nsew")
        chat_panel.rowconfigure(0, weight=1)
        chat_panel.columnconfigure(0, weight=1)
        transcript = ttk.Frame(chat_panel, style="Panel.TFrame")
        transcript.grid(row=0, column=0, sticky="nsew")
        transcript.rowconfigure(0, weight=1)
        transcript.columnconfigure(0, weight=1)
        self.chat = tk.Text(transcript, wrap="word", state="disabled", bg="#fbfaf6", fg="#17211b", relief="flat", padx=14, pady=14, font=("Arial", 12), insertwidth=0)
        self.chat.tag_configure("speaker", font=("Arial", 10, "bold"), foreground="#c95238")
        self.chat.tag_configure("user_body", background="#e4f0ed", lmargin1=12, lmargin2=12, rmargin=12, spacing1=5, spacing3=9)
        self.chat.tag_configure("agent_body", background="#f0eee7", lmargin1=12, lmargin2=12, rmargin=12, spacing1=5, spacing3=9)
        self.chat.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(transcript, orient="vertical", command=self.chat.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.chat.configure(yscrollcommand=scrollbar.set)
        self._add_message("Tell me what you would like to do in the recorded desktop workflows.")
        entry_row = ttk.Frame(chat_panel, style="Panel.TFrame")
        entry_row.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        entry_row.columnconfigure(0, weight=1)
        self.chat_entry = tk.Text(entry_row, height=5, wrap="word", bg="#f1f5f2", fg="#17211b", relief="solid", borderwidth=1, highlightthickness=1, highlightbackground="#c8d2ce", highlightcolor="#e36f4f", padx=12, pady=10, font=("Arial", 12))
        self.chat_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.send_button = ttk.Button(entry_row, text="Send", style="Primary.TButton", command=self.submit_message)
        self.send_button.grid(row=0, column=1)

    def _add_message(self, text: str, user: bool = False) -> None:
        self.chat.configure(state="normal")
        self.chat.insert("end", f"{'You' if user else 'Agent'}:\n", "speaker")
        self.chat.insert("end", f"{text}\n\n", "user_body" if user else "agent_body")
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def submit_message(self) -> None:
        message = self.chat_entry.get("1.0", "end").strip()
        if not message:
            return
        self.chat_entry.delete("1.0", "end")
        self._add_message(message, user=True)
        self.send_button.configure(state="disabled")
        threading.Thread(target=self._extract_in_background, args=(message,), daemon=True).start()

    def _extract_in_background(self, message: str) -> None:
        try:
            extracted = LLMClient().extract_operation(message, self._capability_catalog())
            self.after(0, self._handle_operation, extracted)
        except RuntimeError as exc:
            self.after(0, self._show_error, str(exc))

    def _handle_operation(self, extracted: dict[str, object]) -> None:
        capability = extracted.get("capability")
        artifact_path = self._find_capability(str(capability)) if capability else None
        if artifact_path is None:
            self._add_message(str(extracted.get("reply", "I do not support that operation yet.")))
            self.send_button.configure(state="normal")
            return

        if self.selected_capability != artifact_path:
            self.values = {}
        extracted_values = extracted.get("values", {})
        if isinstance(extracted_values, dict):
            for step_id, value in extracted_values.items():
                if value:
                    self.values[str(step_id)] = str(value)
        self.selected_capability = artifact_path
        typed_steps = self._typed_steps(artifact_path)
        missing = [step.id for step in typed_steps if not self.values.get(step.id, "").strip()]
        reply = str(extracted.get("reply", "Values updated."))
        if missing:
            reply += f"\nMissing: {', '.join(str(value) for value in missing)}"
        self._add_message(reply)
        self.send_button.configure(state="normal")
        if not missing:
            self._confirm_and_replay()

    def _show_error(self, message: str) -> None:
        self._add_message(message)
        self.send_button.configure(state="normal")

    @staticmethod
    def _typed_steps(path: Path) -> list[Any]:
        artifact = CapabilityArtifact.load(path)
        return [
            step for step in artifact.steps
            if step.action == "type" or (step.action == "key" and step.value == "{{input:recorded_inputs}}")
        ]

    def _capability_catalog(self) -> list[dict[str, object]]:
        catalog: list[dict[str, object]] = []
        for path in sorted(CAPABILITIES_DIR.glob("*.json")):
            try:
                artifact = CapabilityArtifact.load(path)
            except (OSError, TypeError, ValueError):
                continue
            catalog.append({
                "capability": path.stem,
                "artifact_name": artifact.name,
                "goal": artifact.goal,
                "input_step_ids": [step.id for step in self._typed_steps(path)],
            })
        if not catalog:
            raise RuntimeError(f"No capability JSON files found in {CAPABILITIES_DIR}.")
        return catalog

    def _find_capability(self, capability: str) -> Path | None:
        requested = Path(capability).stem
        for item in self._capability_catalog():
            if requested in {str(item["capability"]), str(item["artifact_name"])}:
                return CAPABILITIES_DIR / f"{item['capability']}.json"
        return None

    def open_recording_window(self) -> None:
        if self.recording_window and self.recording_window.winfo_exists():
            self.recording_window.focus_force()
            return
        window = tk.Toplevel(self)
        self.recording_window = window
        window.title("Record capability")
        window.geometry("520x390")
        window.configure(bg="#fbfaf6")
        window.transient(self)
        window.grab_set()
        header = ttk.Frame(window, style="DialogHeader.TFrame", padding=(24, 18))
        header.pack(fill="x")
        ttk.Label(header, text="RECORD A WORKFLOW", style="Kicker.TLabel").pack(anchor="w")
        ttk.Label(header, text="Capture a reusable capability", style="DialogTitle.TLabel").pack(anchor="w", pady=(5, 2))
        ttk.Label(header, text="Perform the workflow in the target app, then save it for chat-driven replay.", style="DialogMuted.TLabel").pack(anchor="w")
        frame = ttk.Frame(window, style="Dialog.TFrame", padding=(24, 18, 24, 20))
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="CAPABILITY FILENAME", style="DialogLabel.TLabel").pack(anchor="w")
        filename = ttk.Entry(frame, font=("Arial", 11))
        filename.insert(0, "create_consumer.json")
        filename.pack(fill="x", pady=(5, 13))
        ttk.Label(frame, text="WORKFLOW GOAL", style="DialogLabel.TLabel").pack(anchor="w")
        goal = tk.Text(frame, height=4, wrap="word", bg="#f1f5f2", fg="#17211b", relief="solid", borderwidth=1, highlightthickness=1, highlightbackground="#c8d2ce", highlightcolor="#e36f4f", padx=10, pady=8, font=("Arial", 11))
        goal.insert("1.0", "Create customer and view it")
        goal.pack(fill="both", expand=True, pady=(5, 16))
        controls = ttk.Frame(frame, style="Dialog.TFrame")
        controls.pack(fill="x")
        start = tk.Button(controls, text="Start recording", bg="#f0d8d0", fg="#6b2e20", disabledforeground="#17211b", activebackground="#2e704d", activeforeground="#ffffff", relief="raised", borderwidth=1, highlightthickness=1, highlightbackground="#17211b", padx=12, pady=6, font=("Arial", 10, "bold"), command=lambda: self.start_recording(window, filename, goal, start, pause, stop))
        start.pack(side="left")
        pause = tk.Button(controls, text="Pause", state="disabled", bg="#d7dfdc", fg="#17211b", disabledforeground="#17211b", activebackground="#52625c", activeforeground="#ffffff", relief="raised", borderwidth=1, highlightthickness=1, highlightbackground="#657268", padx=12, pady=6, font=("Arial", 10, "bold"), command=lambda: self.toggle_recording_pause(pause))
        pause.pack(side="left", padx=8)
        stop = tk.Button(controls, text="Stop", state="disabled", bg="#f0d8d0", fg="#6b2e20", disabledforeground="#6b2e20", activebackground="#a9482d", activeforeground="#ffffff", relief="raised", borderwidth=1, highlightthickness=1, highlightbackground="#cc5a33", padx=12, pady=6, font=("Arial", 10, "bold"), command=lambda: self.stop_recording(start, pause, stop))
        stop.pack(side="left")
        window.protocol("WM_DELETE_WINDOW", lambda: self.close_recording_window(window))

    def start_recording(self, window: tk.Toplevel, filename: ttk.Entry, goal: tk.Text, start: ttk.Button, pause: ttk.Button, stop: ttk.Button) -> None:
        name = Path(filename.get().strip()).stem
        if not name or not goal.get("1.0", "end").strip():
            messagebox.showwarning("Recording details", "Provide a JSON filename and goal.", parent=window)
            return
        self.recorder = DesktopRecorder()
        try:
            self.recorder.start()
        except RuntimeError as exc:
            self.recorder = None
            messagebox.showerror("Recording unavailable", str(exc), parent=window)
            return
        start.configure(state="disabled")
        pause.configure(state="normal", text="Pause")
        stop.configure(state="normal")
        threading.Thread(target=self._record_in_background, args=(name, goal.get("1.0", "end").strip(), window, start, pause, stop), daemon=True).start()

    def toggle_recording_pause(self, button: ttk.Button) -> None:
        if not self.recorder:
            return
        if self.recorder.paused:
            self.recorder.resume()
            button.configure(text="Pause")
        else:
            self.recorder.pause()
            button.configure(text="Resume")

    def stop_recording(self, start: tk.Button, pause: tk.Button, stop: tk.Button) -> None:
        if self.recorder:
            self.recorder.stop()
        start.configure(state="normal")
        pause.configure(state="normal", text="Pause")
        stop.configure(state="normal")

    def _record_in_background(self, name: str, goal: str, window: tk.Toplevel, start: ttk.Button, pause: ttk.Button, stop: ttk.Button) -> None:
        try:
            self.recorder.wait()
            artifact = self.recorder.artifact(name, goal, {"surface": "desktop", "entry_point": "iBanking desktop application"})
            path = ROOT / "artifacts/capabilities" / f"{name}.json"
            artifact.save(path)
            self.after(0, self._recording_finished, window, start, pause, stop, path, len(artifact.steps))
        except RuntimeError as exc:
            self.after(0, self._show_error, str(exc))
            self.after(0, lambda: start.configure(state="normal"))

    def _recording_finished(self, window: tk.Toplevel, start: ttk.Button, pause: ttk.Button, stop: ttk.Button, path: Path, steps: int) -> None:
        self._add_message(f"Recording saved: {path}\nSteps recorded: {steps}")
        start.configure(state="normal")
        pause.configure(state="normal", text="Pause")
        stop.configure(state="normal")
        self.recorder = None

    def close_recording_window(self, window: tk.Toplevel) -> None:
        if self.recorder and not self.recorder._stopped:
            messagebox.showwarning("Recording in progress", "Stop the recording before closing this window.", parent=window)
            return
        window.grab_release()
        window.destroy()
        self.recording_window = None

    def _confirm_and_replay(self) -> None:
        if self.selected_capability is None:
            self._add_message("Select a recorded capability by describing the operation.")
            return
        input_steps = self._typed_steps(self.selected_capability)
        if not input_steps:
            self._add_message(
                f"{self.selected_capability.name} contains no recorded input steps. "
                "Re-record this capability while keyboard capture is enabled."
            )
            return
        values = {step.id: self.values.get(step.id, "").strip() for step in input_steps}
        missing = [step_id for step_id, value in values.items() if not value]
        if missing:
            self._add_message(f"Missing: {', '.join(missing)}")
            return
        if not messagebox.askyesno("Confirm desktop replay", f"This will control the live desktop and run {self.selected_capability.stem}. Continue?"):
            return
        self.send_button.configure(state="disabled")
        self._add_message(f"Running {self.selected_capability.stem} replay...")
        threading.Thread(target=self._replay_in_background, args=(self.selected_capability, values), daemon=True).start()

    def _replay_in_background(self, artifact_path: Path, values: dict[str, str]) -> None:
        try:
            artifact = CapabilityArtifact.load(artifact_path)
            input_steps = self._typed_steps(artifact_path)
            inputs: dict[str, Any] = {step.id: values[step.id] for step in input_steps}
            result = DesktopReplayer().replay(artifact, inputs=inputs)
            result.save(ROOT / "artifacts/replay-result.json")
            popup_message = str(result.outputs.get("popup_message", ""))
            if popup_message.strip() == "4":
                popup_message = ""
            self.after(0, self._show_replay_result, result.status, result.error, popup_message)
        except (StopIteration, ValueError, RuntimeError) as exc:
            self.after(0, self._show_error, str(exc))
            self.after(0, lambda: self.send_button.configure(state="normal"))

    def _show_replay_result(self, status: str, error: dict[str, str] | None, popup_message: str) -> None:
        detail = f"{status}: {error.get('message', '')}" if error else status
        if popup_message:
            detail += f"\nPopup message: {popup_message}"
        self._add_message(f"Replay finished: {detail}")
        self.values = {}
        self.selected_capability = None
        self.send_button.configure(state="normal")


def main() -> None:
    CustomerDesk().mainloop()


if __name__ == "__main__":
    main()
