"""
tts.py — TTS 변환 모듈

사용법:
    from tts import text_to_speech, TTS_OUTPUT_PATH
"""

import asyncio
import edge_tts

TTS_OUTPUT_PATH = "./news_report.mp3"


async def _generate_tts(text: str, output_path: str, voice: str):
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate="+20%"  # 느리게(-), 빠르게(+)
    )
    await communicate.save(output_path)


def text_to_speech(text: str, output_path: str = TTS_OUTPUT_PATH) -> tuple:

    # ── 무료: edge_tts ──
    ko_path = output_path.replace(".mp3", "_ko.mp3")
    en_path = output_path.replace(".mp3", "_en.mp3")

    asyncio.run(_generate_tts(text, ko_path, voice="ko-KR-SunHiNeural"))  # 한국어 여성
    # asyncio.run(_generate_tts(text, en_path, voice="en-US-JennyNeural"))  # 영어 여성 🚨🚨tts영어

    print(f"  ✅ 한국어 TTS: {ko_path}")
    # print(f"  ✅ 영어 TTS: {en_path}") 🚨🚨tts영어

    return ko_path #, en_path 🚨🚨tts영어

    # ── 유료: Google Cloud TTS (전환 시 위 edge_tts 블록 주석 처리) ──
    # from google.cloud import texttospeech
    # client = texttospeech.TextToSpeechClient()
    # synthesis_input = texttospeech.SynthesisInput(text=text)
    # voice_params = texttospeech.VoiceSelectionParams(
    #     language_code="ko-KR",
    #     name="ko-KR-Chirp3-HD-Zubenelgenubi"
    # )
    # audio_config = texttospeech.AudioConfig(
    #     audio_encoding=texttospeech.AudioEncoding.MP3,
    #     speaking_rate=1.1,
    # )
    # response = client.synthesize_speech(
    #     input=synthesis_input, voice=voice_params, audio_config=audio_config
    # )
    # with open(ko_path, "wb") as f:
    #     f.write(response.audio_content)
    # return ko_path, ko_path
