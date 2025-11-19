import asyncio
import time


class FinnhubAsyncRateLimiter:
    def __init__(self, max_calls: int, period: int = 60):
        """
        max_calls: 기간 내 최대 호출 횟수 (예: 60회)
        period: 기간 (초 단위, 예: 60초)
        """
        self.period = period
        self.max_calls = max_calls
        self.interval = period / max_calls  # 1회 요청당 필요한 시간 (예: 1.0초)
        self.lock = asyncio.Lock()
        self.last_call_time = 0

    async def wait(self):
        """호출 간격을 강제로 조절"""
        async with self.lock:
            now = time.monotonic()
            # 마지막 호출로부터 얼마나 지났는지 계산
            elapsed = now - self.last_call_time

            # 아직 기다려야 할 시간이 남았다면 sleep
            wait_time = self.interval - elapsed
            if wait_time > 0:
                await asyncio.sleep(wait_time)

            self.last_call_time = time.monotonic()