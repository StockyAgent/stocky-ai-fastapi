from typing import List, Optional
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError

# 우리가 정의한 Schema와 Connection을 가져옵니다.
from app.db.connection import get_dynamodb_table
from app.db.utils import execute_batch_write
from app.schemas.stockNews import StockNews


class NewsRepository:
    def __init__(self):
        self.table_name = "StockProjectData"

    async def save_news(self, news_item: StockNews) -> bool:
        """
        [책임의 이동]
        기존 모델의 to_dynamodb_item 로직이 이곳으로 이사 왔습니다.
        StockNews 객체를 받아 DynamoDB Item 형태로 변환 후 저장합니다.
        """
        # 1. Pydantic -> Dict 변환
        item_dict = news_item.model_dump()

        # 2. PK, SK 생성 (Repository가 결정)
        # PK: STOCK#{symbol}
        # SK: NEWS#{timestamp}#{id}
        pk = f"STOCK#{news_item.symbol}"
        sk = f"NEWS#{news_item.datetime}#{news_item.id}"

        item_dict['PK'] = pk
        item_dict['SK'] = sk

        # (필요시 GSI 데이터 추가 등도 여기서 수행)

        try:
            async with get_dynamodb_table(self.table_name) as table:
                await table.put_item(Item=item_dict)
            return True
        except ClientError as e:
            print(f"❌ News Save Error: {e}")
            return False

    async def fetch_news_by_date(self, symbol: str, start_ts: int, end_ts: int, min_importance: int = 6) -> List[dict]:
        """
        특정 기간의 뉴스 조회
        """
        pk_value = f"STOCK#{symbol}"
        sk_start = f"NEWS#{start_ts}#000000000"
        sk_end = f"NEWS#{end_ts}#999999999"

        try:
            async with get_dynamodb_table(self.table_name) as table:
                response = await table.query(
                    KeyConditionExpression=Key('PK').eq(pk_value) & Key('SK').between(sk_start, sk_end),
                    FilterExpression = Attr('impact_score').gte(min_importance)
                )
                return response.get('Items', [])
        except Exception as e:
            print(f"❌ Query Error: {e}")
            return []

    async def save_news_batch(self, news_list: List[StockNews]):
        """
        여러 개의 뉴스를 한 번에 저장합니다.
        """
        if not news_list:
            return

        # 1. 모델 리스트 -> DynamoDB Item(Dict) 리스트로 변환
        dynamo_items = []
        for news in news_list:
            item_dict = news.model_dump()

            # PK, SK 생성 책임은 여전히 Repository에 있음!
            item_dict['PK'] = f"STOCK#{news.symbol}"
            item_dict['SK'] = f"NEWS#{news.datetime}#{news.id}"

            dynamo_items.append(item_dict)

        # 2. 유틸 함수를 통해 배치 저장 실행
        async with get_dynamodb_table(self.table_name) as table:
            await execute_batch_write(table, dynamo_items)


# 싱글톤처럼 사용
news_repo = NewsRepository()