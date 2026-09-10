# iBankingAgent

Python computer-use agent arm for training against a live iBanking desktop session.

The arm deliberately does not import, inspect, or modify the iBanking application. It records what an operator does at the screen boundary and saves a versioned capability artifact that can be reviewed and replayed.

## Record a capability

Install dependencies in a virtual environment, launch the iBanking app separately, then run:

```bash
python -m agent_arm.recorder lookup_balance --goal "Look up a member and read their current balance"
```

Without `--output`, this saves to `artifacts/capabilities/lookup_balance.json`. The filename is derived from the capability name. Use `--output` to choose a different path.

Use the target app normally while recording. `F8` pauses/resumes, `F9` stops and saves, and `F10` records a human handoff point. macOS may require Accessibility permission for the terminal/Python process.

## Replay a capability

```bash
python -m agent_arm.replay \
	artifacts/capabilities/recorded_capability.json \
	--inputs '{"step_003":"505576"}'
```

Pass input values as a JSON object keyed by the recorded step IDs. For multiple fields:

```bash
python -m agent_arm.replay \
	artifacts/capabilities/recorded_capability.json \
	--inputs '{"step_002":"fName3","step_004":"lName3","step_006":"2000-01-12","step_008":"gghhjj","step_010":"123456783","step_012":"10"}'
```

But, the best way to run replay is to use Desktop Chatbot that uses LLM to map the values provided in a sequence with the steps.

Replay is deterministic and policy-gated. It returns `success`, `blocked`, or `failed` with the step, error code, and evidence paths. Risky steps require `--confirm-risky`. Screenshots are evidence only; secrets and sensitive parameter values should be supplied at invocation time rather than persisted in the artifact.

## Desktop chatbot and recording

The native Tkinter app lists every JSON capability in `artifacts/capabilities/`, gives that catalog to the LLM, and uses the capability selected from the user's request. It is not limited to customer creation: every capability recorded in that folder can be selected and replayed.

Install dependencies and configure the LLM environment variables:

```bash
python3 -m pip install -r requirements.txt
brew install tesseract
export LLM_BASE_URL="https://your-llm-provider.example/v1"
export LLM_MODEL="your-model"
export LLM_API_KEY="your-api-key"
python3 -m agent_arm.desktop
```

Type a request in the multiline chat box and click **Send**. The LLM identifies the matching JSON capability by its filename, artifact name, and goal, extracts values for its recorded input steps, and asks for confirmation before running replay. For example:

```text
Create customer with:
John
Smith
01/01/2000
1234 Dummy Ave
123456789
100
```

During replay, after click actions that may open a dialog, the app looks for dialog-sized windows belonging to the recorded target application, not the chatbot. It reads the full popup in memory with Tesseract OCR, removes standalone `OK`, `Cancel`, and `Close` button labels, and returns the message in the chat and in `artifacts/replay-result.json`. No OCR screenshot is saved.

### Record from the chatbot UI

1. Open the target desktop application and leave it ready for the workflow.
2. Click **Record** in the Operator Console area.
3. Enter a JSON filename, such as `create_consumer.json`, and a goal describing the workflow.
4. Click **Start recording** in the popup.
5. Perform the workflow in the target application.
6. Use **Pause**/**Resume** when you need to interact without recording an action.
7. Click **Stop** to finish and save the capability.

The artifact is saved to `artifacts/capabilities/<filename>.json`. Its filename, artifact name, goal, and recorded input step IDs are automatically included in the LLM capability catalog, so later chat requests can select the appropriate recording. macOS Accessibility and Input Monitoring permissions are required for Python to capture desktop actions.

## Design boundary

`CapabilityArtifact` describes intent, typed inputs/outputs, target strategy, checkpoints, and policy. `DesktopRecorder` and `DesktopReplayer` are the surface adapter. A browser or native-app adapter can implement the same action contract later without changing the recorded capability schema.