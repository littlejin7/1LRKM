import sys
import os
import json

sys.path.append(os.getcwd())
from database import get_session, RawNews
from processor import process_single, client, LLM_MODEL, SUMMARY_SYSTEM_PROMPT, SUMMARY_USER_PROMPT_TEMPLATE

def debug_ai_response(raw_id):
    with get_session() as session:
        raw = session.query(RawNews).filter(RawNews.id == raw_id).first()
        if not raw: return

        # 힌트 파싱 (processor.py 로직 그대로)
        full_content = (raw.content or "")
        artist_hint = ""
        clean_content_text = full_content
        if full_content.startswith("[ARTIST_HINT]"):
            parts = full_content.split("\n", 1)
            artist_hint = parts[0].replace("[ARTIST_HINT]", "").strip()
            clean_content_text = parts[1] if len(parts) > 1 else ""

        user_message = SUMMARY_USER_PROMPT_TEMPLATE.format(
            title=raw.title or "",
            content=clean_content_text[:3000],
            raw_category_hint=f"{raw.category} / {raw.sub_category}",
            raw_artist_hint=artist_hint if artist_hint else "없음",
        )

        print(f"--- [AI에게 보내는 질문] ---\n{user_message}\n")

        response = client.chat.completions.create(
            model=LLM_MODEL,
            temperature=0.3,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )
        print(f"--- [AI의 원본 답변] ---\n{response.choices[0].message.content}")

if __name__ == "__main__":
    debug_ai_response(26) # ID=10에 해당하는 RawID=26
