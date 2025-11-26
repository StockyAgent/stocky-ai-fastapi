import aioboto3
from app.core.settings import settings
from contextlib import asynccontextmanager
from botocore.exceptions import ClientError
import asyncio

#공통 설정
session_args = {
    "region_name": settings.AWS_REGION
}

# 개발 환경일 경우 로컬 dynamodb를 사용하고,
# 운영 환경일 경우 실제 AWS DynamoDB를 사용하도록 설정합니다.
# --- 1. 환경별 설정 분기 ---
print(settings.APP_ENV)
if settings.APP_ENV == "development":
    # (1) 개발 환경일 경우 (로컬 Docker)
    session_args['aws_access_key_id'] = 'dummy'  # 로컬에선 의미 없음
    session_args['aws_secret_access_key'] = 'dummy'  # 로컬에선 의미 없음

    # (중요) Boto3가 바라볼 엔드포인트를 로컬 주소로 변경합니다.
    resource_args = {
        "endpoint_url": settings.DYNAMODB_ENDPOINT_URL
    }

else:
    # (2) 운영 환경일 경우 (실제 AWS)
    session_args['aws_access_key_id'] = settings.AWS_ACCESS_KEY_ID
    session_args['aws_secret_access_key'] = settings.AWS_SECRET_ACCESS_KEY

    # (중요) 실제 AWS를 바라볼 때는 endpoint_url이 없어야 합니다.
    resource_args = {}

# 위에서 만든 설정값으로 세션을 생성합니다.
session = aioboto3.Session(**session_args)

@asynccontextmanager
async def get_dynamodb_resource():
    """DynamoDB 리소스 세션을 제공 (환경에 맞게 연결됨)"""

    # 리소스를 생성할 때만 endpoint_url을 지정합니다.
    async with session.resource("dynamodb", **resource_args) as resource:
        yield resource


async def put_item_dynamodb(table_name: str, item: dict):
    """
    DynamoDB 테이블에 단일 아이템을 put (Upsert) 합니다.
    item 딕셔너리 안에 PK와 SK가 포함되어야 합니다.
    """
    try:
        async with get_dynamodb_resource() as dynamo_resource:
            table = await dynamo_resource.Table(table_name)
            await table.put_item(Item=item)
            print(f"Successfully put item into {table_name}")  # (디버깅용)
    except Exception as e:
        print(f"Error putting item into DynamoDB {table_name}: {e}")
        # (에러 처리 로직)

# 데이터 25개씩 자르기 (DynamoDB 물리적 제약 준수용)
def chunk_list(data, size):
    for i in range(0, len(data), size):
        yield data[i:i + size]


# 병렬 배치 저장 함수
async def put_items_batch_dynamodb(table_name: str, items: list):
    if not items:
        return

    # [Rate Limit] WCU 초과 방지용
    # 10개 = 한 번에 최대 250개(25*10) 아이템 처리 시도
    sem = asyncio.Semaphore(10)

    # 내부 작업 함수: 25개 묶음 하나를 전송
    async def _write_chunk(table, chunk):
        async with sem:  # 신호등(Semaphore) 확인
            request_items = {
                table_name: [{'PutRequest': {'Item': item}} for item in chunk]
            }

            max_retries = 5 # 최대 재시도 횟수 : 추후에 설정 가능하도록 변경 고려

            for attempt in range(max_retries + 1):
                try:
                    response = await table.meta.client.batch_write_item(RequestItems=request_items)

                    unprocessed = response.get("UnprocessedItems", {})
                    if not unprocessed:
                        return

                    request_items = unprocessed
                    import random
                    sleep_time = (0.05 * (2 ** attempt)) + (random.uniform(0, 0.05)) # 지수 백오프
                    print(f"재시도 {attempt + 1}/{max_retries}: {len(unprocessed[table_name])}개 남음. {sleep_time:.2f}초 대기")
                    await asyncio.sleep(sleep_time)
                except ClientError as e:
                    error_code = e.response['Error']['Code']
                    #용량 초과 에러라면 재시도
                    if error_code == 'ProvisionedThroughputExceededException':
                        sleep_time = (0.1 * (2 ** attempt))
                        await asyncio.sleep(sleep_time)
                        continue
                    else:
                        # 그 외 에러는 재시도 안함
                        print(f"Critical Error: {e}")
                        #추후 DLQ로 보내는 로직 추가 가능
                        break




    # 메인 로직
    async with get_dynamodb_resource() as dynamo_resource:
        table = await dynamo_resource.Table(table_name)

        # 1. 25개씩 쪼개기 (Safety)
        chunks = list(chunk_list(items, 25))

        # 2. 작업 생성 (병렬 처리 준비)
        tasks = [_write_chunk(table, chunk) for chunk in chunks]

        # 3. 동시 실행 (Performance)
        if tasks:

            await asyncio.gather(*tasks)

