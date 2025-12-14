from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from datetime import datetime, timedelta

from app.schemas.stockNews import NewsCollectRequest, ManySymbolNewsCollectRequest
router = APIRouter()


@router.post("/collect", summary="뉴스 수집 및 분석 파이프라인 트리거")
async def trigger_news_collection(
        request: Request,
        body: NewsCollectRequest,
        background_tasks: BackgroundTasks
):
    """
    특정 심볼에 대한 뉴스 수집 -> 분석 -> 저장 파이프라인을 실행합니다.
    작업은 백그라운드에서 비동기로 처리됩니다.
    """
    # 1. 날짜 기본값 처리 (입력 없으면 오늘)
    today = datetime.now()
    if today.weekday() == 0: # 월요일
        days_to_fetch = 3
    elif today.weekday() == 6: # 일요일
        days_to_fetch = 2
    else:
        days_to_fetch = 1

    start_date = body.start_date if body.start_date else (today - timedelta(days=days_to_fetch)).strftime("%Y-%m-%d")
    end_date = body.end_date if body.end_date else today.strftime("%Y-%m-%d")

    print("start:", start_date, "end:", end_date)

    # 2. 앱 상태(state)에 저장된 파이프라인 매니저 가져오기
    # (main.py에서 lifespan으로 등록할 예정)
    pipeline_manager = request.app.state.pipeline_manager

    if not pipeline_manager:
        raise HTTPException(status_code=500, detail="파이프라인 매니저가 초기화되지 않았습니다.")

    # 3. 백그라운드 작업 등록 (Fire and Forget)
    # 사용자는 기다리지 않고 바로 응답을 받습니다.
    background_tasks.add_task(
        pipeline_manager.ingest_news,
        symbol=body.symbol,
        start_date=start_date,
        end_date=end_date
    )

    return {
        "status": "accepted",
        "message": f"'{body.symbol}' 뉴스 수집 요청이 백그라운드 작업으로 등록되었습니다.",
        "period": f"{start_date} ~ {end_date}"
    }


@router.post("/collect-stocks", summary="뉴스 수집 및 분석 파이프라인 트리거")
async def trigger_news_collection(
        request: Request,
        body: ManySymbolNewsCollectRequest,
        background_tasks: BackgroundTasks
):
    """
    특정 심볼에 대한 뉴스 수집 -> 분석 -> 저장 파이프라인을 실행합니다.
    작업은 백그라운드에서 비동기로 처리됩니다.
    """
    # 1. 날짜 기본값 처리 (입력 없으면 오늘)
    today = datetime.now()
    start_date = body.start_date if body.start_date else (today - timedelta(days=1)).strftime("%Y-%m-%d")
    end_date = body.end_date if body.end_date else today.strftime("%Y-%m-%d")

    print("start:", start_date, "end:", end_date)

    # 2. 앱 상태(state)에 저장된 파이프라인 매니저 가져오기
    # (main.py에서 lifespan으로 등록할 예정)
    pipeline_manager = request.app.state.pipeline_manager

    if not pipeline_manager:
        raise HTTPException(status_code=500, detail="파이프라인 매니저가 초기화되지 않았습니다.")

    # 3. 백그라운드 작업 등록 (Fire and Forget)
    # 사용자는 기다리지 않고 바로 응답을 받습니다.
    background_tasks.add_task(
        pipeline_manager.ingest_all_stocks_news,
        symbols=body.symbols,
        start_date=start_date,
        end_date=end_date
    )

    return {
        "status": "accepted",
        "message": f"'{body.symbols}' 뉴스 수집 요청이 백그라운드 작업으로 등록되었습니다.",
        "period": f"{start_date} ~ {end_date}"
    }