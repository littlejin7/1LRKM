from __future__ import annotations
import json
import os
import urllib.error
import urllib.request
from refine_prompts import SUMMARY_REFINE_SYSTEM_PROMPT

def _http_headers() -> dict[str, str]:
    h = {"Content-Type": "application/json; charset=utf-8"}
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if key and key != "ollama":
        h["Authorization"] = f"Bearer {key}"
    return h


def _call_llm(
    *,
    base_url: str,
    user_message: str,
    model: str,
    temperature: float,
    timeout: float,
    max_tokens: int,
    json_mode: bool,
) -> str:
    """OpenAI 호환 POST /v1/chat/completions (Ollama·OpenRouter 등). SDK·jiter 미사용."""
    url = base_url.rstrip("/") + "/chat/completions"
    messages = [
        {"role": "system", "content": SUMMARY_REFINE_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    payload: dict = {
        "model": model,
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "stream": False,
        "keep_alive": 0,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers=_http_headers())

    try:
        with urllib.request.urlopen(req, timeout=float(timeout)) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body[:1200]}") from e
    except OSError as e:
        raise RuntimeError(f"연결 실패: {e}") from e

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"응답 JSON 파싱 실패: {e!s} · 앞부분: {raw[:400]!r}") from e

    choices = obj.get("choices")
    if not choices:
        raise RuntimeError(f"choices 없음: {raw[:800]!r}")
    msg = (choices[0] or {}).get("message") or {}
    return (msg.get("content") or "").strip()

