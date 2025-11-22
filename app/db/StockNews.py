from typing import Optional, Any

from pydantic import BaseModel, Field, ConfigDict


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

    # --- [3. DynamoDB 변환 메서드] ---
    def to_dynamodb_item(self) -> dict[str, Any]:
        """
        DynamoDB에 저장할 형태로 변환
        PK: STOCK#{symbol}
        SK: NEWS#{datetime} (최신순 정렬을 위해)
        """
        item = self.model_dump(exclude_none=True)  # None인 필드는 저장 안 함 (용량 절약)

        # PK/SK 생성 전략
        # PK: 종목별로 모으기 위해 STOCK#AAPL
        item['PK'] = f"STOCK#{self.symbol}"

        # SK: 시간순 정렬을 위해 NEWS#타임스탬프
        # (주의: 같은 시간에 뉴스가 2개일 수도 있으니 ID를 붙여 유니크하게 만듦)
        item['SK'] = f"NEWS#{self.datetime}#{self.id}"

        # GSI용 데이터 (옵션): 날짜별로 모아보고 싶다면
        # item['GSI1_PK'] = f"DATE#{datetime.fromtimestamp(self.datetime).date()}"
        # item['GSI1_SK'] = f"SCORE#{self.impact_score}"

        item['Type'] = "News"  # 아이템 구분용

        return item