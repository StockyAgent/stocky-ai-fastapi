import asyncio

import httpx
import yfinance as yf
from typing import Dict, Any, Optional

from app.core.settings import settings
from app.services.http_client import get_http_client


# 주식 정보 수집만 하는 역할
class FinnhubStockCollector:

    def __init__(self, client: httpx.AsyncClient):
        self.BASE_URL = "https://finnhub.io/api/v1/stock"
        self.api_key = settings.FINNHUB_API_KEY
        self.client = client

    async def fetch_mojor_symbols(self, exchange: str = "US"):
        print("🔍 Fetching stock symbols...")
        url = f"{self.BASE_URL}/symbol"
        params = {"exchange": exchange, "token": self.api_key}
        target_mics = ["XNYS", "XNAS", "XASE"]

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()  # 오류 발생 시 예외 처리

            filtered_response = [
                (item['symbol'],item['figi'])
                for item in response.json()
                if item.get('type') == 'Common Stock'  # 보통주만 (ETF, 워런트 제외)
                   and item.get('mic') in target_mics  # 메이저 거래소만
            ]

            return filtered_response

        except httpx.HTTPStatusError as e:
            print(f"⚠️ HTTP Error while fetching symbols: {e.response.status_code} - {e}")
            return []
        except Exception as e:
            print(f"⚠️ Failed to fetch symbols: {e}")
            return []




    async def fetch_profile(self, symbol: str) -> Optional[Dict[str, Any]]:
        """finnhub 통해 주식 정보(info) 수집"""
        print(f"🔍 Collecting profile for {symbol}...")

        url = f"{self.BASE_URL}/profile2"
        params = {"symbol": symbol, "token": self.api_key}

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status() # 오류 발생 시 예외 처리
            return response.json()

        except httpx.HTTPStatusError as e:
            print(f"⚠️ HTTP Error for {symbol}: {e.response.status_code} - {e}")
            return None

        except Exception as e:
            print(f"⚠️ Failed to fetch profile for {symbol}: {e}")
            return None


# 테스트
async def main():
    async with get_http_client() as client:
        collector = FinnhubStockCollector(client)

        symbols = await collector.fetch_symbols()
        print(symbols)
        print(len(symbols))

if __name__ == "__main__":
    asyncio.run(main())

