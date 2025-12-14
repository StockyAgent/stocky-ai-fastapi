import logging

import aioboto3
from app.core.settings import settings
import json

logger = logging.getLogger("SQSService")

class SQSService:
    # SQSService는 응답 메시지를 SQS에 발송하는 역할을 담당합니다.
    def __init__(self):
        self.session = aioboto3.Session(
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY
        )
        #응답을 보낼 큐 URL (Response Queue)
        self.response_queue_url = settings.SQS_RESPONSE_QUEUE_URL

    async def send_response(self, response_data: dict):
        try:
            async with self.session.client("sqs") as sqs:
                await sqs.send_message(
                    QueueUrl=self.response_queue_url,
                    MessageBody=json.dumps(response_data, ensure_ascii=False)
                )
            logger.info(f"🚀 [SQS Send] 응답 발송 완료 (ReqID: {response_data.get('message_body')})")
        except Exception as e:
            logger.error(f"❌ [SQS Send Error] 발송 실패: {e}")
            # TODO: 발송 실패시 재시도 로직 추후 고려
sqs_service = SQSService()