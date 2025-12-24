import json
import logging
from app.schemas.report import ReportRetrievalRequest, ReportRetrievalResponse
from app.services.report_service import report_service
from app.sqs.service.sqs_service import sqs_service
from app.sqs.worker.base_worker import BaseSQSWorker
from app.core.settings import settings

logger = logging.getLogger("RetrievalWorker")


class RetrievalWorker(BaseSQSWorker):
    def __init__(self):
        # 부모에게 "나는 Request Queue를 감시할래"라고 전달
        super().__init__(queue_url=settings.SQS_REQUEST_QUEUE_URL)

    async def process_message(self, message_body: str) -> bool:
        from pydantic import ValidationError
        try:
            #  JSON 파싱
            data = json.loads(message_body)
            request = ReportRetrievalRequest(**data)

            logger.info(f"🔍 [조회 시작] User: {request.userId}, 종목: {request.symbols}")

            # DB 조회 (Service 호출)
            reports = await report_service.get_aggregated_reports(
                symbols=request.symbols,
                invest_type=request.investment_type
            )

            # 응답 포맷팅
            response = ReportRetrievalResponse(
                userId=request.userId,
                reports=reports
            )

            # 결과 발송 (SQSService 사용)
            await sqs_service.send_response(response.model_dump())

            return True  # 성공!

        except ValidationError as e:
            # 유효성 검사 실패시 True 반환으로 재시도 불가 처리
            logger.error(f"🗑️ [데이터 폐기] 유효성 검사 실패 (재시도 불가): {e}")
            return True


        except Exception as e:
            logger.error(f"❌ [처리 실패] 데이터: {message_body[:50]}... / 원인: {e}")
            return False  # 실패! (메시지 삭제 안 함 -> 재시도 됨)