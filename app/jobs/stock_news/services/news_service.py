import logging
import asyncio
from typing import List


from app.db.repositories.StockNewsRepository import NewsRepository
from app.schemas.stockNews import StockNews

logger = logging.getLogger("NewsService")

class NewsService:
    def __init__(self, crawler_factory, analyzer, news_repo: NewsRepository, concurrency_limit: int = 5):
        self.crawler_factory = crawler_factory
        self.analyzer = analyzer
        self.news_repo = news_repo  # Repository 주입
        self.semaphore = asyncio.Semaphore(concurrency_limit)

    async def process_news_list(self, items: List[StockNews]) -> List[StockNews]:
        if not items:
            return []

        # 1. 크롤링 (병렬 처리)
        crawl_tasks = [self._fetch_content_safe(item) for item in items if not item.content]
        if crawl_tasks:
            await asyncio.gather(*crawl_tasks)

        # 2. 유효성 검사
        valid_items = [item for item in items if self._is_valid(item.content)]


        if not valid_items:
            logger.info(f"⚠️ 처리할 유효한 뉴스가 없습니다. (요청: {len(items)}건)")
            return []


        # 3. AI 분석
        logger.info(f"🧠 AI 분석 시작: {len(valid_items)}건")
        try:
            analysis_results = self.analyzer.analyze_batch(valid_items)

      
            for item, analysis in zip(valid_items, analysis_results):
                item.sentiment = analysis.get('sentiment', 'neutral')
                item.impact_score = analysis.get('importance', 0)
                item.ai_summary = analysis.get('summary', '')

        except Exception as e:
            logger.error(f"❌ AI 분석 단계 에러: {e}")
            return []

        # 4. DB 저장 (Repository 사용)
        try:
            # Service는 DynamoDB JSON 변환을 몰라도 됨. 객체 그대로 전달.
            await self.news_repo.save_news_batch(valid_items)
            logger.info(f"💾 DB 저장 완료: {len(valid_items)}건")
        except Exception as e:
            logger.error(f"❌ 저장 실패: {e}")

        return valid_items



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
        return bool(content and len(content.strip()) >= 50)

