from pydantic import BaseModel, Field, ConfigDict
from typing import Optional


# ==========================================
# Request Schemas (API 요청용 DTO)
# ==========================================
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

# ==========================================
# Data Models (DB 저장/조회용 틀)
# ==========================================
class StockNews(BaseModel):
    # Pydantic V2 설정
    model_config = ConfigDict(populate_by_name=True)

    # --- [1. Finnhub 원본 데이터] ---
    id: int = Field(..., description="Finnhub 뉴스 고유 ID (중복 체크용)")
    symbol: str = Field(..., description="관련 주식 심볼 (예: AAPL)")
    datetime: int = Field(..., description="뉴스 발행 시각 (Unix Timestamp)")
    headline: str = Field(..., description="뉴스 헤드라인")
    summary: Optional[str] = Field(default="", description="뉴스 요약")
    url: Optional[str] = Field(default="", description="뉴스 원문 링크")
    source: Optional[str] = Field(default="", description="뉴스 출처 (Yahoo, CNBC 등)")
    category: Optional[str] = Field(default="general", description="뉴스 카테고리")
    image: Optional[str] = Field(default="", description="뉴스 이미지 URL")

    # content는 Finnhub 무료 버전에서는 거의 안 주므로 빼거나 Optional로 둡니다.
    content: Optional[str] = Field(default=None, description="뉴스 본문 (있을 경우)")

    # --- [2. AI 분석 데이터 (나중에 채워질 부분)] ---
    sentiment: Optional[str] = Field(default=None, description="AI 감성 분석 (POSITIVE/NEGATIVE)")
    impact_score: Optional[int] = Field(default=None, description="중요도 점수 (0~100)")
    ai_summary: Optional[str] = Field(default=None, description="AI 한줄 요약")
