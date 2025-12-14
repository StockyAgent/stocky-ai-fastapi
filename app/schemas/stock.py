from datetime import date
from decimal import Decimal
from typing import Optional, Union, Dict, Any
from pydantic import BaseModel, Field, ConfigDict





# ==========================================
# Data Models (DB 저장/조회용 틀)
# ==========================================
class StockProfile(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,  # v2에서는 이 이름 사용
        json_encoders={date: lambda v: v.isoformat()}
    )

    figi: str = Field(..., alias="_id")  # ERD의 _id를 figi로 매핑

    # /stock/symbol 에서 가져옴
    symbol: str

    #Finnhub /stock/profile2
    name: Optional[str] = None
    country: Optional[str] = None
    currency: Optional[str] = None
    exchange: Optional[str] = None
    finnhubIndustry: Optional[str] = None
    ipo: Optional[date] = None  # date | None
    logo: Optional[str] = None
    marketCapitalization: Optional[Decimal] = None  # float | None
    phone: Optional[str] = None
    shareOutstanding: Optional[Decimal] = None
    weburl: Optional[str] = None

    # 관리용
    last_updated_at: Optional[str] = None

    def to_dynamodb_item(self) -> Dict[str, Any]:
        """
        Pydantic 모델을 DynamoDB 호환 딕셔너리로 변환합니다.
        - date 타입은 ISO 형식 문자열로 변환
        - float는 Decimal로 변환
        - PK, SK 추가
        """
        item_data = self.model_dump(by_alias=False)

        # date 타입을 문자열로 변환
        if item_data.get('ipo') and isinstance(item_data['ipo'], date):
            item_data['ipo'] = item_data['ipo'].isoformat()

        # float를 Decimal로 변환
        for key in ['marketCapitalization', 'shareOutstanding']:
            if item_data.get(key) is not None:
                item_data[key] = Decimal(str(item_data[key]))

        # # PK, SK 추가 --> Repository에서 담당하므로 주석 처리: pk sk의 생성 책임은 Repository에 있음
        # item_data['PK'] = f"FIGI#{self.figi}"
        # item_data['SK'] = "METADATA"

        return item_data