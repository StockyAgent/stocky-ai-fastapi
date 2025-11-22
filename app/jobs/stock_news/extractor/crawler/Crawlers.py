from bs4 import BeautifulSoup

from app.jobs.stock_news.extractor.crawler.BaseArticleCrawler import BaseArticleCrawler
from app.services.http_client import get_http_client


class YahooCrawler(BaseArticleCrawler):
    def parse(self, html: str) -> str:
        soup = BeautifulSoup(html, 'html.parser')
        selectors = [
            "div.bodyItems-wrapper p",
            "div.article-body p",
            "div.atoms-wrapper p"
        ]

        for selector in selectors:
            nodes = soup.select(selector)
            if nodes:
                return ' '.join([p.get_text().strip() for p in nodes])
        return ""

class CNBCCrawler(BaseArticleCrawler):
    def parse(self, html: str) -> str:
        # SeekingAlpha 전용 파싱 로직
        soup = BeautifulSoup(html, 'html.parser')
        selectors = [
            "div.group p",
            "div.atoms-wrapper p"
        ]

        for selector in selectors:
            nodes = soup.select(selector)
            if nodes:
                return ' '.join([p.get_text().strip() for p in nodes])
        return ""

class DefaultCrawler(BaseArticleCrawler):
    def parse(self, html: str) -> str:
        # 기본 파싱 로직
        soup = BeautifulSoup(html, 'html.parser')
        selectors = [
            "div.atoms-wrapper p",
            "div.article-body p",
            "div.article-content p",
            "section.article-body p",
            "div#article-view-content p"
        ]

        for selector in selectors:
            nodes = soup.select(selector)
            if nodes:
                return ' '.join([p.get_text().strip() for p in nodes])
        return ""

# 테스트 코드
# import asyncio
#
# async def main():
#     async with get_http_client() as client:
#         crawler = CNBCCrawler(client)
#         url= "https://finnhub.io/api/news?id=9d831cc8a34053db3d12ef17423e7a100201ddd9444d33344e3c34ee0db04ea3"
#         content = await crawler.fetch(url)
#         print(content)
#
# if __name__ == '__main__':
#     asyncio.run(main())