from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timedelta

class NewsCollectRequest(BaseModel):
    symbol: str = Field(..., description="수집할 주식 심볼 (예: AAPL)")
    start_date: Optional[str] = Field(
        default=None,
        description="시작 날짜 (YYYY-MM-DD). 없으면 오늘 날짜"
    )
    end_date: Optional[str] = Field(
        default=None,
        description="종료 날짜 (YYYY-MM-DD). 없으면 오늘 날짜"
    )

class ManySymbolNewsCollectRequest(BaseModel):
    symbols: list= Field(..., description="수집할 주식 심볼 리스트 (예: [AAPL, MSFT])")
    start_date: Optional[str] = Field(
        default=None,
        description="시작 날짜 (YYYY-MM-DD). 없으면 오늘 날짜"
    )
    end_date: Optional[str] = Field(
        default=None,
        description="종료 날짜 (YYYY-MM-DD). 없으면 오늘 날짜"
    )