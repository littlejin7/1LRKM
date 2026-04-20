"""Few-shot (최신 객체형 summary 구조 반영)."""

from __future__ import annotations

# 주의: 예시는 반드시 "순수 JSON"만 포함해야 합니다.
FEWSHOT_BLOCK = r"""
[FEW-SHOT 예시 1]
{
  "summary": [
    {"label": "투어 공개", "content": "그룹 A가 새 월드투어 일정을 공개했습니다."},
    {"label": "도시 범위", "content": "투어는 아시아와 북미 여러 도시에서 진행될 예정입니다."},
    {"label": "예매 안내", "content": "소속사는 티켓 예매 일정과 공연장 정보를 함께 안내했습니다."},
    {"label": "추가 검토", "content": "일부 도시는 추가 회차 편성을 검토 중이라고 밝혔습니다."}
  ],
  "summary_en": [
    {"label": "Tour Announcement", "content": "Group A announced new dates for its world tour."},
    {"label": "City Coverage", "content": "The tour is expected to cover multiple cities across Asia and North America."},
    {"label": "Ticketing Info", "content": "The agency shared ticketing dates along with venue information."},
    {"label": "Additional Shows", "content": "It added that additional shows are being considered for some cities."}
  ],
  "artist_tags": ["Group A"],
  "keywords": ["월드투어", "티켓 예매", "공연 일정", "도시 확장", "글로벌 활동"],
  "category": "콘서트/투어",
  "sub_category": "콘서트/투어",
  "source_name": "연예뉴스",
  "language": "ko",
  "ko_title": "그룹 A, 아시아 및 북미 월드투어 일정 전격 공개",
  "is_k_ent": true,
  "sentiment": "중립",
  "sentiment_score": null,
  "importance": 6,
  "importance_reason": "[IP2+사건2+파급1+기본1=6] 대형 그룹의 신규 투어 소식으로 파급력이 높습니다.",
  "trend_insight": "엔데믹 이후 대규모 월드투어 규모가 점차 확대되는 추세입니다.",
  "tts_text": "그룹 에이가 아시아와 북미를 아우르는 새 월드투어 일정을 공개했습니다. 티켓 예매 정보와 함께 추가 공연 검토 소식까지 전해지며 팬들의 기대감이 높아지고 있습니다."
}

[FEW-SHOT 예시 2 — 아티스트 없는 경우]
{
  "summary": [
    {"label": "협업 검토", "content": "해외 매체는 한 기획사가 신규 플랫폼 협업을 검토 중이라고 보도했습니다."},
    {"label": "수치 부재", "content": "기사에는 협업의 구체적 규모나 금액 등 정량 정보는 포함되지 않았습니다."},
    {"label": "확정 미정", "content": "다만 최종 계약 여부나 일정은 아직 확정되지 않았다고 전해졌습니다."},
    {"label": "업계 흐름", "content": "소식은 업계 전반의 유통 채널 다변화 흐름과 맞물려 해석될 여지가 있습니다."}
  ],
  "summary_en": [
    {"label": "Partnership Review", "content": "An overseas outlet reported that an agency is considering a new platform partnership."},
    {"label": "No Figures", "content": "The article does not include numeric details such as scale or financial terms."},
    {"label": "Not Finalized", "content": "However, the final decision and timeline were said to be unconfirmed."},
    {"label": "Industry Context", "content": "The news is being read in the context of broader distribution diversification in the industry."}
  ],
  "artist_name": "",
  "keywords": ["플랫폼 협업", "유통 채널", "검토 단계", "해외 보도", "산업 전략"],
  "category": "산업/기획사",
  "sub_category": "산업/기획사",
  "source_name": "글로벌 비즈",
  "language": "ko",
  "ko_title": "대형 기획사, 신규 플랫폼 협업 검토 중",
  "is_k_ent": true,
  "sentiment": "중립",
  "importance": 3,
  "importance_reason": "[IP0+사건1+파급1+기본1=3] 특정 아티스트 소식은 아니나 업계 유통 구조 변화를 시사합니다.",
  "trend_insight": "콘텐츠 유통 채널의 다변화가 가속화되고 있습니다.",
  "tts_text": "한 대형 기획사가 신규 플랫폼과의 협업을 검토 중이라는 소식입니다. 아직 구체적인 규모나 계약 여부는 확정되지 않았으나, 업계의 유통 채널 다변화 흐름을 보여주는 사례로 풀이됩니다."
}
"""