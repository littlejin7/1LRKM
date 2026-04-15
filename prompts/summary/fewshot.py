"""Few-shot (짧게, 빈 값 케이스 포함)."""

from __future__ import annotations

# 주의: 예시는 반드시 "순수 JSON"만. 주석/설명/마크다운 금지.
FEWSHOT_BLOCK = r"""
[FEW-SHOT 예시 1 — 최소 형식(빈 배열/빈 문자열 케이스 없음)]
예시 출력(JSON):
{
  "summary": [
    "그룹 A가 새 월드투어 일정을 공개했다.",
    "투어는 아시아와 북미 여러 도시에서 진행될 예정이다.",
    "소속사는 티켓 예매 일정과 공연장 정보를 함께 안내했다.",
    "일부 도시는 추가 회차 편성을 검토 중이라고 밝혔다.",
    "이번 투어는 글로벌 활동 확장 전략의 일환으로 해석된다."
  ],
  "summary_en": [
    "Group A announced new dates for its world tour.",
    "The tour is expected to cover multiple cities across Asia and North America.",
    "The agency shared ticketing dates along with venue information.",
    "It added that additional shows are being considered for some cities.",
    "The tour is being viewed as part of the group's strategy to expand global activities."
  ],
  "artist_tags": ["Group A"],
  "keywords": ["월드투어", "티켓 예매", "공연 일정", "도시 확장", "글로벌 활동"],
  "briefing": [
    {"label": "투어 공개", "content": "새 월드투어 일정과 도시 목록이 공개됐습니다."},
    {"label": "예매 안내", "content": "티켓 예매 일정과 공연장 정보가 함께 안내됐습니다."},
    {"label": "확장 검토", "content": "일부 도시는 추가 회차 편성을 검토 중입니다."}
  ],
  "sub_category": "콘서트/투어",
  "sentiment": "중립",
  "sentiment_score": null,
  "importance": 6,
  "importance_reason": "[IP2+사건2+파급1+기본1=6] 투어 확대로 관심은 크지만 정량 성과는 본문에 없습니다.",
  "tts_text": "그룹 A가 새 월드투어 일정을 공개했습니다. 아시아와 북미 여러 도시를 포함하고, 티켓 예매 일정과 공연장 정보도 함께 안내됐는데요. 일부 도시는 추가 회차도 검토 중이라 향후 업데이트가 주목됩니다."
}

[FEW-SHOT 예시 2 — 빈 값 케이스(artist=[] 가능)]
예시 출력(JSON):
{
  "summary": [
    "해외 매체는 한 기획사가 신규 플랫폼 협업을 검토 중이라고 보도했다.",
    "기사에는 협업의 구체적 규모나 금액 등 수치 정보는 포함되지 않았다.",
    "소식은 업계 전반의 유통 채널 다변화 흐름과 맞물려 해석된다.",
    "다만 최종 계약 여부나 일정은 아직 확정되지 않았다고 전해졌다.",
    "현재로서는 검토 단계의 보도라는 점이 핵심이다."
  ],
  "summary_en": [
    "An overseas outlet reported that an agency is considering a new platform partnership.",
    "The article does not include numeric details such as scale or financial terms.",
    "The news is being read in the context of broader distribution diversification in the industry.",
    "However, the final decision and timeline were said to be unconfirmed.",
    "For now, the key point is that this remains at a review stage."
  ],
  "artist_tags": [],
  "keywords": ["플랫폼 협업", "유통 채널", "검토 단계", "해외 보도", "산업 전략"],
  "briefing": [
    {"label": "협업 검토", "content": "신규 플랫폼 협업을 검토 중이라는 보도가 나왔습니다."},
    {"label": "수치 부재", "content": "규모·금액 등 정량 정보는 기사에 없었습니다."},
    {"label": "확정 미정", "content": "최종 계약 여부와 일정은 아직 확정되지 않았습니다."}
  ],
  "sub_category": "기타",
  "sentiment": "중립",
  "sentiment_score": null,
  "importance": 5,
  "importance_reason": "[IP1+사건2+파급1+기본1=5] 산업 협업 이슈지만 확정 정보가 제한적입니다.",
  "tts_text": "해외 매체가 한 기획사의 신규 플랫폼 협업 검토 소식을 전했습니다. 다만 규모나 금액 같은 구체 수치는 없고, 최종 계약 여부와 일정도 아직 확정되지 않았다고 하는데요. 업계 유통 채널 변화 흐름 속에서 후속 발표를 지켜볼 필요가 있습니다."
}
"""

