"""1-1차 출력이 따를 계약 — 상세(SSOT는 schemas.KpopNewsSummary)."""

from __future__ import annotations

OUTPUT_SCHEMA_REFINE_BLOCK = r"""
[출력 JSON 계약 — 1-1차]
**목표:** 입력 `processed`와 **같은 키**로, 값만 품질 개선. 루트에 임의 필드 추가 금지(입력에 없던 키를 새로 만들지 마라).
**검증 기준은 `schemas.KpopNewsSummary`와 동일**하다. DB에서 온 dict에 `briefing`, `url` 등이 있으면 **그대로 유지**해도 된다(스키마 extra 무시).

**반드시 유지할 타입·형태**
- **summary**: `[{"label": str, "content": str}, ...]` 객체 배열. **문자열 단일 문단 금지.**
  - **카드 개수: 4~6개가 목표.** 입력이 7개 이상이면 병합해 4~6으로 맞출 것. 4~6이면 유지.
- **summary_en**: summary 와 **같은 길이**의 객체 배열. 각 원소 `label` + `content`. **`label`/`content`에 `Auto` 금지**(백엔드 더미로 간주).
- **문자열 필드** (`tts_text`, `ko_title` 등): 값이 없으면 **`""`**. JSON **`null` 금지**(스키마 검증 실패).
- **trend_insight**: 1-1차에서는 **`""`만**(RAG 단계에서 별도 생성). **`null` 금지**.
- **keywords**: 문자열 배열. 일반적으로 **정확히 5개**(입력이 이미 5개면 유지).
- **category**: `컨텐츠 & 작품` | `인물 & 아티스트` | `비즈니스 & 행사` 중 하나(전체 문자열).
- **sub_category**: 허용 중분류 목록 중 하나(위 [분류 필드]).
- **ko_title**: 비어 있지 않은 문자열(한국어).
- **sentiment**: `긍정` | `부정` | `중립`
- **importance**: 1~10 정수. **importance_reason** 의 `[IPa+사건베+파급씨+기본1=총점]` 합이 importance 와 맞을 것.
- **timeline**: 보통 `[]`. 입력과 동일하게 유지 권장.
- **chart_data**: 없으면 `null`.
- **tts_text**: 구어체 브리핑 문자열(과도하게 길게 부풀리지 말 것).

**1-1차에서 자주 손보는 필드**
- summary[].label / summary[].content
- summary_en[].label / summary_en[].content
- ko_title
- (선택) tts_text — 입력이 어색할 때만, 한국어 구어체 유지

**손대지 않는 편이 좋은 필드(입력이 정상일 때)**
- raw_news_id, url, published_at, thumbnail_url 등 **식별·메타**
- is_rag_used, rag_sources — 입력 값 유지

**잘못된 출력 예(금지)**
- 루트가 `{}` 이거나 summary 키 없음
- summary 를 문자열로 바꿈
- **summary 가 7장 이상으로 방치**(4~6으로 병합할 것) 또는 **1장으로만 압축**
- summary_en 길이 ≠ summary 길이 · summary_en 에 `"Auto"` 라벨
- `trend_insight`: null (→ **`""`**)
- keywords 가 빈 배열이 되게 만듦(가능하면 **5개** 유지·보강)
"""
