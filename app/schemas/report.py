# Data Models (DB 저장/조회용 틀)
from typing import Literal, Optional, Dict, Any, List

from pydantic import BaseModel, Field


# ==========================================
# 공통으로 쓰이는 Schemas (Nested Item)
# ==========================================
class ReportItem(BaseModel):
    """
    개별 리포트 상태 및 내용
    """
    symbol: str = Field(..., description="종목 코드")
    status: Literal["COMPLETED", "PENDING", "FAILED"] = Field(..., description="상태")
    content: Optional[str] = Field(None, description="HTML 본문 (완료 시에만 존재)")
    meta: Optional[Dict[str, Any]] = Field(default_factory=dict, description="추가 정보(점수, 날짜 등)")

# ==========================================
# Request Schemas (API 요청용 DTO)
# ==========================================
class ReportRequest(BaseModel):
    symbol: str
    investment_type: Literal["trader", "investor"]

class ManySymbolReportRequest(BaseModel):
    symbols: list[str]

class ReportRetrievalRequest(BaseModel): #(조회용) Spring Boot -> FastAPI 조회 요청
    # request_id: str = Field(..., description="요청 추적 ID (UUID)") # user_id로 구분할 예정
    user_id: str
    symbols: List[str]
    investment_type: str

# ==========================================
# Response Schemas (API 요청용 DTO)
# ==========================================

class ReportRetrievalResponse(BaseModel):
    """(조회용) 최종 반환될 큰 박스"""
    # request_id: str  # 요청받았던 ID를 그대로 돌려줌 (확인용)
    user_id: str
    reports: List[ReportItem] #ReportItem들이 담기는 용도

# ==========================================
# Data Models (DB 저장/조회용 틀)
# ==========================================