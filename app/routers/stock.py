from fastapi import APIRouter, BackgroundTasks, status
from app.jobs.stock_information.collector.FinnhubStockCollector import FinnhubStockCollector
from app.jobs.stock_information.service.StockCollectionService import StockCollectionService
from app.services.http_client import get_http_client

router = APIRouter()


# 1. 백그라운드에서 실행될 독립적인 작업 함수
# (이 함수는 요청/응답 주기와 상관없이 끝까지 실행됩니다.)
async def task_logic():
    print("🕒 백그라운드 작업 시작: 주식 정보 수집")

    # 중요: 백그라운드 작업 전용으로 새로운 HTTP 세션을 엽니다.
    async with get_http_client() as client:
        # Collector와 Service 조립
        collector = FinnhubStockCollector(client=client)
        stock_collection_service = StockCollectionService(collector=collector)

        # 실제 수집 로직 실행 (시간이 오래 걸려도 됨)
        # (주의: 이전 대화에서 함수명을 update_all_stock_profiles로 바꿨다면 그걸로 호출하세요)
        await stock_collection_service.update_stock_profiles()

    print("✅ 백그라운드 작업 종료")


# 2. API 엔드포인트
@router.post("/sync/stock-info", status_code=status.HTTP_202_ACCEPTED)
async def start_stock_sync(background_tasks: BackgroundTasks):
    """
    주식 정보 수집을 백그라운드에서 시작합니다.
    서버는 즉시 'Accepted(202)' 응답을 반환하고, 작업은 뒤에서 계속됩니다.
    """
    # 3. 작업 큐에 함수 등록
    # 주의: task_logic() 처럼 호출하는 게 아니라, 함수 이름만 넘겨줍니다.
    background_tasks.add_task(task_logic)

    return {
        "status": "accepted",
        "message": "주식 정보 수집 요청이 접수되었습니다. 백그라운드에서 실행됩니다."
    }