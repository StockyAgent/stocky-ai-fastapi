from fastapi import FastAPI

from app.jobs.stock_news.pipeline.manager import PipelineManager
from app.routers import stock, stock_news

from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn


# [Lifespan] 앱 켜질 때 워커 출근 -> 꺼질 때 워커 퇴근 관리
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. 시작(Startup): 파이프라인 매니저 생성 및 워커 가동
    print("🏭 시스템 가동: 파이프라인 매니저 초기화 중...")
    manager = PipelineManager()
    await manager.start(worker_count=3)  # 워커 3명 출근

    # 앱 전체에서 쓸 수 있게 state에 저장
    app.state.pipeline_manager = manager

    yield  # 앱 실행 중...

    # 2. 종료(Shutdown): 워커 퇴근 및 정리
    print("🛑 시스템 종료: 파이프라인 정리 중...")
    await manager.stop()


app = FastAPI(lifespan=lifespan, title="AI Stock Analyst Agent")

# 라우터 등록
app.include_router(stock_news.router, prefix="/api/news", tags=["News"])
app.include_router(stock.router, prefix="/api/stock", tags=["Stock"])

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)