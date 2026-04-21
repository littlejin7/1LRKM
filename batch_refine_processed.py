#!/usr/bin/env python3
"""
배치 1-1차 refine: `processed_news` 행을 순회해 LLM 재가공 후 같은 id 행을 덮어쓴다.

  # 미리보기만 (DB 변경 없음)
  python batch_refine_processed.py --dry-run --limit 3

  # 전체 순회 (최신 id 먼저)
  python batch_refine_processed.py

  # 100건만, 호출 간 0.5초
  python batch_refine_processed.py --limit 100 --sleep 0.5

  # 10건씩 끊어서 처리(기본 chunk-size=10), 청크 사이 30초 쉼
  python batch_refine_processed.py --chunk-size 10 --sleep-between-chunks 30

  # 한 번에 묶지 않고 예전처럼 한 줄로만 진행표시
  python batch_refine_processed.py --chunk-size 0

  # 특정 id만
  python batch_refine_processed.py --ids 11,12,13

  # Pydantic 검증 실패 시 LLM 재시도 끄기(서버 후처리만)
  python batch_refine_processed.py --no-schema-retry --limit 5

  # artist_tags는 DB 기존 값 그대로(리파인에서 태그만 건드리지 않음)
  python batch_refine_processed.py --preserve-artist-tags --limit 10

환경변수: LLM_MODEL(미설정 시 기본 gemma3:latest), OLLAMA_BASE_URL, OPENAI_API_KEY, LLM_MAX_TOKENS (랩과 동일)

LLM 호출은 OpenAI Python SDK 대신 urllib로 `/v1/chat/completions`에 POST한다.
(jiter·openai 패키지 깨짐 없이 Ollama 호환 엔드포인트 사용)
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pydantic import ValidationError
from sqlalchemy.orm import joinedload

from database import ProcessedNews, RawNews, get_session
from prompts.summary_refine import (
    REFINE_VALIDATION_RETRY_USER_SUFFIX,
    SUMMARY_REFINE_SYSTEM_PROMPT,
    build_refine_user_message,
)
from refine_db import apply_refined_to_processed, processed_news_row_to_dict
from refine_json_parse import parse_llm_json
from schemas import KpopNewsSummary

RETRY_USER_EXTRA = (
    "\n\n[출력 규칙] 위와 동일한 키 구조의 JSON 객체 하나만 출력. "
    "설명·마크다운·코드펜스 금지."
)


# NOTE: Python re look-behind requires fixed width, so avoid (?<=...|...).
# Split on whitespace that follows common sentence end markers.
_SENT_SPLIT_RE = re.compile(r"(?:[\.?!]|다\.)\s+")


def _as_list_of_str(x) -> list[str]:
    if x is None:
        return []
    if isinstance(x, list):
        return [str(v).strip() for v in x if str(v).strip()]
    s = str(x).strip()
    return [s] if s else []


def _is_korean_headline_binomial_junk(s: str) -> bool:
    """한글 2글자+공백+한글 2글자 — 사건 헤드라인 조각(예: 얼굴 상처). artist_tags 부적합."""
    t = (s or "").strip()
    if not t or re.search(r"[A-Za-z]", t):
        return False
    return re.fullmatch(r"[가-힣]{2}\s+[가-힣]{2}", t) is not None


_KO_SURNAME_FIRST_CONSENSUS = frozenset(
    {
        "김",
        "이",
        "박",
        "최",
        "정",
        "강",
        "조",
        "윤",
        "장",
        "임",
        "한",
        "오",
        "서",
        "신",
        "권",
        "황",
        "안",
        "송",
        "류",
        "홍",
        "전",
        "고",
        "문",
        "양",
        "손",
        "배",
        "백",
        "허",
        "남",
        "심",
        "노",
        "하",
        "변",
        "주",
        "차",
        "유",
        "나",
        "민",
        "진",
    }
)

_DENY_KO_TITLE_TTS_CONSENSUS = frozenset(
    {
        "한국",
        "대한",
        "민국",
        "이번",
        "오늘",
        "어제",
        "내일",
        "방송",
        "뉴스",
        "기자",
        "속보",
        "관련",
        "영상",
        "사진",
        "최신",
        "전체",
        "확인",
        "공개",
        "논란",
        "화제",
        "시청자",
        "프로그램",
        "편스토랑",
        "예능",
        "드라마",
        "영화",
        "근황",
    }
)


def _consensus_name_tokens_from_ko_title_tts(ko_title: str, tts: str) -> list[str]:
    """ko_title과 tts_text에 **동시에** 등장하는 한글 토큰만(보수적)."""
    kt = (ko_title or "").strip()
    tt = (tts or "").strip()
    if not kt or not tt:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in re.finditer(r"[가-힣]{2,10}", kt):
        w = m.group(0)
        if w in seen or w in _DENY_KO_TITLE_TTS_CONSENSUS:
            continue
        if w not in tt:
            continue
        if _is_korean_headline_binomial_junk(w):
            continue
        ln = len(w)
        if ln == 2:
            if w[0] in _KO_SURNAME_FIRST_CONSENSUS:
                out.append(w)
                seen.add(w)
        elif ln == 3:
            if w[0] in _KO_SURNAME_FIRST_CONSENSUS:
                out.append(w)
                seen.add(w)
        elif 5 <= ln <= 10:
            out.append(w)
            seen.add(w)
    return out[:8]


def _apply_title_tts_consensus_recovery(d: dict, original: dict) -> None:
    """헤드라인 조각 제거 후 비었거나 K-Enter일 때만 ko_title∩tts로 보강."""
    raw = _as_list_of_str(d.get("artist_tags"))
    cleaned = [t for t in raw if not _is_korean_headline_binomial_junk(t)]
    if cleaned and cleaned != ["K-Enter"]:
        d["artist_tags"] = cleaned[:10]
        return
    ko_title = str(d.get("ko_title") or original.get("ko_title") or "").strip()
    tts = str(d.get("tts_text") or original.get("tts_text") or "").strip()
    cands = _consensus_name_tokens_from_ko_title_tts(ko_title, tts)
    if cands:
        tail = [t for t in cleaned if t not in cands]
        merged: list[str] = []
        seen_m: set[str] = set()
        for t in cands + tail:
            if t not in seen_m:
                seen_m.add(t)
                merged.append(t)
        d["artist_tags"] = merged[:10]
        return
    d["artist_tags"] = cleaned if cleaned else ["K-Enter"]


def _coerce_summary_item_to_card(
    c: object, *, index: int, first_label: str, rest_label: str
) -> dict:
    """LLM이 카드 대신 문자열을 넣은 경우 dict로 맞춘다."""
    if c is None:
        return {"label": first_label if index == 0 else rest_label, "content": ""}
    if isinstance(c, dict):
        return c
    if isinstance(c, str):
        return {
            "label": first_label if index == 0 else rest_label,
            "content": c.strip(),
        }
    return {
        "label": first_label if index == 0 else rest_label,
        "content": str(c) if c is not None else "",
    }


def _split_into_cards(cards: list[dict], *, min_cards: int = 4, max_cards: int = 6) -> list[dict]:
    """카드가 너무 적을 때 content를 '있는 문장'만 쪼개 최소 개수를 맞춘다(새 사실 생성 금지)."""
    if not cards:
        return cards
    cards = [
        _coerce_summary_item_to_card(c, index=i, first_label="요약", rest_label="주요내용")
        for i, c in enumerate(cards)
    ]
    if min_cards <= len(cards) <= max_cards:
        return cards

    chunks: list[str] = []
    for c in cards:
        txt = str((c or {}).get("content") or "").strip()
        if not txt:
            continue
        parts = [p.strip() for p in _SENT_SPLIT_RE.split(txt) if p.strip()]
        if len(parts) < 2:
            # 문장 구분이 안 되면 약한 구분자로 한 번 더 쪼갠다.
            parts = [p.strip() for p in re.split(r"[\\n;·•]+", txt) if p.strip()] or parts
        chunks.extend(parts or [txt])

    if not chunks:
        return cards

    chunks = chunks[:max_cards]
    out: list[dict] = []
    for i, ch in enumerate(chunks):
        out.append({"label": "요약" if i == 0 else "주요내용", "content": ch})
    # 그래도 카드가 부족하면 마지막 내용을 반복해 최소 개수는 맞춘다(새 사실 추가 금지).
    while len(out) < min_cards:
        out.append({"label": "추가", "content": out[-1]["content"]})
    return out


def _split_into_en_cards(cards: list[dict], *, min_cards: int = 4, max_cards: int = 6) -> list[dict]:
    """summary_en 카드가 너무 적을 때 영어 문장만 쪼개 최소 개수로 맞춘다(새 사실 생성 금지)."""
    if not cards:
        return cards
    cards = [
        _coerce_summary_item_to_card(c, index=i, first_label="Summary", rest_label="Details")
        for i, c in enumerate(cards)
    ]
    if min_cards <= len(cards) <= max_cards:
        return cards

    chunks: list[str] = []
    for c in cards:
        txt = str((c or {}).get("content") or "").strip()
        if not txt:
            continue
        parts = [p.strip() for p in re.split(r"(?<=[\.?!])\s+", txt) if p.strip()]
        chunks.extend(parts or [txt])

    if not chunks:
        return cards

    chunks = chunks[:max_cards]
    out: list[dict] = []
    for i, ch in enumerate(chunks):
        out.append({"label": "Summary" if i == 0 else "Details", "content": ch})
    while len(out) < min_cards:
        out.append({"label": "Details", "content": out[-1]["content"]})
    return out


def _keywords_from_title(title: str) -> list[str]:
    t = (title or "").strip()
    if not t:
        return []
    # 한글/영문/숫자 토큰만 추출
    toks = re.findall(r"[A-Za-z0-9가-힣]{2,}", t)
    stop = {
        "music",
        "video",
        "views",
        "view",
        "record",
        "debut",
        "kpop",
        "k-pop",
        "youtube",
        "mv",
    }
    out: list[str] = []
    for tok in toks:
        low = tok.lower()
        if low in stop:
            continue
        if tok not in out:
            out.append(tok)
    return out


def _coerce_keywords_5(*, refined: list[str], original: list[str], title: str) -> list[str]:
    # 1) refined 우선 + 중복 제거
    pool: list[str] = []
    for x in refined + original + _keywords_from_title(title):
        s = str(x).strip()
        if not s:
            continue
        if re.fullmatch(r"(?i)k-?enter|kpop|k-pop|youtube|mv|views?|record", s):
            continue
        if s not in pool:
            pool.append(s)

    if len(pool) >= 5:
        return pool[:5]
    # 부족하면 가장 안전한 더미로 채운다(스키마 고정용)
    while len(pool) < 5:
        pool.append("K-Enter")
    return pool[:5]


def _koreanize_keywords(keywords: list[str]) -> list[str]:
    """
    간단 사전 기반 한글화.
    - 고유명사(예: BTS) / 연도(예: 2026) 는 유지
    - 일반 영문 키워드는 한글로 치환 (world tour -> 월드투어 등)
    """
    mapping = {
        "world tour": "월드투어",
        "tour": "투어",
        "concert": "콘서트",
        "music": "음악",
        "mv": "뮤직비디오",
        "music video": "뮤직비디오",
        "debut": "데뷔",
        "comeback": "컴백",
        "album": "앨범",
        "new song": "신곡",
        "chart": "차트",
        "views": "조회수",
        "record": "기록",
        "global": "글로벌",
        "asia": "아시아",
        "north america": "북미",
        "south america": "남미",
        "europe": "유럽",
        "japan": "일본",
        "korea": "한국",
        "k-pop": "케이팝",
        "kpop": "케이팝",
    }

    out: list[str] = []
    for kw in keywords:
        s = str(kw).strip()
        if not s:
            continue
        # 연도/숫자 유지
        if re.fullmatch(r"\d{4}", s) or re.fullmatch(r"\d+(?:\.\d+)?", s):
            if s not in out:
                out.append(s)
            continue
        # 짧은 영문 약어(그룹/회사) 유지
        if re.fullmatch(r"[A-Z]{2,6}", s):
            if s not in out:
                out.append(s)
            continue

        low = s.lower().strip()
        low = re.sub(r"\s+", " ", low)
        repl = mapping.get(low)
        if repl:
            if repl not in out:
                out.append(repl)
            continue
        # 단어 단위로도 치환 시도
        if re.fullmatch(r"[a-z][a-z ]{1,40}", low):
            words = low.split()
            joined = " ".join(words)
            repl2 = mapping.get(joined)
            if repl2:
                if repl2 not in out:
                    out.append(repl2)
                continue
        if s not in out:
            out.append(s)

    return out


def _sanitize_refine_dict(
    *, refined: dict, original: dict, preserve_artist_tags: bool = False
) -> dict:
    """리파인 결과를 DB 덮어쓰기 전에 최소한으로 보정/방어."""
    d = copy.deepcopy(refined)

    def _score_tag_by_title(tag: str, title_text: str) -> int:
        if not tag or not title_text:
            return 0
        try:
            return 1 if str(tag).strip().lower() in str(title_text).strip().lower() else 0
        except Exception:
            return 0

    # null 방지
    if d.get("trend_insight") is None:
        d["trend_insight"] = ""

    orig_summary = original.get("summary") or []
    orig_summary_en = original.get("summary_en") or []
    title = str(original.get("ko_title") or original.get("title") or "").strip()

    # 빈 문자열로 덮어써서 메타가 날아가는 사고 방지: 비어있으면 원본 유지
    for key in ("ko_title", "tts_text", "source_name", "language"):
        v = d.get(key)
        if v is None or (isinstance(v, str) and not v.strip()):
            if key in original:
                d[key] = original.get(key)

    # summary 카드 수 방어 (1개만 오는 케이스 완화)
    if isinstance(d.get("summary"), list):
        d["summary"] = _split_into_cards(d["summary"])
    s_len = len(d.get("summary") or [])
    if not (4 <= s_len <= 6):
        d["summary"] = orig_summary

    # summary_en: 부족/불일치가 자주 발생하므로 후처리로 4~6장 + summary 길이 일치로 보정한다.
    se = d.get("summary_en")
    if isinstance(se, list):
        d["summary_en"] = _split_into_en_cards(se)

    s_len = len(d.get("summary") or [])
    se_list = d.get("summary_en") if isinstance(d.get("summary_en"), list) else []

    # 부족하면 마지막 카드를 반복해 길이를 summary에 맞춘다(6장 초과 금지).
    if isinstance(se_list, list) and se_list and len(se_list) < s_len:
        last = se_list[-1]
        while len(se_list) < s_len and len(se_list) < 6:
            se_list.append(
                {
                    "label": last.get("label", "Details"),
                    "content": last.get("content", ""),
                }
            )
        d["summary_en"] = se_list

    se_len = len(d.get("summary_en") or []) if isinstance(d.get("summary_en"), list) else 0
    if not (4 <= se_len <= 6) or se_len != s_len:
        # 그래도 안 맞으면 안전하게 원본 유지
        d["summary_en"] = orig_summary_en

    # keywords 5개 방어
    kws = _as_list_of_str(d.get("keywords"))
    orig_kws = _as_list_of_str(original.get("keywords"))
    d["keywords"] = _koreanize_keywords(
        _coerce_keywords_5(refined=kws, original=orig_kws, title=title)
    )

    if preserve_artist_tags:
        oa = original.get("artist_tags")
        if isinstance(oa, list):
            d["artist_tags"] = copy.deepcopy(oa)
        elif oa is None:
            d["artist_tags"] = []
        else:
            d["artist_tags"] = _as_list_of_str(oa)
        return d

    # artist_tags 노이즈 제거 + 원본 병합
    def _normalize_artist_tags(xs: list[str]) -> list[str]:
        # JSON 문자열 리스트를 펼친다 (예: '["a","b"]')
        expanded: list[str] = []
        for t in xs:
            tt = str(t).strip()
            if not tt:
                continue
            if tt.startswith("[") and tt.endswith("]"):
                try:
                    parsed_list = json.loads(tt)
                    if isinstance(parsed_list, list):
                        for x in parsed_list:
                            s = str(x).strip()
                            if s:
                                expanded.append(s)
                        continue
                except Exception:
                    pass
            expanded.append(tt)

        # 기본 필터: 너무 긴 값/JSON 찌꺼기/메타 단어 제거
        out = [t for t in expanded if 2 <= len(t) <= 40]
        out = [t for t in out if "[" not in t and "]" not in t and '\\"' not in t]
        out = [
            t
            for t in out
            if not re.fullmatch(r"(?i)k-?enter|kpop|k-pop|youtube|mv|views?|record", t)
        ]

        # 제목에 한글이 있으면(국내 기사) 로마자 인명(Firstname Lastname 형태)을 artist_tags로 두지 않는다.
        # 단, 제목에 그대로 등장하는 로마자 표기는 유지한다(예: "Le Sserafim"은 제목에 실제로 있음).
        has_hangul_in_title = bool(re.search(r"[가-힣]", title or ""))

        def _is_titlecase_phrase(s: str) -> bool:
            return bool(re.fullmatch(r"(?:[A-Z][a-zA-Z0-9]+)(?:\s+[A-Z][a-zA-Z0-9]+){1,3}", s.strip()))

        if has_hangul_in_title:
            out2: list[str] = []
            title_low = (title or "").lower()
            for t in out:
                if _is_titlecase_phrase(t) and t.lower() not in title_low:
                    # 제목에 없는 로마자 2~4단어(대개 인명/작품명) 제거
                    continue
                out2.append(t)
            out = out2

        # 작품/문구형 Title Case 2~4단어(예: "Perfect Crown")는 artist_tags에서 제거
        # 단, 제목에 그대로 등장하는 경우는 그룹명일 수 있으므로 유지한다.
        title_low = (title or "").lower()
        out = [
            t
            for t in out
            if not (_is_titlecase_phrase(t) and t.lower() not in title_low)
        ]

        # 직업/역할 꼬리표 최소화 (예: "김광균 시인" -> "김광균")
        cleaned: list[str] = []
        for t in out:
            t2 = re.sub(r"\s+(시인|배우|가수|작가|감독|프로듀서|아이돌|그룹|멤버|대표|회장)\b", "", t).strip()
            # 흔한 호칭/접미 제거 (예: "김향기표" -> "김향기", "OOO님/씨/군/양" 제거)
            t2 = re.sub(r"(표|님|씨|군|양)$", "", t2).strip()
            cleaned.append(t2 or t)
        out = cleaned

        # 일반 단어/조각 제거(태그에 섞여 들어오는 경우가 많음)
        junk = {
            "명곡",
            "데뷔",
            "회고",
            "영화",
            "개봉",
            "레전드",
            "합류",
            "귀환",
            "코미디",
            "게임",
            "파이터",
            "스트리트",
            "확정",
            "격투",
            "전설의",
            "영화화",
            "뮤직비디오",
            "뮤비",
            "신곡",
            "앨범",
            "콘서트",
            "투어",
            "차트",
            "기록",
            "조회수",
            "뷰",
            "뷰를",
            "신기록",
            "유튜브",
            "걸그룹",
            "보이그룹",
            "음원",
            "하나로",
            "결말",
            "파국",
            "최고",
            "최고의",
            "최악",
            "최악의",
            "논란",
            "화제",
            "관심",
            "조건부",
        }
        out = [t for t in out if t not in junk]

        # 한글 인명 필터용 성씨(최소 집합). 너무 크게 잡으면 오히려 false negative/positive 튜닝이 어려워진다.
        _KOREAN_SURNAMES = {
            "김",
            "이",
            "박",
            "최",
            "정",
            "강",
            "조",
            "윤",
            "장",
            "임",
            "한",
            "오",
            "서",
            "신",
            "권",
            "황",
            "안",
            "송",
            "류",
            "홍",
            "전",
            "고",
            "문",
            "양",
            "손",
            "배",
            "백",
            "허",
            "남",
            "심",
            "노",
            "하",
            "변",
            "주",
            "차",
            "유",
            "나",
            "민",
            "진",
        }
        _KOREAN_PARTICLE_ENDINGS = (
            "에",
            "의",
            "에서",
            "으로",
            "로",
            "을",
            "를",
            "은",
            "는",
            "이",
            "가",
            "와",
            "과",
            "도",
            "만",
            "까지",
        )

        # "허용 목록"은 원본 artist_tags에 한정한다.
        # keywords는 LLM이 작품명/프로그램명/형용사 등을 섞는 경우가 많아, 여길 근거로 쓰면 메인 화면 태그가 오염된다.
        _allow_exact = set(
            _as_list_of_str(original.get("artist_tags"))
        )

        def _looks_like_artist_name(tag: str) -> bool:
            s = tag.strip()
            if not s:
                return False
            if _is_korean_headline_binomial_junk(s):
                return False

            # 프로그램/작품명 suffix/패턴(자주 오염되는 경우) 차단
            # (예: "편스토랑", "런닝맨", "나는솔로" 등)
            if re.search(
                r"(스토랑|런닝맨|나는솔로|아침마당|미스트롯|나는가수다|전참시|놀뭐|쇼챔피언|뮤직뱅크|인기가요|쇼!?\s?음악중심)",
                s,
                re.IGNORECASE,
            ):
                return False

            # 조각/문장 끝 조사 제거: "선택에" 같은 것 차단
            for suf in _KOREAN_PARTICLE_ENDINGS:
                if s.endswith(suf) and len(s) > len(suf) + 1:
                    return False

            # 한글 다단어(공백 포함) 인명/그룹명 허용 (예: "아리아나 그란데", "르 세라핌" 등)
            # - 각 토큰은 2~10자 한글
            # - 2~3토큰까지 허용
            if re.fullmatch(r"[가-힣]{2,15}(?:\s+[가-힣]{2,15}){1,2}", s):
                # 너무 긴 구(문장)에 가까운 건 제외: 총 길이 제한
                if len(s) <= 24:
                    return True

            # 한글-only (그룹명 5~10자·비성씨 활동명 포함 — LLM 태그는 허용 폭을 넓힘)
            if re.fullmatch(r"[가-힣]+", s):
                if len(s) == 2:
                    _STAGE_ALLOW_2 = {
                        "아이유",
                        "수지",
                        "비비",
                        "지코",
                        "비",
                    }
                    return (
                        (s[0] in _KOREAN_SURNAMES)
                        or (s in _STAGE_ALLOW_2)
                        or (s in _allow_exact)
                    )
                if 3 <= len(s) <= 15:
                    return True
                return False

            # 영문 이름/그룹명: 알파벳/숫자/공백/&/./- 만 허용
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .&\\-]{1,49}", s):
                return True

            return False

        # 제목/문장/키워드 조각 제거: "대한민국에서 건물주 되는 법", "갈린다" 같은 것 차단
        out = [t for t in out if _looks_like_artist_name(t)]

        # 중복 제거
        uniq: list[str] = []
        for t in out:
            if t not in uniq:
                uniq.append(t)

        # 제목에 다단어 고유명사가 있으면(예: "아리아나 그란데", "미트 페어런츠"),
        # 조각 태그만 있는 경우 전체 구로 합쳐서 치환한다.
        title_text = (title or "").strip()
        if title_text:
            # 한글 다단어 구 추출 (2~3토큰)
            phrases = re.findall(r"[가-힣]{2,15}(?:\s+[가-힣]{2,15}){1,2}", title_text)
            for ph in phrases:
                if len(ph) > 20:
                    continue
                parts = [p for p in ph.split() if p]
                if len(parts) < 2:
                    continue
                # 조각이 모두 있으면 전체 구를 넣고 조각은 제거
                if all(p in uniq for p in parts):
                    for p in parts:
                        while p in uniq:
                            uniq.remove(p)
                    if ph not in uniq:
                        uniq.insert(0, ph)

        # 긴 이름이 존재할 때, 그 일부 조각(부분 문자열) 태그는 제거
        # 예: "아리아나 그란데"가 있으면 "아리아나", "그란데"는 제거
        def _key(s: str) -> str:
            return re.sub(r"\s+", "", s).lower()

        keys = [_key(t) for t in uniq]
        drop: set[int] = set()
        for i, ki in enumerate(keys):
            # 너무 짧은 토큰 처리:
            # - 짧은 영문 약어(예: YG, BTS)는 유지
            # - 한글(또는 혼합) 조각(예: "미트", "그란데")은 긴 태그에 포함되면 제거
            raw_i = uniq[i]
            is_short_ascii = bool(re.fullmatch(r"[A-Za-z]{2,5}", raw_i))
            if len(ki) < 2:
                continue
            for j, kj in enumerate(keys):
                if i == j:
                    continue
                # 다른 태그(더 긴 것)에 포함되면 드롭
                if len(kj) > len(ki) and ki and ki in kj:
                    if is_short_ascii:
                        # 영문 약어는 드롭하지 않음
                        break
                    drop.add(i)
                    break

        filtered = [t for idx, t in enumerate(uniq) if idx not in drop]

        # 너무 빈약하거나(1개 이하) 의미 없는 값만 남으면 빈 리스트로 처리해 상위에서 원본 유지로 빠지게 한다.
        if len(filtered) <= 1:
            only = filtered[0] if filtered else ""
            if only in {"K-Enter", "최고", "화제", "논란"}:
                return []

        return filtered

    refined_tags = _normalize_artist_tags(_as_list_of_str(d.get("artist_tags")))
    orig_tags = _normalize_artist_tags(_as_list_of_str(original.get("artist_tags")))

    title_for_check = title
    seen: set[str] = set()

    def _add_unique(xs: list[str], out: list[str]) -> None:
        for t in xs:
            if t not in seen:
                seen.add(t)
                out.append(t)

    def _extract_title_artist_candidates(title_text: str) -> list[str]:
        """제목에서 영문 그룹명/아티스트 후보를 뽑아 artist_tags 0번 앵커링에 사용."""
        t = (title_text or "").strip()
        if not t:
            return []
        # 영문/숫자 단어 2~4개 조합(Le Sserafim, BabyMonster 등)
        cands = re.findall(r"\b[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,2}\b", t)
        # 너무 일반적인 단어 제거
        stop = {
            "Kpop",
            "Kpop",
            "Kpop",
            "K",
            "Kpop",
            "The",
            "A",
            "An",
        }
        out: list[str] = []
        for c in cands:
            s = c.strip()
            if not s or s in stop:
                continue
            if s not in out:
                out.append(s)
        return out[:5]

    # 제목에서 한글 연속구 슬라이스로 태그를 뽑는 방식은 오탐이 많아 사용하지 않음(영문 후보만).
    _hc: list[str] = []
    _en = _normalize_artist_tags(_extract_title_artist_candidates(title_for_check))
    title_candidates = []
    _tc_seen: set[str] = set()
    for t in _hc + _en:
        if t not in _tc_seen:
            _tc_seen.add(t)
            title_candidates.append(t)

    # (1) 제목에 등장하는 태그 우선(제목 추출 후보 + 원본 + 리파인 전체에서)
    title_matched: list[str] = []
    for t in title_candidates + orig_tags + refined_tags:
        if _score_tag_by_title(t, title_for_check) and t not in seen:
            _add_unique([t], title_matched)

    title_low = (title_for_check or "").lower()

    _surnames_for_anchor = {
        "김",
        "이",
        "박",
        "최",
        "정",
        "강",
        "조",
        "윤",
        "장",
        "임",
        "한",
        "오",
        "서",
        "신",
        "권",
        "황",
        "안",
        "송",
        "류",
        "홍",
        "전",
        "고",
        "문",
        "양",
        "손",
        "배",
        "백",
        "허",
        "남",
        "심",
        "노",
        "하",
        "변",
        "주",
        "차",
        "유",
        "나",
        "민",
        "진",
    }
    _stage2_anchor = {"아이유", "수지", "비비", "지코", "비"}
    _anchor_whitelist = set(orig_tags) | set(refined_tags) | set(
        _as_list_of_str(original.get("artist_tags"))
    )

    def _in_title(tag: str) -> bool:
        t = (tag or "").strip()
        if not t:
            return False
        return t.lower() in title_low

    def _looks_like_artist_anchor(tag: str) -> bool:
        """
        제목에 포함돼도 artist_tags로 두면 안 되는 일반어(국가/장소/부사 등)를 걸러낸다.
        - 한글: 2~10자 인명/그룹명(2자는 성·무대명·원본 태그), 다단어 한글명사구
        - 영문: 약어(BTS) 또는 TitleCase 1~3단어(Le Sserafim)
        """
        s = (tag or "").strip()
        if not s:
            return False
        if _is_korean_headline_binomial_junk(s):
            return False

        # 대표적으로 자주 섞이는 일반어/부사/장소
        bad = {
            "뉴질랜드",
            "현지서",
            "현지",
            "학교",
            "텃세",
            "적응",
            "걱정",
            "겪은",
            "갈린다",
            "건물주",
            "조건부",
        }
        if s in bad:
            return False

        # 조사/부사형으로 끝나는 경우 차단
        if re.search(r"(에서|으로|로|에게|께|부터|까지|처럼|대로|마다|쯤|밖에|조차|마저|라도|이나|나|든지|서)$", s):
            return False

        # 한글 단일 토큰 2~10자 (방탄소년단·베이비몬스터·에스파 등)
        if re.fullmatch(r"[가-힣]{2,15}", s):
            if len(s) == 2:
                return (
                    (s[0] in _surnames_for_anchor)
                    or (s in _stage2_anchor)
                    or (s in _anchor_whitelist)
                )
            return True

        # 한글 다단어(2~3토큰) 허용 (예: 아리아나 그란데)
        if re.fullmatch(r"[가-힣]{2,15}(?:\s+[가-힣]{2,15}){1,2}", s) and len(s) <= 24:
            return True

        # 영문 약어/그룹명
        if re.fullmatch(r"[A-Z]{2,6}", s):
            return True

        # 영문 Title Case (Le Sserafim 같은)
        if re.fullmatch(r"[A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+){0,2}", s):
            return True

        return False

    def _reorder_artist_tags_entity_first(
        tags: list[str],
        *,
        title_text: str,
        keywords: list[str],
    ) -> list[str]:
        """따옴표 안 곡명·키워드에만 있는 라틴 짧은 토큰을 뒤로 보내 대표 태그(그룹/인물)를 앞에 둔다."""
        if len(tags) <= 1:
            return tags
        quoted: set[str] = set()
        for m in re.finditer(r"""[''`「『]([^''"`」』]{2,50})[''`」』]""", title_text or ""):
            quoted.add(m.group(1).strip().lower())
        kw_lower = {
            str(k).strip().lower()
            for k in (keywords or [])
            if isinstance(k, str) and str(k).strip()
        }

        def tier(i: int, t: str) -> tuple[int, int]:
            st = t.strip()
            if re.search(r"[가-힣]", st):
                return (0, i)
            tl = st.lower()
            if tl in quoted:
                return (3, i)
            if tl in kw_lower and re.fullmatch(r"[A-Z0-9]{2,25}", st):
                return (2, i)
            if tl in kw_lower:
                return (1, i)
            return (0, i)

        order = list(range(len(tags)))
        order.sort(key=lambda i: tier(i, tags[i]))
        return [tags[i] for i in order]

    # 제목에 매칭이 1개라도 있으면(=앵커가 있으면),
    # artist_tags는 "제목에 실제로 등장한 고유명사"만 남긴다.
    # 이 규칙이 없으면 LLM이 뽑은 일반 단어(국가/학교/걱정 등)가 태그로 섞여 메인 화면이 망가진다.
    if title_matched:
        kept: list[str] = []
        seen2: set[str] = set()
        for t in title_matched + orig_tags + refined_tags:
            if t in seen2:
                continue
            if _in_title(t) and _looks_like_artist_anchor(t):
                seen2.add(t)
                kept.append(t)
        if kept:
            kws_for_order = _as_list_of_str(d.get("keywords"))
            kept = _reorder_artist_tags_entity_first(
                kept,
                title_text=title_for_check or "",
                keywords=kws_for_order,
            )
            d["artist_tags"] = kept[:10]
            _apply_title_tts_consensus_recovery(d, original)
            return d

        # 제목에 인물명이 있는데도 kept가 비면, 제목 앞 절(첫 쉼표 전)에서만 한글 후보를 복구한다.
        title_text = title_for_check or ""
        primary_seg = re.split(r"[,，]", title_text, 1)[0]
        orig_allow_rec = set(_as_list_of_str(original.get("artist_tags")))
        recovered: list[str] = []
        seen_r: set[str] = set()
        for m in re.finditer(r"[가-힣]{2,15}", primary_seg):
            n = m.group(0)
            if n in seen_r:
                continue
            ok = False
            if len(n) == 2:
                ok = (
                    (n[0] in _surnames_for_anchor)
                    or (n in _stage2_anchor)
                    or (n in orig_allow_rec)
                )
            elif 3 <= len(n) <= 4:
                ok = (n[0] in _surnames_for_anchor) or (n in orig_allow_rec)
            else:
                ok = len(n) >= 5
            if ok:
                recovered.append(n)
                seen_r.add(n)
            if len(recovered) >= 5:
                break
        d["artist_tags"] = recovered[:10] if recovered else ["K-Enter"]
        _apply_title_tts_consensus_recovery(d, original)
        return d

    # (2) 원본 나머지(제목 비매칭 포함) — 원본이 이미 괜찮다면 순서를 최대한 보존
    orig_rest: list[str] = []
    _add_unique(orig_tags, orig_rest)

    # (3) 리파인 추가분(원본에 없던 것)
    refined_extra: list[str] = []
    _add_unique(refined_tags, refined_extra)

    merged = (title_matched + orig_rest + refined_extra)[:10]
    if not merged:
        # title_matched가 비었을 때(한글-only 제목 + 원본 K-Enter만 등): 제목·후보에서 직접 복구
        fb: list[str] = []
        seen_fb: set[str] = set()
        for t in _hc + _en + orig_rest + refined_extra:
            if not t or t in seen_fb:
                continue
            if not _in_title(t) or not _looks_like_artist_anchor(t):
                continue
            seen_fb.add(t)
            fb.append(t)
        merged = fb[:10]
    if merged:
        merged = _reorder_artist_tags_entity_first(
            merged,
            title_text=title_for_check or "",
            keywords=_as_list_of_str(d.get("keywords")),
        )
    d["artist_tags"] = merged if merged else ["K-Enter"]

    _apply_title_tts_consensus_recovery(d, original)
    return d


def _quality_ok(d: dict) -> tuple[bool, str]:
    s = d.get("summary") or []
    se = d.get("summary_en") or []
    kws = d.get("keywords") or []
    if not (isinstance(s, list) and 4 <= len(s) <= 6):
        return False, f"summary={len(s) if isinstance(s, list) else 'N/A'}"
    if not (isinstance(se, list) and len(se) == len(s) and 4 <= len(se) <= 6):
        return False, f"summary_en={len(se) if isinstance(se, list) else 'N/A'}"
    if not (isinstance(kws, list) and len(kws) == 5):
        return False, f"keywords={len(kws) if isinstance(kws, list) else 'N/A'}"
    return True, "ok"


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


def _resolve_ids(
    session,
    *,
    ids: list[int] | None,
    order_desc: bool,
    limit: int | None,
    offset: int,
) -> list[int]:
    if ids:
        return sorted(set(ids))
    q = session.query(ProcessedNews.id)
    o = ProcessedNews.id.desc() if order_desc else ProcessedNews.id.asc()
    q = q.order_by(o).offset(max(0, offset))
    if limit is not None:
        q = q.limit(limit)
    return [r[0] for r in q.all()]


def _run_one(
    session,
    *,
    base_url: str,
    processed_id: int,
    notes: str,
    model: str,
    temperature: float,
    timeout: float,
    max_tokens: int,
    use_json_mode: bool,
    auto_retry: bool,
    schema_retry: bool,
    dry_run: bool,
    preserve_artist_tags: bool = False,
) -> tuple[str, str | None]:
    """
    Returns:
        (status, error_detail) — status: ok | skip | err
    """
    proc = (
        session.query(ProcessedNews)
        .options(joinedload(ProcessedNews.raw))
        .filter(ProcessedNews.id == processed_id)
        .first()
    )
    if proc is None:
        return "err", "processed_news 행 없음"

    title = ""
    if proc.raw:
        title = proc.raw.title or ""
    else:
        r = session.query(RawNews).filter(RawNews.id == proc.raw_news_id).first()
        title = (r.title or "") if r else ""

    processed_dict = processed_news_row_to_dict(proc)
    user_message = build_refine_user_message(title=title, notes=notes, processed=processed_dict)

    try:
        raw_text = _call_llm(
            base_url=base_url,
            user_message=user_message,
            model=model,
            temperature=temperature,
            timeout=timeout,
            max_tokens=max_tokens,
            json_mode=use_json_mode,
        )
    except Exception as e:
        return "err", f"LLM API: {e}"

    parsed: dict | None = None
    parse_hint: str | None = None
    try:
        parsed, parse_hint = parse_llm_json(raw_text)
    except json.JSONDecodeError as err_first:
        if auto_retry:
            try:
                raw_text2 = _call_llm(
                    base_url=base_url,
                    user_message=user_message + RETRY_USER_EXTRA,
                    model=model,
                    temperature=0.0,
                    timeout=timeout,
                    max_tokens=max_tokens,
                    json_mode=False,
                )
                parsed, parse_hint = parse_llm_json(raw_text2)
            except (json.JSONDecodeError, Exception) as e2:
                return "err", f"JSON 파싱 실패: {err_first} / 재시도: {e2}"
        else:
            return "err", f"JSON 파싱: {err_first}"

    if parsed is None:
        return "err", "parsed is None"

    parsed = _sanitize_refine_dict(
        refined=parsed,
        original=processed_dict,
        preserve_artist_tags=preserve_artist_tags,
    )

    # summary_en이 비는 케이스가 빈번해서(특히 해외기사), 영문 요약만 강제 보강 재시도를 1회 수행한다.
    def _needs_summary_en_fix(d: dict) -> bool:
        se = d.get("summary_en")
        if not isinstance(se, list) or len(se) < 4:
            return True
        # content가 비어있는 카드가 많으면 실패로 간주
        empty_cnt = 0
        for it in se:
            if not isinstance(it, dict) or not str(it.get("content") or "").strip():
                empty_cnt += 1
        return empty_cnt >= 2

    if _needs_summary_en_fix(parsed):
        try:
            retry_suffix = (
                "\n\n[summary_en 보강 재시도] 직전 출력에서 summary_en이 비었거나(또는 4~6장 미만) 품질이 낮습니다.\n"
                "- summary는 그대로 두고, summary_en만 영어로 4~6장 채워라.\n"
                "- summary_en의 카드 수는 summary와 반드시 같게 맞춰라.\n"
                "- JSON 객체 1개만 출력.\n"
            )
            raw_text_se = _call_llm(
                base_url=base_url,
                user_message=user_message + retry_suffix,
                model=model,
                temperature=0.0,
                timeout=timeout,
                max_tokens=max_tokens,
                json_mode=False,
            )
            parsed_se, parse_hint_se = parse_llm_json(raw_text_se)
            parsed_se = _sanitize_refine_dict(
                refined=parsed_se,
                original=processed_dict,
                preserve_artist_tags=preserve_artist_tags,
            )
            parsed = parsed_se
            if parse_hint and parse_hint_se:
                parse_hint = f"{parse_hint} | summary_en-retry: {parse_hint_se}"
            elif parse_hint_se:
                parse_hint = f"summary_en-retry: {parse_hint_se}"
        except Exception:
            # 실패해도 기존 parsed로 계속 진행 (quality gate가 최종 차단)
            pass

    try:
        validated = KpopNewsSummary(**copy.deepcopy(parsed))
    except ValidationError as e:
        if not (auto_retry and schema_retry):
            return "err", f"스키마: {e.errors()[:3]}"
        try:
            raw_text_schema = _call_llm(
                base_url=base_url,
                user_message=user_message + REFINE_VALIDATION_RETRY_USER_SUFFIX,
                model=model,
                temperature=0.0,
                timeout=timeout,
                max_tokens=max_tokens,
                json_mode=False,
            )
            parsed2, parse_hint2 = parse_llm_json(raw_text_schema)
            parsed2 = _sanitize_refine_dict(
                refined=parsed2,
                original=processed_dict,
                preserve_artist_tags=preserve_artist_tags,
            )
            validated = KpopNewsSummary(**copy.deepcopy(parsed2))
            parsed = parsed2
            if parse_hint and parse_hint2:
                parse_hint = f"{parse_hint} | schema-retry: {parse_hint2}"
            elif parse_hint2:
                parse_hint = f"schema-retry: {parse_hint2}"
        except Exception as e2:
            return "err", f"스키마: {e.errors()[:3]} · 재시도: {e2}"

    ok, reason = _quality_ok(parsed)
    if not ok:
        return "skip", f"품질 기준 미달({reason}) — DB 덮어쓰기 생략"

    if dry_run:
        return "ok", parse_hint

    apply_refined_to_processed(session, processed_id, validated, parsed)
    return "ok", parse_hint


def main() -> int:
    p = argparse.ArgumentParser(description="1-1차 refine 배치 (processed_news 덮어쓰기)")
    p.add_argument("--dry-run", action="store_true", help="LLM은 호출하되 DB는 갱신하지 않음")
    p.add_argument("--limit", type=int, default=None, help="처리 건수 상한 (기본: 전체)")
    p.add_argument("--offset", type=int, default=0, help="건너뛸 행 수 (order 적용 후)")
    p.add_argument(
        "--order",
        choices=("desc", "asc"),
        default="desc",
        help="processed_news.id 정렬 (기본: desc 최신 먼저)",
    )
    p.add_argument(
        "--ids",
        type=str,
        default="",
        help="쉼표로 구분한 processed_news id만 (예: 1,2,3). 쉼표 뒤 공백 금지 — 공백 있으면 나머지가 별도 인자로 잡혀 오류 남",
    )
    p.add_argument("--sleep", type=float, default=0.0, help="각 건 처리 후 대기(초)")
    p.add_argument(
        "--chunk-size",
        type=int,
        default=10,
        help="이 개수마다 한 묶음으로 처리·요약 로그 (0이면 청크 구분 없이 전체 한 번에)",
    )
    p.add_argument(
        "--sleep-between-chunks",
        type=float,
        default=0.0,
        help="청크(묶음)가 끝날 때마다 추가 대기(초). 마지막 청크 뒤에는 쉬지 않음",
    )
    p.add_argument("--notes", type=str, default="", help="유저 메시지 [팀 메모]")
    p.add_argument("--fail-fast", action="store_true", help="첫 오류에서 중단")
    p.add_argument("--no-json-mode", action="store_true", help='response_format json_object 끄기')
    p.add_argument("--no-retry", action="store_true", help="JSON 파싱 실패 시 재시도 안 함")
    p.add_argument(
        "--no-schema-retry",
        action="store_true",
        help="Pydantic 검증 실패 시 두 번째 LLM 호출 안 함(후처리만)",
    )
    p.add_argument(
        "--preserve-artist-tags",
        action="store_true",
        help="artist_tags는 DB 기존 값 유지(LLM 출력·태그 후처리·보강 적용 안 함)",
    )

    p.add_argument("--model", default=os.getenv("LLM_MODEL", "gemma3:latest"))
    p.add_argument("--base-url", default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"))
    p.add_argument("--temperature", type=float, default=0.3)
    p.add_argument("--timeout", type=float, default=180.0)
    p.add_argument("--max-tokens", type=int, default=int(os.getenv("LLM_MAX_TOKENS", "8192")))

    args = p.parse_args()

    id_list: list[int] | None = None
    if args.ids.strip():
        id_list = [int(x.strip()) for x in args.ids.split(",") if x.strip()]

    use_json_mode = not args.no_json_mode
    auto_retry = not args.no_retry
    schema_retry = not args.no_schema_retry

    with get_session() as session:
        ids = _resolve_ids(
            session,
            ids=id_list,
            order_desc=(args.order == "desc"),
            limit=args.limit,
            offset=args.offset,
        )

    cs = int(args.chunk_size)
    if cs <= 0:
        chunks: list[list[int]] = [ids]
    else:
        chunks = [ids[i : i + cs] for i in range(0, len(ids), cs)]

    print(
        f"[batch_refine] 대상 {len(ids)}건 · 청크 {len(chunks)}개(chunk-size={cs if cs > 0 else '전체'}) "
        f"· dry_run={args.dry_run} · preserve_artist_tags={args.preserve_artist_tags} · "
        f"model={args.model!r} · LLM=urllib( /v1/chat/completions )",
        flush=True,
    )
    if not ids:
        print("대상 id가 없습니다.", flush=True)
        return 0

    ok = skip = fail = 0
    t0 = time.perf_counter()
    global_idx = 0

    with get_session() as session:
        for cn, chunk in enumerate(chunks, start=1):
            c_ok = c_skip = c_fail = 0
            print(
                f"--- 청크 {cn}/{len(chunks)} 시작 · id {chunk[0]} … {chunk[-1]} ({len(chunk)}건) ---",
                flush=True,
            )
            for pid in chunk:
                global_idx += 1
                t_row = time.perf_counter()
                status, detail = _run_one(
                    session,
                    base_url=args.base_url,
                    processed_id=pid,
                    notes=args.notes,
                    model=args.model,
                    temperature=args.temperature,
                    timeout=args.timeout,
                    max_tokens=args.max_tokens,
                    use_json_mode=use_json_mode,
                    auto_retry=auto_retry,
                    schema_retry=schema_retry,
                    dry_run=args.dry_run,
                    preserve_artist_tags=args.preserve_artist_tags,
                )
                elapsed = time.perf_counter() - t_row
                if status == "ok":
                    ok += 1
                    c_ok += 1
                    extra = f" · {detail}" if detail else ""
                    print(
                        f"  [{global_idx}/{len(ids)}] OK id={pid} {elapsed:.1f}s{extra}",
                        flush=True,
                    )
                elif status == "skip":
                    skip += 1
                    c_skip += 1
                    print(
                        f"  [{global_idx}/{len(ids)}] SKIP id={pid} {elapsed:.1f}s · {detail}",
                        flush=True,
                    )
                else:
                    fail += 1
                    c_fail += 1
                    print(
                        f"  [{global_idx}/{len(ids)}] FAIL id={pid} {elapsed:.1f}s · {detail}",
                        flush=True,
                    )
                    if args.fail_fast:
                        print("fail-fast 중단.", flush=True)
                        return 1

                if args.sleep > 0 and global_idx < len(ids):
                    time.sleep(args.sleep)

            print(
                f"--- 청크 {cn}/{len(chunks)} 끝 · 이 청크 OK={c_ok} SKIP={c_skip} FAIL={c_fail} ---",
                flush=True,
            )
            if (
                args.sleep_between_chunks > 0
                and cn < len(chunks)
            ):
                time.sleep(args.sleep_between_chunks)

    total = time.perf_counter() - t0
    print(
        f"[batch_refine] 완료 OK={ok} SKIP={skip} FAIL={fail} 총 {total:.1f}s",
        flush=True,
    )
    return 0 if fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
