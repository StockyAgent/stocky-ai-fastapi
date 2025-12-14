import logging

from dotenv import load_dotenv
from fastapi import FastAPI

from app.jobs.stock_news.analyzer.QuickNewsAnalyzer import QuickNewsAnalyzer
from app.jobs.stock_news.pipeline.manager import PipelineManager
from app.routers import stock, stock_news, report

from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware


# [Lifespan] 앱 켜질 때 워커 출근 -> 꺼질 때 워커 퇴근 관리
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작: 파이프라인 매니저 생성 및 워커 가동
    print("🏭 시스템 가동: 파이프라인 매니저 초기화 중...")

    load_dotenv()
    from langchain_openai import ChatOpenAI
    chat_model = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    analyzer = QuickNewsAnalyzer(chat_model)

    manager = PipelineManager(analyzer = analyzer)
    await manager.start(worker_count=3)

    # 앱 전체에서 쓸 수 있게 state에 저장
    app.state.pipeline_manager = manager

    yield  # 앱 실행 중...

    # 종료: 워커 퇴근 및 정리
    print("🛑 시스템 종료: 파이프라인 정리 중...")
    await manager.stop()


app = FastAPI(lifespan=lifespan, title="AI Stock Analyst Agent", root_path="/ai")
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)


# 라우터 등록
app.include_router(stock_news.router, prefix="/api/news", tags=["News"])
app.include_router(stock.router, prefix="/api/stock", tags=["Stock"])
app.include_router(report.router, prefix="/api/report", tags=["Report"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)