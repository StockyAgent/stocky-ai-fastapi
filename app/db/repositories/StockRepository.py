from app.schemas.stock import StockProfile
from app.db.connection import get_dynamodb_table  # aws_service 대신 이거 import!
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger("StockRepo")


class StockRepository:
    def __init__(self):
        self.table_name = "StockProjectData"

    async def save_profile(self, profile: StockProfile) -> bool:
        """
        주식 프로필 정보를 저장합니다.
        """
        try:
            # Pydantic 모델 -> DynamoDB Item 변환
            item = profile.to_dynamodb_item()

            item['PK'] = f"STOCK#{profile.figi}"
            item['SK'] = "PROFILE"

            # [변경] put_item_dynamodb 대신 직접 context manager 사용
            async with get_dynamodb_table(self.table_name) as table:
                await table.put_item(Item=item)

            # 로그도 여기서 찍으면 훨씬 명확합니다.
            logger.info(f"✅ Saved Profile: {profile.symbol}")
            return True

        except ClientError as e:
            logger.error(f"❌ Failed to save profile {profile.symbol}: {e}")
            return False