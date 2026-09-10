from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from .artifact import CapabilityArtifact, ReplayResult


class DesktopReplayer:
    """Deterministic executor for recorded actions with explicit safety gates."""

    def __init__(self, evidence_dir: str | Path = "artifacts/evidence"):
        self.evidence_dir = Path(evidence_dir)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def replay(self, artifact: CapabilityArtifact, inputs: dict[str, Any], confirm_risky: bool = False) -> ReplayResult:
        try:
            import pyautogui
        except ImportError:
            return ReplayResult("failed", artifact.name, 0, error={"code": "missing_dependency", "message": "Replay requires pyautogui."})

        evidence: list[str] = []
        completed = 0
        previous_recorded_input = False
        popup_message = ""
        for step in artifact.steps:
            if step.action not in artifact.policy["allowed_actions"] and step.action != "handoff":
                return self._finish_with_message(
                    "failed", artifact.name, completed,
                    {"code": "policy_block", "message": f"Action {step.action} is not allowlisted."},
                    evidence,
                    target=artifact.target,
                )
            if step.risk != "safe" and not confirm_risky:
                return self._finish_with_message(
                    "blocked", artifact.name, completed,
                    {"code": "confirmation_required", "message": f"Step {step.id} requires confirmation."},
                    evidence,
                    target=artifact.target,
                )
            try:
                is_recorded_input = step.value == "{{input:recorded_inputs}}" and step.action in {"key", "type"}
                has_step_input = step.id in inputs
                if is_recorded_input and previous_recorded_input and not has_step_input:
                    completed += 1
                    continue
                if step.action == "click":
                    pyautogui.click(step.target["x"], step.target["y"])
                elif step.action in {"key", "type"}:
                    value = inputs.get(step.id, step.value or "")
                    if value == "{{input:recorded_inputs}}":
                        value = inputs.get("recorded_inputs", "")
                    if step.action == "key" and value in {"enter", "tab", "backspace", "delete", "space"}:
                        pyautogui.press(value)
                    else:
                        pyautogui.write(str(value))
                elif step.action == "wait":
                    time.sleep(float(step.value or 1))
                elif step.action == "screenshot":
                    path = self.evidence_dir / f"{artifact.name}_{step.id}.png"
                    pyautogui.screenshot().save(path)
                    evidence.append(str(path))
                elif step.action == "handoff":
                    input("Human handoff required. Operate the live app, then press Enter to resume: ")
                completed += 1
                previous_recorded_input = is_recorded_input and not has_step_input
                if step.action == "click":
                    popup_message = self._capture_popup_message(artifact.name, evidence, artifact.target, wait_seconds=0.4) or popup_message
            except Exception as exc:
                failure_evidence = self.evidence_dir / f"{artifact.name}_{step.id}_failure.png"
                try:
                    pyautogui.screenshot().save(failure_evidence)
                    evidence.append(str(failure_evidence))
                except Exception:
                    pass
                return self._finish_with_message(
                    "failed", artifact.name, completed,
                    {"code": "runtime_error", "message": f"{step.id}: {exc}"},
                    evidence,
                    target=artifact.target,
                    popup_message=popup_message,
                )

        return self._finish_with_message("success", artifact.name, completed, None, evidence, artifact.checkpoint, artifact.target, popup_message)

    def _finish_with_message(
        self,
        status: str,
        capability: str,
        completed: int,
        error: dict[str, str] | None,
        evidence: list[str],
        checkpoint: dict[str, str] | None = None,
        target: dict[str, str] | None = None,
        popup_message: str = "",
    ) -> ReplayResult:
        popup_message = popup_message or self._capture_popup_message(capability, evidence, target or {})
        popup_message = self._remove_popup_buttons(popup_message)
        outputs: dict[str, Any] = {}
        if checkpoint is not None:
            outputs["checkpoint"] = checkpoint
        if popup_message:
            outputs["popup_message"] = popup_message
        return ReplayResult(status, capability, completed, outputs=outputs, error=error, evidence=evidence)

    def _capture_popup_message(
        self,
        capability: str,
        evidence: list[str],
        target: dict[str, str] | None = None,
        wait_seconds: float = 1.5,
    ) -> str:
        try:
            import pyautogui
            import pytesseract

            time.sleep(wait_seconds)
            regions = self._popup_regions(target or {})
            if not regions:
                return ""
            messages: list[str] = []
            for region in regions:
                screenshot = pyautogui.screenshot(region=region)
                message = self._remove_popup_buttons(pytesseract.image_to_string(screenshot))
                if message:
                    messages.append(message)
            if not messages:
                return ""
            indicators = ("success", "added", "error", "invalid", "failed", "warning", "ok")
            for message in messages:
                if any(indicator in message.lower() for indicator in indicators):
                    return message
            return messages[0]
        except ImportError as exc:
            return f"Popup text unavailable: install OCR dependencies ({exc})."
        except Exception as exc:
            return f"Popup text could not be read: {exc}"

    @staticmethod
    def _remove_popup_buttons(text: str) -> str:
        button_labels = {"ok", "cancel", "close"}
        kept_lines = []
        for line in text.splitlines():
            cleaned = re.sub(r"[^A-Za-z]+", " ", line).strip().lower()
            if cleaned in button_labels:
                continue
            kept_lines.append(line.rstrip())
        result = "\n".join(kept_lines).strip()
        if not result or re.fullmatch(r"[\d\W]+", result):
            return ""
        return result

    @staticmethod
    def _popup_regions(target: dict[str, str] | None = None) -> list[tuple[int, int, int, int]]:
        """Return dialog-sized macOS window bounds without scanning the full desktop."""
        try:
            import Quartz

            window_list = Quartz.CGWindowListCopyWindowInfo(
                Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
                Quartz.kCGNullWindowID,
            )
            layer_key = getattr(Quartz, "kCGWindowLayer", "kCGWindowLayer")
            owner_key = getattr(Quartz, "kCGWindowOwnerName", "kCGWindowOwnerName")
            title_key = getattr(Quartz, "kCGWindowName", "kCGWindowName")
            bounds_key = getattr(Quartz, "kCGWindowBounds", "kCGWindowBounds")
            import pyautogui

            screen_width, screen_height = pyautogui.size()
            candidates: list[tuple[int, int, int, int, int, int]] = []
            target_text = " ".join(str(value) for value in (target or {}).values()).lower()
            target_tokens = {token for token in re.findall(r"[a-z0-9]+", target_text) if len(token) >= 4}
            for index, window in enumerate(window_list):
                layer = int(window.get(layer_key, 0))
                owner = str(window.get(owner_key, "")).lower()
                title = str(window.get(title_key, "")).lower()
                bounds = window.get(bounds_key, {})
                width = int(bounds.get("Width", 0))
                height = int(bounds.get("Height", 0))
                if width < 120 or height < 70:
                    continue
                if "desktop agent" in title or "chatbot" in title:
                    continue
                target_matches = any(token in owner or token in title for token in target_tokens)
                python_dialog = owner in {"python", "python3"} and width < screen_width * 0.8 and height < screen_height * 0.8
                if target_tokens and not target_matches and not python_dialog:
                    continue
                candidates.append((
                    index,
                    layer,
                    int(bounds.get("X", 0)),
                    int(bounds.get("Y", 0)),
                    width,
                    height,
                ))

            dialog_candidates = [
                (x, y, width, height)
                for _, layer, x, y, width, height in candidates
                if layer > 0 or (width < screen_width * 0.8 and height < screen_height * 0.8)
            ]
            return dialog_candidates
        except (ImportError, TypeError, ValueError):
            return []

    @staticmethod
    def _popup_region() -> tuple[int, int, int, int] | None:
        regions = DesktopReplayer._popup_regions()
        return regions[0] if regions else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a recorded capability")
    parser.add_argument("artifact")
    parser.add_argument("--inputs", default="{}", help="JSON object keyed by recorded step id")
    parser.add_argument("--confirm-risky", action="store_true")
    parser.add_argument("--result", default="artifacts/replay-result.json")
    args = parser.parse_args()
    result = DesktopReplayer().replay(CapabilityArtifact.load(args.artifact), inputs=json.loads(args.inputs), confirm_risky=args.confirm_risky)
    result.save(args.result)
    print(json.dumps(result.__dict__, indent=2))


if __name__ == "__main__":
    main()