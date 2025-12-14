from datetime import datetime, timedelta
from botocore.exceptions import ClientError
import logging

# [중요] 뉴스 때 만들었던 connection을 그대로 재사용합니다.
from app.db.connection import get_dynamodb_table
from app.db.utils import chunk_list
import asyncio

logger = logging.getLogger("ReportRepo")


class ReportRepository:
    def __init__(self):
        self.table_name = "StockProjectData"

    async def save_report(self, symbol: str, html: str, invest_type: str, category: str = "DAILY") -> bool:

        # 날짜 및 시간 데이터 생성
        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        created_at_iso = now.isoformat()

        # TTL 설정 (30일 후 자동 삭제)
        ttl_expire = int((now + timedelta(days=30)).timestamp())

        # PK, SK 생성 (Repository의 책임)
        pk = f"STOCK#{symbol}"
        sk = f"REPORT#{today_str}#{category}#{invest_type}"

        # 저장할 아이템 구성 (Dict)
        item = {
            'PK': pk,
            'SK': sk,
            'symbol': symbol,
            'date': today_str,
            'report_category': category,  # DAILY / URGENT
            'investment_type': invest_type,  # trader / investor
            'report_html': html,  # 리포트 본문
            'created_at': created_at_iso,
            'status': 'COMPLETED',
            'ttl': ttl_expire
        }

        try:
            # 비동기 Context Manager를 통해 테이블 리소스 획득 및 저장
            async with get_dynamodb_table(self.table_name) as table:
                await table.put_item(Item=item)

            logger.info(f"✅ Report Saved: {pk} / {sk}")
            return True

        except ClientError as e:
            logger.error(f"❌ DynamoDB Save Failed: {e}")
            raise e  # 라우터에서 500 에러 처리를 위해 예외를 다시 던짐

    async def get_report_batch(self, symbols: list[str], date: str, investment_type: str) -> dict[str, dict]:
        if not symbols:
            return {}

        found_items_map = {}

        chunks = list(chunk_list(symbols, 100))  # DynamoDB 제한
        sem = asyncio.Semaphore(5)  # 동시 요청 제한 (Throttling)

        # 내부 함수: 청크 단위 비동기 조회
        async def _fetch_chunk(chunk_symbols):
            async with sem:
                keys = [
                    {"PK": f"STOCK#{sym}", "SK": f"REPORT#{date}#DAILY#{investment_type}"}
                    for sym in chunk_symbols
                ]
                try:
                    async with get_dynamodb_table(self.table_name) as table:
                        response = await table.meta.client.batch_get_item(
                            RequestItems={
                                self.table_name: {'Keys': keys, 'ConsistentRead': False}
                            }
                        )
                        return response.get('Responses', {}).get(self.table_name, [])
                except Exception as e:
                    logger.error(f"Batch Get Error: {e}")
                    return []

        # 병렬 실행 (Parallel Execution)
        tasks = [_fetch_chunk(chunk) for chunk in chunks]
        results = await asyncio.gather(*tasks)

        # 결과 병합
        for batch in results:
            for item in batch:
                found_items_map[item['symbol']] = item

        return found_items_map


# 싱글톤 인스턴스 생성
report_repo = ReportRepository()