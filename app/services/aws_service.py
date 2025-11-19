import aioboto3
from app.core.settings import settings
from contextlib import asynccontextmanager


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

# --- 2. 세션 생성 ---
# 위에서 만든 설정값으로 세션을 생성합니다.
session = aioboto3.Session(**session_args)


# --- 3. 사용자님의 기존 코드 (변경 없음) ---
# 이하는 사용자님이 작성하신 코드와 동일하며, 잘 작동합니다.

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