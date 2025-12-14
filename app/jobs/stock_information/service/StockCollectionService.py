from app.core.AsyncRateLimiter import FinnhubAsyncRateLimiter
from app.schemas.stock import StockProfile
from app.jobs.stock_information.collector.FinnhubStockCollector import FinnhubStockCollector
# from app.services.aws_service import put_item_dynamodb
import asyncio


class StockCollectionService:
    def __init__(self, collector: FinnhubStockCollector):
        self.collector = collector
        self.table_name = "StockProjectData"


    async def update_stock_profiles(self):
        print("주식 정보 업데이트 시작")

        symbols = await self.collector.fetch_mojor_symbols()
        if not symbols:
            print("⚠️ No symbols fetched.")
            return

        # 1. Rate Limiter 설정 (안전하게 1분에 55회 정도로 설정 추천)
        # 60초 동안 60회 = 1초에 1회
        rate_limiter = FinnhubAsyncRateLimiter(max_calls=55, period=60)

        # 2. Semaphore 설정 (동시 연결 수 제한)
        semaphore = asyncio.Semaphore(5)

        async def process_with_limit(sym, figi):
            # Semaphore로 동시 실행 제어 (내 서버 보호)
            async with semaphore:
                # RateLimiter로 빈도 제어 (상대 서버 보호)
                # 여기서 1초가 안 지났으면 대기하게 됨
                await rate_limiter.wait()

                try:
                    return await self._process_single_symbol(sym, figi)
                except Exception as e:
                    print(f"Error processing {sym}: {e}")
                    return None

        # Task 생성
        tasks = [process_with_limit(sym, figi) for sym,figi in symbols]

        # 실행
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _process_single_symbol(self, symbol, figi):
        raw_data = await self.collector.fetch_profile(symbol)
        if not raw_data:
            return

        # 2. 데이터 변환 (Pydantic)
        try:
            profile = StockProfile(
                figi = figi,
                symbol=symbol,
                name=raw_data.get("name"),
                country=raw_data.get("country"),
                currency=raw_data.get("currency"),
                exchange=raw_data.get("exchange"),
                ipo=raw_data.get("ipo"),
                logo=raw_data.get("logo"),
                marketCapitalization=raw_data.get("marketCapitalization"),
                phone=raw_data.get("phone"),
                shareOutstanding=raw_data.get("shareOutstanding"), # 주식 발행 수
                weburl=raw_data.get("weburl")
            )
        except Exception as e:
            print(f"⚠️ Validation Error for {symbol}: {e}")
            return

        # 3. 데이터 저장 (사용자님의 aws_service 함수 활용)
        await put_item_dynamodb(
            table_name=self.table_name,
            item=profile.to_dynamodb_item()
        )
        print(f"✅ Saved profile for {symbol}")


# # 테스트용 메인 함수
# async def main():
#     async with get_http_client() as client:
#         stock_collection_service = StockCollectionService(FinnhubStockCollector(client=client))
#         await stock_collection_service.update_stock_profiles()
#
# if __name__ == "__main__":
#     asyncio.run(main())