import time
import asyncio
import logging
from app.db.StockNews import StockNews
from app.services.aws_service import put_item_dynamodb, put_items_batch_dynamodb

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

    def _is_valid_for_analysis(self, content: str) -> bool:
        """AI 분석을 수행하기에 충분한 데이터인지 판단"""
        if not content:
            return False
        if len(content.strip()) < 50:  # 공백 제거 후 길이 체크 등 디테일 추가 가능
            return False
        return True


    async def _process_item(self, item: StockNews):
        # A. 크롤링 (Crawling)
        # 팩토리에서 소스에 맞는 크롤러를 가져옴
        crawler = self.crawler_factory.get_crawler(item.source)

        # content가 이미 있으면 스킵, 없으면 크롤링
        if not item.content:
            # fetch 메소드는 url만 받도록 되어 있으므로 호출
            item.content = await crawler.fetch(item.url)

        # 본문이 너무 짧으면 분석 스킵
        if not self._is_valid_for_analysis(item.content):
            logger.warning(f"⚠️ 분석 부적합(내용 부족): {item.url}")
            return

        # B. AI 분석 (Analysis)
        # QuickNewsAnalyzer.analyze 메소드 호출
        # 단건 분석 방식으로 진행
        analysis_result = self.analyzer.analyze(item.content, item.symbol)

        # 결과 매핑
        item.sentiment = analysis_result.sentiment
        item.impact_score = analysis_result.importance
        item.ai_summary = analysis_result.summary

        # C. 저장 (Save)
        await put_item_dynamodb(table_name=self.table_name ,item = item.to_dynamodb_item())


class NewsBatchWorker:
    # 배치에 쌓인 일들을 처리하는 워커
    def __init__(self, crawler_factory, analyzer, queue, batch_size=10, batch_timeout=5.0):
        self.crawler_factory = crawler_factory
        self.analyzer = analyzer
        self.queue = queue
        self.table_name = "StockProjectData"
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.semaphore = asyncio.Semaphore(3)

    def _is_valid_for_analysis(self, content: str) -> bool:
        """AI 분석을 수행하기에 충분한 데이터인지 판단"""
        if not content:
            return False
        if len(content.strip()) < 50:  # 공백 제거 후 길이 체크 등 디테일 추가 가능
            return False
        return True

    async def run(self, worker_id: int = 0):
        logger.info(f"🚜 배치 워커 {worker_id}번 가동 시작")
        logger.info("NewsBatchWorker Started")
        buffer = []
        last_flush_time = time.time()  # 마지막 처리 시간 기록

        while True:
            try:
                # 큐에서 가져오기 (타임아웃 설정)
                # 1초 동안 기다려보고 없으면 asyncio.TimeoutError 발생
                item = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                buffer.append(item)

            except asyncio.TimeoutError:
                pass  # 타임아웃 나면 현재 버퍼라도 처리하러 감

            # 시간 체크
            current_time = time.time()
            time_since_flush = current_time - last_flush_time

            # 버퍼가 꽉 찼거나, (데이터가 있는데) 시간이 지났다면 처리
            if len(buffer) >= self.batch_size or (buffer and time_since_flush >= self.batch_timeout):

                processed_count = len(buffer)

                try:
                    await self._process_batch(buffer)
                except Exception as e:
                    import traceback
                    logger.error(f"Batch Critical Error: {e}")
                    logger.error(traceback.format_exc())  # 어디서 에러 났는지 줄번호 확인
                finally:
                    for _ in range(processed_count):
                        self.queue.task_done()


                buffer = []  # 버퍼 초기화
                last_flush_time = current_time

    async def _fetch_and_assign(self, item: StockNews):
        # 개별 아이템에 대해 크롤링 수행-->이를 _process_batch에서 병령적으로 수행
        async with self.semaphore:
            try:
                crawler = self.crawler_factory.get_crawler(item.source)
                # 가져와서 바로 자기 자신(item)에 집어넣음
                content = await crawler.fetch(item.url)
                item.content = content
            except Exception as e:
                # 에러가 나도 여기서 처리하고, item에는 None이나 빈 값을 둠
                logger.warning(f"Crawling failed for {item.url}: {e}")
                item.content = None


    async def _process_batch(self, items: list[StockNews]):

        # 크롤링
        tasks = [
            self._fetch_and_assign(item)
            for item in items
            if not item.content
        ]

        if tasks:
            # 다 끝날 때까지 기다림 (결과를 리턴받을 필요 없음! 이미 item이 수정됨)
            await asyncio.gather(*tasks)


        # 리스트 컴프리헨션으로 유효한 것만 재할당
        items[:] = [item for item in items if self._is_valid_for_analysis(item.content)]

        if not items:
            logger.info("⚠️ 배치 내 유효한 뉴스가 없어 스킵합니다.")
            return

        #ai 분석
        analysis_results = self.analyzer.analyze_batch(
            items
        )

        #매핑
        for item, analysis in zip(items, analysis_results):
            item.sentiment = analysis['sentiment']
            item.impact_score = analysis['importance']
            item.ai_summary = analysis['summary']


        #저장
        await put_items_batch_dynamodb(table_name=self.table_name, items=[item.to_dynamodb_item() for item in items])