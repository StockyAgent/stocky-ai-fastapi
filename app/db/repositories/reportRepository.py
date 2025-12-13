from datetime import datetime, timedelta
from botocore.exceptions import ClientError
import logging

# [중요] 뉴스 때 만들었던 connection을 그대로 재사용합니다.
from app.db.connection import get_dynamodb_table

logger = logging.getLogger("ReportRepo")


class ReportRepository:
    def __init__(self):
        # [핵심] 뉴스 데이터와 같은 테이블을 사용합니다 (Single Table Design)
        self.table_name = "StockProjectData"

    async def save_report(self, symbol: str, html: str, invest_type: str, category: str = "DAILY") -> bool:

        # 날짜 및 시간 데이터 생성
        now = datetime.now()
        today_str = now.strftime('%Y-%m-%d')
        created_at_iso = now.isoformat()

        # TTL 설정 (30일 후 자동 삭제)
        ttl_expire = int((now + timedelta(days=30)).timestamp())

        # PK, SK 생성 (Repository의 책임)
        pk = f"REPORT#{symbol}"
        sk = f"DT#{today_str}#{category}#{invest_type}"

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


# 싱글톤 인스턴스 생성
report_repo = ReportRepository()