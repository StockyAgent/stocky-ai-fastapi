import asyncio
import logging
from app.db.StockNews import StockNews
from app.services.aws_service import put_item_dynamodb

logger = logging.getLogger("NewsWorker")


class NewsWorker:
    def __init__(self, crawler_factory, analyzer, queue):
        """
        Dependency Injection (의존성 주입)
        워커는 구체적인 구현 내용을 몰라도 됨. 
        """
        self.crawler_factory = crawler_factory
        self.analyzer = analyzer
        self.queue = queue
        self.table_name = "StockProjectData"

    async def run(self, worker_id: int):
        logger.info(f"👷 워커 {worker_id}번 출근 완료")

        while True:
            # 1. 큐에서 데이터 꺼내기 (없으면 대기)

            item: StockNews = await self.queue.get()

            try:
                await self._process_item(item)
            except Exception as e:
                logger.error(f"❌ 워커 {worker_id} 에러 ({item.id}): {e}")
            finally:
                self.queue.task_done()

    async def _process_item(self, item: StockNews):
        # A. 크롤링 (Crawling)
        # 팩토리에서 소스에 맞는 크롤러를 가져옴
        crawler = self.crawler_factory.get_crawler(item.source)

        # content가 이미 있으면 스킵, 없으면 크롤링
        if not item.content:
            # fetch 메소드는 url만 받도록 되어 있으므로 호출
            item.content = await crawler.fetch(item.url)

        # 본문이 너무 짧으면 분석 스킵
        if not item.content or len(item.content) < 50:
            logger.warning(f"⚠️ 본문 부족으로 분석 스킵: {item.url}")
            return

        # B. AI 분석 (Analysis)
        # QuickNewsAnalyzer.analyze 메소드 호출
        # (analyze_batch 대신 큐 방식엔 단건 처리가 더 적합)
        analysis_result = self.analyzer.analyze(item.content, item.symbol)

        # 결과 매핑
        item.sentiment = analysis_result.get('sentiment')
        item.impact_score = analysis_result.get('importance', 0)
        item.ai_summary = analysis_result.get('summary')

        # C. 저장 (Save)
        await put_item_dynamodb(table_name=self.table_name ,item = item.to_dynamodb_item())