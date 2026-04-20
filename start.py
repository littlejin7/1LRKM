"""
start.py — 전체 파이프라인 실행 (진입점)

실행 순서:
  1단계: 뉴스 크롤링 (RSS + Tavily) → raw_news
  2단계: LLM 가공 (이 과정에서 최신/과거 뉴스 자동 분류) → processed_news / past_news
  3단계: 이미지 수집 → thumbnail_url
"""

from dotenv import load_dotenv
from database import get_session

import crawler1
import processor

load_dotenv()


def main():
    print("🚀 [K-엔터 뉴스 전체 파이프라인 시작]")

    # 1단계: 뉴스 크롤링 → raw_news
    # crawler1.py의 crawl_and_save는 자체적으로 세션을 열고 실행됩니다.
    print("\n[1단계: 크롤링]")
    crawler1.crawl_and_save()

    with get_session() as session:
        # 2단계: LLM 가공 → processed_news & past_news 분기 저장
        print("\n[2단계: LLM 가공]")
        # 미처리 뉴스들을 가공 (필요시 batch_size 조절 가능)
        processed = processor.process_and_save(session, batch_size=50)
        
        # 3단계: 이미지 수집
        print("\n[3단계: 이미지 수집]")
        processor.fetch_images_for_processed(session, headless=True)

    print("\n✅ [파이프라인 전체 실행 완료]")


if __name__ == "__main__":
    main()
