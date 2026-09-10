from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path
from typing import Any

from .artifact import CapabilityArtifact, Parameter, Step


class DesktopRecorder:
    """Record screen actions without importing or inspecting the target app."""

    def __init__(self, evidence_dir: str | Path = "artifacts/evidence"):
        self.evidence_dir = Path(evidence_dir)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.steps: list[Step] = []
        self._paused = False
        self._stopped = False
        self._mouse_listener: Any = None
        self._keyboard_thread: Any = None
        self._keyboard_run_loop: Any = None
        self._keyboard_ready = threading.Event()
        self._keyboard_error: Exception | None = None

    @property
    def paused(self) -> bool:
        return self._paused

    def pause(self) -> None:
        self._paused = True
        print("Recording paused.")

    def resume(self) -> None:
        self._paused = False
        print("Recording resumed.")

    def stop(self) -> None:
        self._stopped = True

    def start(self) -> None:
        try:
            from pynput import mouse
        except ImportError as exc:
            raise RuntimeError("Recording requires pynput. Install requirements.txt first.") from exc

        self._stopped = False
        self._mouse_listener = mouse.Listener(on_click=self._on_click)
        self._mouse_listener.start()
        self._start_keyboard_tap()

    def wait(self) -> None:
        try:
            while not self._stopped:
                time.sleep(0.1)
        finally:
            if self._mouse_listener:
                self._mouse_listener.stop()
            self._stop_keyboard_tap()

    def artifact(self, name: str, goal: str, target: dict[str, str]) -> CapabilityArtifact:
        return CapabilityArtifact(
            name=name,
            goal=goal,
            target=target,
            parameters=[
                Parameter("recorded_inputs", "object", "Values to substitute into typed steps", sensitive=True)
            ],
            outputs=[{"name": "screen_state", "type": "evidence", "description": "Screenshots captured during replay"}],
            steps=self.steps,
            checkpoint={"type": "manual", "description": "Operator-defined final screen checkpoint"},
        )

    def record(self, name: str, goal: str, target: dict[str, str]) -> CapabilityArtifact:
        print("Recording started. F8 pauses, F9 stops, F10 requests human handoff.")
        print("Use the iBanking app normally. Sensitive values are not persisted by default.")
        self.start()
        self.wait()
        return self.artifact(name, goal, target)

    def _on_click(self, x: int, y: int, button: Any, pressed: bool) -> None:
        if pressed and not self._paused:
            self.steps.append(Step(
                id=f"step_{len(self.steps) + 1:03d}",
                action="click",
                target={"strategy": "screen_coordinate", "x": x, "y": y, "button": str(button)},
            ))

    def _on_press(self, key: Any) -> None:
        from pynput.keyboard import Key

        if key == Key.f8:
            self.resume() if self._paused else self.pause()
            return
        if key == Key.f9:
            self.stop()
            return
        if key == Key.f10:
            self._paused = True
            self.steps.append(Step(
                id=f"step_{len(self.steps) + 1:03d}",
                action="handoff",
                target={"strategy": "operator_control"},
                rationale="Operator requested manual control",
            ))
            print("Human handoff recorded. Press F8 to resume, F9 to stop.")
            return
        if not self._paused:
            value = getattr(key, "char", None)
            if value is not None:
                if not self.steps or self.steps[-1].action != "type":
                    self.steps.append(Step(
                        id=f"step_{len(self.steps) + 1:03d}",
                        action="type",
                        target={"strategy": "focused_control"},
                        value="{{input:recorded_inputs}}",
                    ))
            elif key in {Key.enter, Key.tab, Key.backspace, Key.delete, Key.space}:
                self.steps.append(Step(
                    id=f"step_{len(self.steps) + 1:03d}",
                    action="key",
                    target={"strategy": "focused_control"},
                    value={Key.enter: "enter", Key.tab: "tab", Key.backspace: "backspace", Key.delete: "delete", Key.space: "space"}[key],
                ))

    def _start_keyboard_tap(self) -> None:
        self._keyboard_ready.clear()
        self._keyboard_error = None
        self._keyboard_thread = threading.Thread(target=self._keyboard_loop, daemon=True)
        self._keyboard_thread.start()
        self._keyboard_ready.wait(timeout=2)
        if self._keyboard_error:
            raise RuntimeError(str(self._keyboard_error)) from self._keyboard_error
        if not self._keyboard_run_loop:
            raise RuntimeError("Could not start the macOS keyboard event tap.")

    def _keyboard_loop(self) -> None:
        try:
            import Quartz
        except ImportError as exc:
            self._keyboard_error = RuntimeError("Recording requires Quartz support. Install requirements.txt first.")
            self._keyboard_ready.set()
            return

        event_mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)

        def callback(_proxy: Any, event_type: int, event: Any, _refcon: Any) -> Any:
            if event_type == Quartz.kCGEventKeyDown:
                key_code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
                self._on_quartz_key(key_code, event)
            return event

        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            event_mask,
            callback,
            None,
        )
        if tap is None:
            self._keyboard_error = RuntimeError("macOS denied keyboard recording. Enable Accessibility and Input Monitoring for Python.")
            self._keyboard_ready.set()
            return
        source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        self._keyboard_run_loop = Quartz.CFRunLoopGetCurrent()
        self._keyboard_thread = (tap, source)
        Quartz.CFRunLoopAddSource(self._keyboard_run_loop, source, Quartz.kCFRunLoopDefaultMode)
        Quartz.CGEventTapEnable(tap, True)
        self._keyboard_ready.set()
        Quartz.CFRunLoopRun()

    def _stop_keyboard_tap(self) -> None:
        if self._keyboard_run_loop:
            import Quartz

            Quartz.CFRunLoopStop(self._keyboard_run_loop)
        self._keyboard_run_loop = None
        self._keyboard_thread = None

    def _on_quartz_key(self, key_code: int, event: Any) -> None:
        special_keys = {36: "enter", 48: "tab", 51: "backspace", 117: "delete", 49: "space"}
        if key_code == 100:
            self.pause() if not self._paused else self.resume()
            return
        if key_code == 101:
            self.stop()
            return
        if key_code == 109:
            self._paused = True
            self.steps.append(Step(
                id=f"step_{len(self.steps) + 1:03d}",
                action="handoff",
                target={"strategy": "operator_control"},
                rationale="Operator requested manual control",
            ))
            return
        if self._paused:
            return
        if key_code in special_keys:
            self.steps.append(Step(
                id=f"step_{len(self.steps) + 1:03d}",
                action="key",
                target={"strategy": "focused_control"},
                value=special_keys[key_code],
            ))
            return
        character = self._quartz_character(event)
        if character and (not self.steps or self.steps[-1].action != "type"):
            self.steps.append(Step(
                id=f"step_{len(self.steps) + 1:03d}",
                action="type",
                target={"strategy": "focused_control"},
                value="{{input:recorded_inputs}}",
            ))

    @staticmethod
    def _quartz_character(event: Any) -> str:
        import Quartz

        result = Quartz.CGEventKeyboardGetUnicodeString(event, 4, None, None)
        if isinstance(result, tuple):
            return str(result[-1])
        return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Record an agent capability from a live desktop session")
    parser.add_argument("name")
    parser.add_argument("--goal", required=True)
    parser.add_argument("--target", default="iBanking desktop application")
    parser.add_argument("--output", help="Capability output path; defaults to artifacts/capabilities/<name>.json")
    args = parser.parse_args()

    artifact = DesktopRecorder().record(args.name, args.goal, {"surface": "desktop", "entry_point": args.target})
    output = args.output or f"artifacts/capabilities/{args.name}.json"
    artifact.save(output)
    print(f"Saved {len(artifact.steps)} steps to {output}")
    print(json.dumps({"name": artifact.name, "version": artifact.version, "steps": len(artifact.steps)}, indent=2))


if __name__ == "__main__":
    main()