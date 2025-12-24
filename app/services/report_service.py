import json
from typing import Optional

from app.db.repositories.ReportRepository import report_repo
from app.schemas.report import ReportItem



def get_today_date_kst() -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")

class ReportService:
    def __init__(self):
        self.repo = report_repo

    async def get_aggregated_reports(self, symbols: list[str], invest_type: Optional[str], date: Optional[str] = None) -> list[ReportItem]:
        #타겟 날짜 선정: 스프링에서는 date가 요청 인자로 오지 않는다(추후 확장 가능성을 위해 date 함수 인자로 받음)
        target_date = date
        if not target_date:
            target_date = get_today_date_kst()
        if not invest_type:
            invest_type = "investor"  # 기본값 설정

        # fetched_map = {'AAPL': {...}, 'GOOG': {...}}
        fetched_map = await self.repo.get_report_batch(symbols, target_date, invest_type)

        result_items = []

        # 조합하기
        for sym in symbols:
            if sym in fetched_map:
                # 데이터가 있는 경우
                db_item = fetched_map[sym]
                result_items.append(ReportItem(
                    symbol=sym,
                    status="COMPLETED",
                    content= db_item.get('report_html'),
                    meta={
                        "created_at": db_item.get('created_at')
                    }
                ))
            else:
                # 데이터가 없는 경우 (비즈니스 판단: PENDING 처리)
                result_items.append(ReportItem(
                    symbol=sym,
                    status="PENDING",
                    content=None,
                    meta={"message": "생성 요청이 필요합니다."}
                ))

        return result_items

# 싱글톤 인스턴스
report_service = ReportService()