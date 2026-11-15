"""Create or update Cranley's ElevenLabs phone agent and its three webhook tools. Safe to re-run: ids are kept in
$THRESHOLD_DATA_DIR/photon/voice.json and updated in place. Needs ELEVENLABS_API_KEY and VOICE_TOOL_SECRET in the data
folder's .env; the tool secret is stored as an ElevenLabs workspace secret, so it never appears in the agent config.

    uv run python scripts/setup_voice.py [--base https://<host>:8443]
"""
from __future__ import annotations

import argparse
import json

import httpx

from threshold.config import DATA, env

STATE = DATA / "photon" / "voice.json"
VOICE = "jqcCZkN6Knx8BJ5TBdYR"  # same voice as the iMessage voice messages
CALLER = {"type": "string", "dynamic_variable": "system__caller_id"}
TOOLS = {
    "start_check": ("Start checking a building for the caller. Pass their question in their own words, including the "
                    "place (city, street address) and what must fit or work (a truck, a wheelchair, a sofa).",
                    {"question": {"type": "string", "description": "The caller's question in their words"}}, 10),
    "get_answer": ("Get the result of the check started with start_check. If status is running, say a short filler "
                   "like 'still measuring' and call it again. When status is done, read `say` exactly as written.", {}, 25),
    "answer_question": ("Pass the caller's answer to a question the check asked (for example their wheelchair's "
                        "width with its unit). Then call get_answer.",
                        {"answer": {"type": "string", "description": "The caller's answer in their words, with units"}}, 10),
}
PROMPT = """You are Cranley on a phone call. Cranley checks real buildings from laser scans and aerial photos: whether a
truck fits a garage, whether a wheelchair gets through every door, whether a sofa fits. The caller may be driving to a
viewing or unable to type.
When they ask about a building, call start_check with their words, say "Checking now", then call get_answer until its
status is done. Read the `say` field exactly as written: its numbers come from the measurement, so never change,
round or add a number yourself, and never guess a measurement. If `say` asks a question, ask it, then pass their reply
to answer_question and call get_answer again.
Keep your own lines under 20 words. Before hanging up, tell them the plan and the details will arrive by text."""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="https://linuxbox.<tailnet>:8443")
    a = p.parse_args()
    e = env()
    h = {"xi-api-key": e["ELEVENLABS_API_KEY"]}
    st = json.loads(STATE.read_text()) if STATE.exists() else {}

    def el(method: str, path: str, body: dict) -> dict:
        r = httpx.request(method, "https://api.elevenlabs.io" + path, headers=h, json=body, timeout=60)
        if r.status_code >= 400:
            raise SystemExit(f"{method} {path}: {r.status_code} {r.text[:300]}")
        return r.json() if r.content else {}

    def save() -> None:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(st, indent=1))

    if not st.get("secret_id"):
        st["secret_id"] = el("POST", "/v1/convai/secrets", {"type": "new", "name": "cranley_voice_tool_secret",
                                                             "value": e["VOICE_TOOL_SECRET"]})["secret_id"]
        save()
    st.setdefault("tools", {})
    for name, (desc, props, timeout) in TOOLS.items():
        cfg = {"type": "webhook", "name": name, "description": desc, "response_timeout_secs": timeout,
               "api_schema": {"url": f"{a.base}/voice/tool/{name}", "method": "POST",
                              "request_headers": {"x-cranley-tool-secret": {"secret_id": st["secret_id"]}},
                              "request_body_schema": {"type": "object", "description": "The caller and their words",
                                                      "properties": {"caller_id": CALLER, **props},
                                                      "required": ["caller_id", *props]}}}
        if st["tools"].get(name):
            el("PATCH", f"/v1/convai/tools/{st['tools'][name]}", {"tool_config": cfg})
        else:
            st["tools"][name] = el("POST", "/v1/convai/tools", {"tool_config": cfg})["id"]
            save()
    body = {"name": "Cranley phone", "conversation_config": {
        "agent": {"first_message": "Hi, this is Cranley. Which building should I check for you?", "language": "en",
                  "prompt": {"prompt": PROMPT, "tool_ids": list(st["tools"].values())}},
        "tts": {"voice_id": VOICE, "model_id": "eleven_flash_v2"}}}
    if st.get("agent_id"):
        el("PATCH", f"/v1/convai/agents/{st['agent_id']}", body)
    else:
        st["agent_id"] = el("POST", "/v1/convai/agents/create", body)["agent_id"]
        save()
    print(f"agent {st['agent_id']}, tools {st['tools']}")


if __name__ == "__main__":
    main()
