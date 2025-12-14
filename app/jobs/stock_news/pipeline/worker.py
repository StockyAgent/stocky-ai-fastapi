import time
import asyncio
import logging
from app.db.repositories.StockNewsRepository import news_repo
from app.schemas.stockNews import StockNews
from app.db.StockNews import StockNews
from app.jobs.stock_news.services.news_service import NewsService

from app.db.repositories.StockNewsRepository import news_repo
from app.schemas.stockNews import StockNews

logger = logging.getLogger("NewsWorker")

class NewsBatchWorker:
    def __init__(self, news_service: NewsService, queue: asyncio.Queue, batch_size: int = 10, batch_timeout: float = 3.0):
        self.news_service = news_service
        self.queue = queue
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout

    async def run(self, worker_id: int = 1):
        logger.info(f"🚜 배치 워커 {worker_id}번 가동 시작")

        buffer: list[StockNews] = []
        last_flush_time = time.time()

        while True:
            try:
                # 큐에서 데이터 가져오기 (Timeout 설정)
                try:
                    item = await asyncio.wait_for(self.queue.get(), timeout=1.0)# 1초 동안 기다려보고 없으면 TimeoutError 발생 -> flush 체크로 넘어감
                    buffer.append(item)
                except asyncio.TimeoutError:
                    pass  # 큐가 비어있으면 그냥 넘어감 (시간 체크하러)

                # 처리 조건 확인 (버퍼 꽉 참 OR 시간 초과)
                current_time = time.time()
                time_since_flush = current_time - last_flush_time

                is_batch_full = len(buffer) >= self.batch_size
                is_timeout = (len(buffer) > 0) and (time_since_flush >= self.batch_timeout)

                if is_batch_full or is_timeout:
                    # 처리할 아이템 개수 기억 (task_done을 위해)
                    processed_count = len(buffer)

                    try:
                        await self.news_service.process_news_list(buffer)

                    except Exception as e:
                        logger.error(f"❌ 워커 {worker_id} 배치 처리 중 치명적 오류: {e}")

                    finally:
                        for _ in range(processed_count):
                            self.queue.task_done() # 성공하든 실패하든 큐에 '완료' 신호를 보내야 queue.join()이 안 멈추고 끝남

                    # 버퍼 및 시간 초기화
                    buffer = []
                    last_flush_time = current_time

            except Exception as e:
                # 큐 관련 치명적 에러 방지용 안전장치
                logger.error(f"💀 워커 루프 에러: {e}")
                await asyncio.sleep(1)  # 무한 에러 루프 방지용 대기