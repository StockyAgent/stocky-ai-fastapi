from typing import List, Literal
import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.services.report_service import report_service
from app.db.repositories.ReportRepository import report_repo
from app.schemas.report import ReportRequest, ManySymbolReportRequest, ReportRetrievalResponse, ReportRetrievalRequest
from app.jobs.Daily_report_agent.nodes.nodes import write_report

# [중요] 방금 작성하신 write_report 함수를 임포트해야 합니다.
# 파일 위치에 따라 경로를 맞춰주세요.

router = APIRouter()


# 2. 엔드포인트 정의
@router.post("/generate/daily_report", response_class=HTMLResponse)
async def generate_daily_report(request: ReportRequest):
    """
    특정 종목의 데일리 리포트를 생성하고 HTML로 반환합니다.
    """
    print(f"📥 API 요청 수신: {request.symbol}({request.investment_type}) 리포트 생성")

    try:
        # LangGraph 워크플로우 실행
        # write_report 함수는 비동기(async)여야 합니다.
        html_content = await write_report(request.symbol, request.investment_type)

        if not html_content:
            raise HTTPException(status_code=500, detail="리포트 생성에 실패했습니다 (데이터 부족 또는 에러).")

        await report_repo.save_report(
            symbol=request.symbol,
            html=html_content,
            invest_type=request.investment_type,
            category="DAILY"
        )

        # HTMLResponse를 쓰면 브라우저가 태그를 해석해서 예쁜 화면을 보여줍니다.
        return HTMLResponse(content=html_content)

    except Exception as e:
        print(f"❌ API 에러 발생: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ManySymbolsReportResponse(BaseModel):
    results: List[str] = Field(description="생성된 HTML 리포트 리스트")


# TODO: 다중 심볼 리포트 생성 엔드포인트 --> html 리스트 반환 방향에 대해 수정 고려 필요
@router.post("/generate/daily_reports")
async def generate_daily_reports(request: ManySymbolReportRequest):
    try:
        symbols = request.symbols
        if not symbols:
            return ManySymbolsReportResponse(results=[])
        tasks = [write_report(symbol) for symbol in symbols]
        results = await asyncio.gather(*tasks)

        valid_htmls = [html for html in results if html is not None]

        return ManySymbolsReportResponse(results=valid_htmls)
    except Exception as e:
        print(f"❌ API 에러 발생: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reports/batch_lookup", response_model=ReportRetrievalResponse)
async def fetch_reports(request: ReportRetrievalRequest):
    results = await report_service.get_aggregated_reports(
        symbols=request.symbols,
        invest_type="trader"  #request.investment_type TODO: 수정 필요
    )

    return ReportRetrievalResponse(
        request_id=request.request_id,
        user_id=request.user_id,
        results=results
    )