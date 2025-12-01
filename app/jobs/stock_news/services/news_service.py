import logging
import asyncio
from typing import List
from app.db.StockNews import StockNews
from app.services.aws_service import put_items_batch_dynamodb

logger = logging.getLogger("NewsService")


class NewsService:
    def __init__(self, crawler_factory, analyzer, concurrency_limit: int = 5):
        self.crawler_factory = crawler_factory
        self.analyzer = analyzer
        self.table_name = "StockProjectData"
        self.semaphore = asyncio.Semaphore(concurrency_limit) # 동시 요청 수 자동 제어

    async def process_news_list(self, items: List[StockNews]) -> List[StockNews]:

        if not items:
            return []

        # 크롤링: 내용이 없는 아이템만 골라서 크롤링 태스크 생성
        crawl_tasks = [self._fetch_content_safe(item) for item in items if not item.content]

        if crawl_tasks:
            # 병렬 실행 (내부에서 semaphore로 속도 조절됨)
            await asyncio.gather(*crawl_tasks)

        # 유효성 검사 :크롤링 실패했거나 내용이 너무 짧은 것 제거
        valid_items = [item for item in items if self._is_valid(item.content)]

        if not valid_items:
            logger.info(f"⚠️ 처리할 유효한 뉴스가 없습니다. (요청: {len(items)}건)")
            return []

        # AI 분석 (Analysis)
        logger.info(f"🧠 AI 분석 시작: {len(valid_items)}건")
        try:
            # analyzer.analyze_batch는 리스트 순서대로 결과를 반환한다고 가정
            analysis_results = self.analyzer.analyze_batch(valid_items)

            # 결과 매핑
            for item, analysis in zip(valid_items, analysis_results):
                item.sentiment = analysis.get('sentiment', 'neutral')
                item.impact_score = analysis.get('importance', 0)
                item.ai_summary = analysis.get('summary', '')

        except Exception as e:
            logger.error(f"❌ AI 분석 단계 에러: {e}")
            # 분석 실패 시 여기서 중단하고 빈 리스트 반환 (DB 저장 X)
            return []

        # DB 저장
        try:
            # StockNews 객체를 DynamoDB JSON 포맷으로 변환
            items_to_save = [item.to_dynamodb_item() for item in valid_items]
            await put_items_batch_dynamodb(table_name=self.table_name, items=items_to_save)
            logger.info(f"💾 DB 저장 완료: {len(valid_items)}건")
        except Exception as e:
            logger.error(f"❌ DynamoDB 저장 실패: {e}")

        return valid_items # 무조건 반환: tool에서 후속 처리 가능하도록

    async def _fetch_content_safe(self, item: StockNews):
        async with self.semaphore:
            try:
                crawler = self.crawler_factory.get_crawler(item.source)

                content = await crawler.fetch(item.url)
                item.content = content

            except Exception as e:
                logger.warning(f"⚠️ 크롤링 실패 ({item.source}): {item.url} -> {e}")
                item.content = None

    def _is_valid(self, content: str) -> bool:
        if not content:
            return False
        if len(content.strip()) < 50:  # 50자 미만은 유의미한 정보가 아닐 확률 높음
            return False
        return True