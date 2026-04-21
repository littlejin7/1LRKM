"""Few-shot — 교정 전/후 쌍. 나쁜 예는 최소화하고 정답 구조를 명확히 제시한다."""

from __future__ import annotations

# gemma3 주의: "나쁜 예"를 길게 보여주면 오히려 따라 함.
# 입력(before)은 문제 필드만 발췌, 출력(after)은 완전한 정답 구조로 제시.
FEWSHOT_REFINE_BLOCK = r"""
[FEW-SHOT 안내 — 반드시 읽을 것]
- 아래 "입력" 블록은 **문제가 있는 필드만 발췌**한 예시다. 실제 출력은 유저 메시지의 **[현재 processed JSON]에 있던 키를 빠짐없이** 포함한 **한 개의 객체**여야 한다(발췌본만 내보내지 마라).
- "출력" 예시에 발췌 입력에 없던 필드(예: summary_en)가 나오면, 그것은 **실제 전체 입력에 이미 존재하는 해당 필드를 같은 순서로 고친 결과**를 보여 주기 위함이다. **없던 키를 지어내지 마라.**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[FEW-SHOT 예시 A — label·ko_title 교정]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

입력 (문제 있는 부분 발췌):
{
  "summary": [
    {"label": "기자:", "content": "소속사는 공식 입장을 발표했습니다."},
    {"label": "4대 합작, 글로벌 페스티벌, 일정 미정", "content": "업계는 추가 협의를 기다리고 있습니다."},
    {"label": "HYBE reported to police", "content": "경찰 조사 가능성이 거론되었습니다."},
    {"label": "내용:", "content": "티켓 정책은 아직 확정되지 않았습니다."}
  ],
  "ko_title": "Article about industry merger"
}

출력 (교정 결과 — 이 형태로 출력하라):
{
  "summary": [
    {"label": "소속사 입장", "content": "소속사는 공식 입장을 발표했습니다."},
    {"label": "합작 페스티벌", "content": "업계는 추가 협의를 기다리고 있습니다."},
    {"label": "경찰 고발", "content": "경찰 조사 가능성이 거론되었습니다."},
    {"label": "티켓 미확정", "content": "티켓 정책은 아직 확정되지 않았습니다."}
  ],
  "summary_en": [
    {"label": "Agency Statement", "content": "The agency officially released its position on the matter."},
    {"label": "Joint Festival", "content": "The industry is awaiting further negotiations."},
    {"label": "Police Report", "content": "The possibility of a police investigation has been raised."},
    {"label": "Ticketing TBD", "content": "The ticketing policy has yet to be finalized."}
  ],
  "ko_title": "4대 기획사 합작 페스티벌 추진 및 법적 분쟁 가능성"
}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[FEW-SHOT 예시 B — summary_en Auto 교정 + 카드 수 병합]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

입력 (문제 있는 부분 발췌):
{
  "summary": [
    {"label": "컴백 발표", "content": "그룹 B가 신보 컴백 일정을 발표했습니다."},
    {"label": "타이틀곡", "content": "타이틀곡은 팝 장르 기반으로 제작되었습니다."},
    {"label": "쇼케이스", "content": "온라인 쇼케이스가 발매일에 진행될 예정입니다."},
    {"label": "팬 반응", "content": "팬들은 SNS에서 큰 기대감을 표출했습니다."},
    {"label": "음반 구성", "content": "이번 앨범은 총 8곡으로 구성됩니다."},
    {"label": "유통 채널", "content": "주요 스트리밍 플랫폼에서 동시 발매됩니다."},
    {"label": "해외 반응", "content": "해외 팬들도 큰 관심을 보이고 있습니다."}
  ],
  "summary_en": [
    {"label": "Auto", "content": "Auto generated."},
    {"label": "Auto", "content": "Auto generated."},
    {"label": "Auto", "content": "Auto generated."},
    {"label": "Auto", "content": "Auto generated."},
    {"label": "Auto", "content": "Auto generated."},
    {"label": "Auto", "content": "Auto generated."},
    {"label": "Auto", "content": "Auto generated."}
  ]
}

출력 (7개 → 5개로 병합, summary_en Auto 전부 교체):
{
  "summary": [
    {"label": "컴백 일정", "content": "그룹 B가 신보 컴백 일정과 타이틀곡 장르를 발표했습니다."},
    {"label": "온라인 쇼케이스", "content": "발매일에 온라인 쇼케이스가 진행될 예정입니다."},
    {"label": "앨범 구성", "content": "이번 앨범은 총 8곡으로 구성되며 주요 스트리밍 플랫폼에서 동시 발매됩니다."},
    {"label": "팬 기대감", "content": "국내외 팬들은 SNS에서 큰 기대감을 표출했습니다."},
    {"label": "글로벌 반응", "content": "해외 팬들도 컴백 소식에 높은 관심을 보이고 있습니다."}
  ],
  "summary_en": [
    {"label": "Comeback Schedule", "content": "Group B announced the comeback date and title track genre for their new album."},
    {"label": "Online Showcase", "content": "An online showcase is scheduled to take place on the release date."},
    {"label": "Album Details", "content": "The album consists of 8 tracks and will be released simultaneously on major streaming platforms."},
    {"label": "Fan Anticipation", "content": "Fans worldwide have expressed high expectations across social media."},
    {"label": "Global Interest", "content": "International fans are also showing strong interest in the upcoming comeback."}
  ]
}
"""

FEWSHOT_REFINE_BLOCK += r"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[FEW-SHOT 예시 C — artist_tags: 그룹 vs 곡명]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

입력 (문제 있는 부분 발췌):
{
  "ko_title": "BabyMonster, 'SHEESH' 뮤직비디오 4억 뷰 돌파",
  "artist_tags": ["SHEESH", "BabyMonster"],
  "keywords": ["SHEESH", "뮤직비디오", "4억", "뷰", "기록"]
}

출력 (교정 결과 — 이 형태로 출력하라):
{
  "ko_title": "BabyMonster, 'SHEESH' 뮤직비디오 4억 뷰 돌파",
  "artist_tags": ["BabyMonster"],
  "keywords": ["SHEESH", "뮤직비디오", "4억", "뷰", "기록"]
}
"""

FEWSHOT_REFINE_BLOCK += r"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[FEW-SHOT 예시 D — artist_tags: 헤드라인 조각 vs 인명]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

입력 (문제 있는 부분 발췌):
{
  "ko_title": "송은이·김숙, 방송 중 안타까운 근황",
  "tts_text": "송은이와 김숙이 최근 방송에서 얼굴에 상처가 난 채 등장해 시청자들의 관심을 받았습니다.",
  "artist_tags": ["얼굴 상처"],
  "keywords": ["방송", "근황", "화제", "예능", "논란"]
}

출력 (교정 결과 — 이 형태로 출력하라):
{
  "ko_title": "송은이·김숙, 방송 중 안타까운 근황",
  "tts_text": "송은이와 김숙이 최근 방송에서 얼굴에 상처가 난 채 등장해 시청자들의 관심을 받았습니다.",
  "artist_tags": ["송은이", "김숙"],
  "keywords": ["방송", "근황", "화제", "예능", "논란"]
}
"""
