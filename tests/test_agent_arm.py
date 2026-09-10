import json

from agent_arm.artifact import CapabilityArtifact, Parameter, ReplayResult, Step


def test_artifact_is_versioned_and_round_trips(tmp_path):
    artifact = CapabilityArtifact(
        name="lookup_balance",
        goal="Look up a member balance",
        target={"surface": "desktop", "entry_point": "iBanking"},
        parameters=[Parameter("member_id", "string", "Member identifier")],
        outputs=[{"name": "balance", "type": "number", "description": "Current balance"}],
        steps=[Step("step_001", "click", {"strategy": "screen_coordinate", "x": 10, "y": 20})],
        checkpoint={"type": "manual", "description": "Balance is visible"},
    )
    path = tmp_path / "capability.json"
    artifact.save(path)
    loaded = CapabilityArtifact.load(path)
    assert loaded.version == "1.0.0"
    assert loaded.steps[0].target["strategy"] == "screen_coordinate"
    assert json.loads(path.read_text())["policy"]["redact_sensitive_values"] is True


def test_replay_result_has_structured_failure_contract():
    result = ReplayResult("failed", "lookup_balance", 2, error={"code": "record_not_found", "message": "No member"})
    assert result.status == "failed"
    assert result.error["code"] == "record_not_found"