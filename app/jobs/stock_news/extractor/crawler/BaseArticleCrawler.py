from abc import ABC, abstractmethod

import httpx


class BaseArticleCrawler(ABC):
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0 Safari/537.36"
        }

    async def fetch(self, url: str) -> str:
        try:
            # follow_redirects=True는 여기서 공통 처리
            response = await self.client.get(url, headers=self.headers, follow_redirects=True, timeout=10.0)
            response.raise_for_status()
            return self.parse(response.text)
        except Exception as e:
            print(f"⚠️ [{self.__class__.__name__}] Error: {e}")
            return ""

    @abstractmethod
    def parse(self, html: str) -> str:
        """각 사이트마다 다른 파싱 로직을 구현해야 함"""
        pass
