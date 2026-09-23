"""One explicit, bounded call to an existing local Qwen service."""

from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

from workspace_io import decode_json, save_json


ENDPOINT = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen2.5:3b"


def ask(stage, instructions, context, *, response_shape=None, trace_folder=None):
    payload = context if isinstance(context, str) else json.dumps(context, ensure_ascii=False)
    request_data = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": payload},
        ],
        "stream": False,
        "keep_alive": 0,
        "options": {"num_gpu": 0, "num_thread": 2, "num_ctx": 2048, "num_predict": 768, "temperature": 0},
    }
    if response_shape is not None:
        request_data["format"] = response_shape
    started = datetime.now(timezone.utc)
    request = Request(ENDPOINT, data=json.dumps(request_data).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
    # Local model traffic must not travel through a configured system proxy.
    opener = build_opener(ProxyHandler({}))
    try:
        with opener.open(request, timeout=120) as connection:
            response = decode_json(connection.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError) as error:
        raise RuntimeError("Local Qwen request failed. Check Ollama and the installed model; no retry was made.") from error
    if trace_folder is not None:
        name = stage + "-" + started.strftime("%Y%m%dT%H%M%S%fZ") + ".json"
        save_json(Path(trace_folder) / name, {
            "stage": stage, "started_utc": started.isoformat(),
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "request": request_data, "response": response,
            "meaning": "Original exchange; stage validation takes place after recording.",
        })
    if not isinstance(response, dict) or response.get("done") is not True:
        raise ValueError("The model response was not marked complete.")
    if response.get("done_reason") == "length":
        raise ValueError("The model reached its output limit. The incomplete reply was not accepted.")
    message = response.get("message")
    text = message.get("content") if isinstance(message, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise ValueError("The model returned no usable text.")
    return text
