import httpx

from app.jobs.stock_news.collector.FinnhubNewsCollector import FinnhubNewsCollector
from app.jobs.stock_news.extractor.crawler.BaseArticleCrawler import BaseArticleCrawler
from app.jobs.stock_news.extractor.crawler.Crawlers import YahooCrawler, CNBCCrawler, DefaultCrawler


class CrawlerFactory:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        # 크롤러 인스턴스를 미리 생성해둠 (싱글톤처럼 재사용)
        self.crawlers = {
            "yahoo": YahooCrawler(client),
            "cnbc": CNBCCrawler(client),
            "default": DefaultCrawler(client)
        }

    def get_crawler(self, source: str) -> BaseArticleCrawler:
        """source 문자열(예: 'Yahoo', 'SeekingAlpha')을 보고 크롤러 반환"""
        key = source.lower().replace(" ", "")  # 'Yahoo Finance' -> 'yahoofinance'

        if "yahoo" in key:
            return self.crawlers["yahoo"]
        elif "cnbc" in key:
            return self.crawlers["cnbc"]
        else:
            return self.crawlers["default"]

# # 테스트 코드
import asyncio
async def main():


    async with httpx.AsyncClient() as client:
        finnhubNewsCollector = FinnhubNewsCollector(client)
        news_items = await finnhubNewsCollector.fetch_stock_news("AAPL", "2025-11-20", "2025-11-21")

        # 공장 가동
        factory = CrawlerFactory(client)

        for item in news_items:
            source = item['source']
            url = item['url']

            # 1. 공장에 "이 소스 담당자 나와!" 요청
            crawler = factory.get_crawler(source)
            content = await crawler.fetch(url)

            print(f"item: {item} \ncrawler: {crawler} \n\n" )

            # 2. 누가 나왔는지 신경 안 쓰고 fetch 실행 (다형성)
            # content = await crawler.fetch(url)
            # print(f"✅ [{source}] Content Length: {len(content)}")


if __name__ == "__main__":
    asyncio.run(main())