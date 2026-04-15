"""좌측 패널(요약/브리핑/키워드/TTS/importance) 품질 규칙."""

from __future__ import annotations

RULES_LEFT_PANEL = """
[필드별 엄격 규칙]
- summary: 한국어 완결 문장 배열. 정확히 5~7문장. 같은 말 반복으로 문장 수를 채우지 마라.
- summary_en: 영어 완결 문장 배열. summary와 문장 개수(5~7)와 순서가 정확히 1:1 대응되게 번역하라.
  - i번째 summary_en 문장은 i번째 summary 문장의 번역이어야 한다.
- artist_tags: 제목/본문에 실제로 등장한 뮤지션·그룹·솔로명. 없으면 [].
- keywords: 정확히 5개. artist_tags에 포함된 인명/그룹명은 넣지 말고, 테마·형식·행사·차트명 등 비인명 축으로만.
- briefing: 정확히 3개.
  - label: 2~10자 한글 명사구(짧고 구체).
  - content: 본문 근거 한 줄(존댓말). 3줄은 서로 다른 관점으로 중복을 피하라.
- sentiment: "긍정"|"부정"|"중립" 중 하나(한글).
- sentiment_score: 항상 null로 출력하라. (점수는 백엔드에서 sentiment/importance로 계산한다)
- importance: 1~10 정수.
- importance_reason: 반드시 `[IPa+사건b+파급c+기본1=총점] 근거 한 문장` 형식.
  - a,b,c는 각각 0~3 정수
  - 총점 = a+b+c+1
  - 총점은 importance 값과 정확히 일치
- tts_text: 한국어 구어체 라디오 브리핑(150~220자 권장).
  - URL/해시태그/이모지/마크다운/코드펜스/특수 괄호(【】「」) 금지.
  - 숫자는 읽기 좋게 한글 혼합 표기(예: 641000 → 64만 1천).
"""

