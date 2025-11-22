import httpx

from app.core.settings import settings


class FinnhubNewsCollector:

    def __init__(self, client: httpx.AsyncClient):
        self.BASE_URL = "https://finnhub.io/api/v1"
        self.api_key = settings.FINNHUB_API_KEY
        self.client = client

    async def fetch_stock_news(self, symbol: str, from_date: str, to_date: str):
        """finnhub 통해 주식 뉴스 수집"""
        print(f"🔍 Collecting news for {symbol} from {from_date} to {to_date}...")

        url = self.BASE_URL + "/company-news"
        params = {
            "symbol": symbol,
            "from": from_date,
            "to": to_date,
            "token": self.api_key
        }

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()  # 오류 발생 시 예외 처리
            return response.json()

        except httpx.HTTPStatusError as e:
            print(f"⚠️ HTTP Error for {symbol}: {e.response.status_code} - {e}")
            return []

        except Exception as e:
            print(f"⚠️ Failed to fetch news for {symbol}: {e}")
            return []

    async def fetch_general_news(self, category: str = "general"):
        """finnhub 통해 일반 뉴스 수집"""
        print(f"🔍 Collecting general news for category: {category}...")

        url = self.BASE_URL + "/news"
        params = {
            "category": category,
            "token": self.api_key
        }

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()  # 오류 발생 시 예외 처리
            return response.json()

        except httpx.HTTPStatusError as e:
            print(f"⚠️ HTTP Error for general news: {e.response.status_code} - {e}")
            return []

        except Exception as e:
            print(f"⚠️ Failed to fetch general news: {e}")
            return []


#테스트
async def test():
    async with httpx.AsyncClient() as client:
        collector = FinnhubNewsCollector(client)
        news = await collector.fetch_stock_news("AAPL",'2025-11-19','2025-11-20')
        print(len(news))
        print(news[0:2])

import asyncio
if __name__ == "__main__":
    asyncio.run(test())