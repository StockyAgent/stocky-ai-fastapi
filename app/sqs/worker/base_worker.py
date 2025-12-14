import logging
from abc import ABC, abstractmethod
from app.core.settings import settings
import aioboto3
import asyncio

logger = logging.getLogger("BaseWorker")

class BaseSQSWorker(ABC):
    def __init__(self, queue_url: str):
        self.queue_url = queue_url

        self.session = aioboto3.Session(
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )
        self.is_running = True

    @abstractmethod
    async def process_message(self, message_body: str) -> bool:
        """자식 클래스가 구현해야 할 실제 업무 로직"""
        pass

    async def run(self):
        logger.info(f"👷 워커 가동 시작! (Queue: {self.queue_url})")

        async with self.session.client("sqs") as sqs:
            while self.is_running:
                from botocore.exceptions import ClientError
                try:
                    # 1. 메시지 수신 (Long Polling 20초)
                    response = await sqs.receive_message(
                        QueueUrl=self.queue_url,
                        MaxNumberOfMessages=10,
                        WaitTimeSeconds=20
                    )

                    if 'Messages' in response:
                        logger.info(f"📨 메시지 {len(response['Messages'])}개 도착")

                        for msg in response['Messages']:
                            body = msg['Body']
                            receipt_handle = msg['ReceiptHandle']

                            # 2. 자식 클래스에게 업무 위임
                            success = await self.process_message(body)

                            # 3. 업무 성공 시 큐에서 메시지 삭제
                            if success:
                                await sqs.delete_message(
                                    QueueUrl=self.queue_url,
                                    ReceiptHandle=receipt_handle
                                )

                except ClientError as e:
                    logger.error(f"⚠️ AWS 통신 오류: {e}")
                    await asyncio.sleep(5)  # 오류 나면 잠깐 쉼
                except Exception as e:
                    logger.error(f"💥 알 수 없는 오류: {e}")
                    await asyncio.sleep(5)