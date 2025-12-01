import asyncio
import httpx
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from app.db.StockNews import StockNews
from app.jobs.stock_news.extractor.crawler.CrawlerFactory import CrawlerFactory
from app.jobs.stock_news.collector.FinnhubNewsCollector import FinnhubNewsCollector
from app.jobs.stock_news.services.news_service import NewsService
from .worker import NewsBatchWorker
from ..analyzer.QuickNewsAnalyzer import QuickNewsAnalyzer


# Analyzer 클래스 임포트 (작성하신 파일 경로에 맞게 수정)
# from app.jobs.stock_news.analyzer import QuickNewsAnalyzer

class PipelineManager:
    def __init__(self, analyzer: QuickNewsAnalyzer):
        self.queue = asyncio.Queue()
        self.client = None
        self.workers = []
        self.analyzer = analyzer

    async def start(self, worker_count=3):
        """파이프라인 가동 (HTTP Client 생성 & 워커 실행)"""
        # 1. 커넥션 풀 생성
        self.client = httpx.AsyncClient(timeout=10.0)

        # 2. 크롤러 팩토리 생성 (client 공유)
        crawler_factory = CrawlerFactory(self.client)

        news_service = NewsService(
            crawler_factory=crawler_factory,
            analyzer=self.analyzer
        )

        # 3. 워커 생성 및 배치
        for i in range(worker_count):
            worker = NewsBatchWorker(
                news_service=news_service,
                queue=self.queue,
                batch_size = 10,  # 테스트용으로 작게 설정해봄직 함
                batch_timeout = 3.0
            )
            # 워커를 백그라운드 태스크로 실행
            task = asyncio.create_task(worker.run(worker_id=i + 1))
            self.workers.append(task)

        print("🚀 파이프라인 가동 완료 (워커 3기)")

    async def stop(self):
        """시스템 종료 처리"""
        if self.client:
            await self.client.aclose()
        for task in self.workers:
            task.cancel()
        print("🛑 파이프라인 종료")

    async def ingest_news(self, symbol: str, start_date: str, end_date: str):
        collector = FinnhubNewsCollector(self.client)

        print(f"📥 뉴스 수집 시작: {symbol}...")
        raw_news_list = await collector.fetch_stock_news(symbol, start_date, end_date)

        count = 0
        for raw_data in raw_news_list:
            try:
                # 딕셔너리 -> DTO 변환
                news_item = StockNews(
                    id=raw_data['id'],
                    symbol=symbol,  # Finnhub는 symbol을 안 줄 때가 있어서 직접 주입
                    headline=raw_data['headline'],
                    datetime=raw_data['datetime'],
                    url=raw_data['url'],
                    image=raw_data['image'],
                    source=raw_data['source'],
                    summary=raw_data['summary']
                )

                # 큐에 투입
                self.queue.put_nowait(news_item)
                count += 1
            except Exception as e:
                print(f"⚠️ 데이터 변환 실패: {e}")

        print(f"✅ 큐 적재 완료: {count}건")

    # 다중 종목 수집 메서드
    async def ingest_all_stocks_news(self, symbols: list[str], start_date: str, end_date: str):
        """
        여러 종목 리스트를 받아서 순차적으로 수집을 요청합니다.
        """
        print(f"🚀 총 {len(symbols)}개 종목 수집을 시작합니다.")

        for symbol in symbols:
            # 1. 기존 ingest_news 재활용
            await self.ingest_news(symbol, start_date, end_date)

            # 2. [Rate Limit 방어] Finnhub 분당 60회 제한 고려
            # 너무 빨리 요청하면 429 에러 뜨니까, 종목 사이에 숨 고르기
            await asyncio.sleep(1.0)

        print("🎉 모든 종목의 수집 요청이 큐에 등록되었습니다.")


# 테스트용 메인 함수
async def main():
    manager = PipelineManager()

    try:
        # 2. 파이프라인 가동 (워커들이 대기 상태로 들어감)
        await manager.start(worker_count=3)

        # 3. 뉴스 투입 (애플 뉴스 가져오기)
        # 이 함수가 실행되면 큐에 데이터가 쌓이고, 워커들이 즉시 처리를 시작함
        await manager.ingest_news("MSFT", "2025-11-25", "2025-11-26")

        # 4. 큐가 빌 때까지 대기 (모든 처리가 끝날 때까지 Main 유지)
        await manager.queue.join()

        print("🎉 모든 작업이 완료되었습니다!")

    finally:
        # 5. 정리 (Client 닫기 등)
        await manager.stop()


if __name__ == "__main__":
    asyncio.run(main())