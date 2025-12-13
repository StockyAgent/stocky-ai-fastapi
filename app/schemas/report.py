from typing import Literal

from pydantic import BaseModel

# ==========================================
# Request Schemas (API 요청용 DTO)
# ==========================================
class ReportRequest(BaseModel):
    symbol: str
    investment_type: Literal["trader", "investor"]

class ManySymbolReportRequest(BaseModel):
    symbols: list[str]

# ==========================================
# Data Models (DB 저장/조회용 틀)
# ==========================================

