from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Parameter:
    name: str
    type: str
    description: str
    required: bool = True
    sensitive: bool = False


@dataclass
class Step:
    id: str
    action: str
    target: dict[str, Any]
    value: str | None = None
    rationale: str = "Recorded from operator action"
    risk: str = "safe"
    checkpoint: str | None = None


@dataclass
class CapabilityArtifact:
    name: str
    goal: str
    target: dict[str, str]
    parameters: list[Parameter]
    outputs: list[dict[str, str]]
    steps: list[Step]
    checkpoint: dict[str, str]
    version: str = "1.0.0"
    artifact_type: str = "desktop.computer_use_capability"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    policy: dict[str, Any] = field(default_factory=lambda: {
        "allowed_actions": ["click", "key", "type", "wait", "screenshot"],
        "blocked_actions": ["hotkey", "shell", "clipboard_read"],
        "require_confirmation_for": ["submit", "deposit", "delete", "transfer"],
        "redact_sensitive_values": True,
    })

    def save(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "CapabilityArtifact":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        payload["parameters"] = [Parameter(**item) for item in payload.get("parameters", [])]
        payload["steps"] = [Step(**item) for item in payload.get("steps", [])]
        return cls(**payload)


@dataclass
class ReplayResult:
    status: str
    capability: str
    completed_steps: int
    outputs: dict[str, Any] = field(default_factory=dict)
    error: dict[str, str] | None = None
    evidence: list[str] = field(default_factory=list)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")