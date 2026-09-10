from __future__ import annotations

import json
import os
import re
from urllib import error, request


class LLMClient:
    def __init__(self) -> None:
        self.base_url = os.environ.get("LLM_BASE_URL", "").rstrip("/")
        self.model = os.environ.get("LLM_MODEL", "")
        self.api_key = os.environ.get("LLM_API_KEY", "")

    def extract_operation(self, message: str, capabilities: list[dict[str, object]]) -> dict[str, object]:
        if not all((self.base_url, self.model, self.api_key)):
            raise RuntimeError("Set LLM_BASE_URL, LLM_MODEL, and LLM_API_KEY before using the chatbot.")

        system_prompt = (
            "Choose the capability that best matches the user's request. Return JSON only with exactly "
            "these keys: capability, values, missing, reply. capability must be one of the listed capability "
            "names or null if unsupported. values must be an object keyed by the selected capability's input "
            "step IDs, containing the values supplied by the user. Use null for values not provided. missing "
            "must list the input step IDs still missing. Do not invent values. For unsupported requests, "
            "use capability null and explain the limitation in reply. If a create-customer request contains "
            "unlabeled non-empty lines, map them in order to the selected capability's typed step IDs. "
            "For the standard customer sequence, the order is firstName, lastName, dob, address, ssn, deposit. "
            "\n\nAvailable capabilities:\n"
            + json.dumps(capabilities, indent=2)
        )
        if "api.anthropic.com" in self.base_url:
            endpoint = f"{self.base_url}/v1/messages"
            payload = {
                "model": self.model,
                "max_tokens": 512,
                "temperature": 0,
                "system": system_prompt,
                "messages": [{"role": "user", "content": message}],
            }
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
        else:
            endpoint = f"{self.base_url}/chat/completions"
            payload = {
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
            }
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        req = request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=45) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (error.HTTPError, error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc

        try:
            if "api.anthropic.com" in self.base_url:
                content = result["content"][0]["text"]
            else:
                content = result["choices"][0]["message"]["content"]
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content)
            extracted = self._parse_json_response(content)
            values = extracted.get("values", {})
            if not isinstance(values, dict):
                raise ValueError("values must be an object")
            return {
                "capability": extracted.get("capability"),
                "values": values,
                "missing": extracted.get("missing", []) if isinstance(extracted.get("missing", []), list) else [],
                "reply": extracted.get("reply", "Please provide the missing customer values."),
            }
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("The LLM returned an invalid customer extraction response.") from exc

    @staticmethod
    def _parse_json_response(content: object) -> dict[str, object]:
        if not isinstance(content, str):
            raise ValueError("LLM content was not text")
        cleaned = content.strip()
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE).strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start < 0 or end <= start:
                raise
            parsed = json.loads(cleaned[start:end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("LLM response must be a JSON object")
        return parsed