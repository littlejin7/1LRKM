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

_DIR = Path(__file__).resolve().parent
_ROOT = _DIR.parent

# 상위 폴더(root)와 현재 폴더(REFINE)를 path에 추가하여 database, schemas 및 로컬 모듈 로드 가능케 함
for p in [_DIR, _ROOT]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from pydantic import ValidationError
from sqlalchemy.orm import joinedload

from database import ProcessedNews, RawNews, get_session
from refine_prompts import (
    REFINE_VALIDATION_RETRY_USER_SUFFIX,
    SUMMARY_REFINE_SYSTEM_PROMPT,
    build_refine_user_message,
)
from refine_db import apply_refined_to_processed, processed_news_row_to_dict
from refine_json_parse import parse_llm_json
from schemas import KpopNewsSummary

from refine_llm_client import _call_llm
from refine_helpers import _sanitize_refine_dict, _quality_ok


RETRY_USER_EXTRA = (
    "\n\n[출력 규칙] 위와 동일한 키 구조의 JSON 객체 하나만 출력. "
    "설명·마크다운·코드펜스 금지."
)






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
