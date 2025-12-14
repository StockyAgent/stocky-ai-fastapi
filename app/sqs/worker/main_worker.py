import asyncio
import logging

from app.sqs.worker.retrieval_worker import RetrievalWorker

# 로그 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)


async def main():
    # 워커 인스턴스 생성
    worker = RetrievalWorker()

    # 워커 실행 (무한 루프)
    await worker.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 워커를 종료합니다.")