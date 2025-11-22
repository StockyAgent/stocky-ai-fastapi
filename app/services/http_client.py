from contextlib import asynccontextmanager

import httpx


@asynccontextmanager
async def get_http_client():
    """
    애플리케이션 전체 라이프사이클 동안
    HTTP 연결 풀(Pool)을 효율적으로 관리하기 위한 컨텍스트 매니저
    """
    # limits: 동시 연결 수 제한 (실무 필수 설정)
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)

    async with httpx.AsyncClient(
            timeout=10.0,
            limits=limits,
            headers={"Content-Type": "application/json"},
            follow_redirects=True
    ) as client:
        yield client
        # async with 블록을 빠져나가는 순간 자동으로 client.aclose()가 호출됨
