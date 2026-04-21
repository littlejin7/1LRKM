"""LLM 응답에서 JSON 객체 추출·파싱 (랩·배치 공용)."""

from __future__ import annotations

import json
import re


def extract_json_object(text: str) -> str | None:
    t = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", t, re.IGNORECASE)
    if m:
        t = m.group(1).strip()
    start = t.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    quote: str | None = None
    for i in range(start, len(t)):
        c = t[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif quote and c == quote:
                in_str = False
                quote = None
            continue
        if c in ('"', "'"):
            in_str = True
            quote = c
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return t[start : i + 1]
    return None


def parse_llm_json(raw_text: str) -> tuple[dict, str | None]:
    raw_text = (raw_text or "").strip()
    if not raw_text:
        raise json.JSONDecodeError("empty response", raw_text, 0)

    try:
        out = json.loads(raw_text)
        if isinstance(out, dict):
            return out, None
        raise json.JSONDecodeError("root is not an object", raw_text, 0)
    except json.JSONDecodeError:
        pass

    sub = extract_json_object(raw_text)
    if sub and sub != raw_text:
        try:
            out = json.loads(sub)
            if isinstance(out, dict):
                return out, "마크다운/주변 텍스트에서 JSON 객체 블록만 추출해 파싱했습니다."
        except json.JSONDecodeError:
            pass
    elif sub:
        try:
            out = json.loads(sub)
            if isinstance(out, dict):
                return out, None
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("no valid JSON object", raw_text, 0)
