import asyncio
from botocore.exceptions import ClientError
import logging

logger = logging.getLogger("DBUtils")


def chunk_list(data, size):
    for i in range(0, len(data), size):
        yield data[i:i + size]


async def execute_batch_write(table, items: list):
    """
    DynamoDB Table 객체와 Item 리스트(Dict 형태)를 받아 배치 저장을 수행합니다.
    (재시도 로직 및 세마포어 포함)
    """
    if not items:
        return

    # DynamoDB 배치 쓰기 제한 (25개)
    chunks = list(chunk_list(items, 25))

    # 동시 실행 제어 (너무 많은 요청 방지)
    sem = asyncio.Semaphore(5)

    async def _write_chunk(chunk_items):
        async with sem:
            request_items = {
                table.name: [{'PutRequest': {'Item': item}} for item in chunk_items]
            }

            max_retries = 5
            for attempt in range(max_retries + 1):
                try:
                    # aioboto3 테이블 객체의 batch_write_item 호출
                    # 주의: table.meta.client가 아니라 resource 레벨 메서드 사용 시 문법이 다를 수 있음
                    # 여기서는 low-level client 접근 방식을 유지합니다.
                    response = await table.meta.client.batch_write_item(RequestItems=request_items)

                    unprocessed = response.get("UnprocessedItems", {})
                    if not unprocessed:
                        return  # 성공

                    # 실패한 것만 남겨서 재시도
                    request_items = unprocessed
                    sleep_time = (0.1 * (2 ** attempt))
                    await asyncio.sleep(sleep_time)

                except ClientError as e:
                    if e.response['Error']['Code'] == 'ProvisionedThroughputExceededException':
                        await asyncio.sleep(1 * (2 ** attempt))
                    else:
                        logger.error(f"Batch Write Error: {e}")
                        break

    tasks = [_write_chunk(chunk) for chunk in chunks]
    if tasks:
        await asyncio.gather(*tasks)