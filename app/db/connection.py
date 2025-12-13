import aioboto3
from contextlib import asynccontextmanager
from app.core.settings import settings

# 1. 세션 설정 (환경에 따라 분기)
session_args = {"region_name": settings.AWS_REGION}
resource_args = {}

if settings.APP_ENV == "development":
    session_args.update({
        'aws_access_key_id': 'dummy',
        'aws_secret_access_key': 'dummy'
    })
    resource_args['endpoint_url'] = settings.DYNAMODB_ENDPOINT_URL
else:
    session_args.update({
        'aws_access_key_id': settings.AWS_ACCESS_KEY_ID,
        'aws_secret_access_key': settings.AWS_SECRET_ACCESS_KEY
    })

# 전역 세션 생성
session = aioboto3.Session(**session_args)

@asynccontextmanager
async def get_dynamodb_table(table_name: str):
    """
    DynamoDB Table 리소스를 제공하는 비동기 Context Manager
    """
    async with session.resource("dynamodb", **resource_args) as dynamodb:
        table = await dynamodb.Table(table_name)
        yield table