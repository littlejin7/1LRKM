"""
tts.py — TTS 변환 모듈

사용법:
    from tts import text_to_speech, TTS_OUTPUT_PATH
"""

import asyncio
import re
import edge_tts

TTS_OUTPUT_PATH = "./news_report.mp3"

# ── 영문 철자 문제 완화 ──
_TTS_TOKEN_MAP: dict = {
    "HYBE": "하이브", "ADOR": "어도어", "SM": "에스엠", "YG": "와이지",
    "JYP": "제이와이피", "CJ": "씨제이", "MBC": "엠비씨", "KBS": "케이비에스",
    "SBS": "에스비에스", "JTBC": "제이티비씨", "OTT": "오티티",
    "BTS": "비티에스", "IVE": "아이브", "SHEESH": "쉬시",
}

_RE_SPACED_LETTERS = re.compile(r"\b(?:[A-Za-z]\s+){2,}[A-Za-z]\b")
_RE_UPPER_TOKEN = re.compile(r"\b[A-Z]{3,}\b")


def normalize_tts_text(text: str) -> str:
    s = (text or "").strip()
    if not s:
        return ""
    def _join_letters(m):
        return re.sub(r"\s+", "", m.group(0))
    s = _RE_SPACED_LETTERS.sub(_join_letters, s)
    for k, v in _TTS_TOKEN_MAP.items():
        s = re.sub(rf"\b{re.escape(k)}\b", v, s, flags=re.IGNORECASE)
    s = _RE_UPPER_TOKEN.sub(lambda m: m.group(0).lower(), s)
    return s


async def _generate_tts(text: str, output_path: str, voice: str):
    communicate = edge_tts.Communicate(
        text=normalize_tts_text(text),
        voice=voice,
        rate="+20%"
    )
    await communicate.save(output_path)


def text_to_speech(text: str, output_path: str = TTS_OUTPUT_PATH) -> tuple:

    # ── 무료: edge_tts ──
    ko_path = output_path.replace(".mp3", "_ko.mp3")
    en_path = output_path.replace(".mp3", "_en.mp3")

    asyncio.run(_generate_tts(text, ko_path, voice="ko-KR-SunHiNeural"))
    # asyncio.run(_generate_tts(text, en_path, voice="en-US-JennyNeural"))  

    print(f"  TTS: {ko_path}")

    return ko_path 
