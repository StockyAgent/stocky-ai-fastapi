from typing import Literal, Dict, List

from dotenv import load_dotenv
from langchain_core.output_parsers import JsonOutputParser, PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.jobs.stock_news.collector.FinnhubNewsCollector import FinnhubNewsCollector
from app.jobs.stock_news.extractor.crawler.CrawlerFactory import CrawlerFactory


#[단일 뉴스] LLM이 뱉어내야 할 데이터의 틀
class NewsAnalysisResult(BaseModel):
    news_id: int = Field(description="입력된 뉴스의 ID")

    sentiment: Literal["POSITIVE", "NEGATIVE", "NEUTRAL"] = Field(
        description="주가에 미칠 영향 (POSITIVE, NEGATIVE, NEUTRAL)"
    )
    importance: int = Field(
        description="주가 변동 파급력 점수 (1~10)"
    )
    summary: str = Field(
        description="원인과 결과를 포함한 한국어 한 줄 요약"
    )

# [배치] 리스트 형태의 결과 정의 (이게 핵심!)
class NewsBatchResult(BaseModel):
    results: List[NewsAnalysisResult] = Field(
        description="분석된 뉴스 결과들의 리스트"
    )

class QuickNewsAnalyzer:
    def __init__(self, chatModel):
        self.chatModel = chatModel

    def analyze(self, news_context: str, symbol:str) -> str:

        parser = PydanticOutputParser(pydantic_object=NewsAnalysisResult)

        # 시스템 프롬프트: 역할, 기준, 출력 형식을 정의
        system_template = """
        당신은 월스트리트에서 20년 경력을 가진 '수석 금융 뉴스 애널리스트'입니다. 
        당신의 임무는 주어진 뉴스 텍스트를 분석하여 특정 종목({symbol})에 미칠 영향을 평가하고 구조화된 데이터로 추출하는 것입니다.

        ### 1. 감성 분석 기준 (Sentiment)
        뉴스가 **{symbol}의 주가**에 미칠 영향을 기준으로 판단하십시오.
        - **POSITIVE**: 주가 상승 요인 (실적 호조, M&A, 신제품 성공, 목표가 상향 등)
        - **NEGATIVE**: 주가 하락 요인 (실적 부진, 규제 이슈, 소송, 악재 루머 등)
        - **NEUTRAL**: 주가에 영향이 없거나, 시장 전반의 일반적인 시황, 또는 단순한 등락 정보

        ### 2. 중요도 평가 기준 (Importance, 1~10점)
        다음 가이드라인에 따라 주가 변동성에 미칠 파급력을 정수로 평가하십시오.
        - **[9-10점]**: 초대형 이슈 (인수합병, 어닝 서프라이즈/쇼크, CEO 교체, 주요 규제 변화, 거래 정지)
        - **[7-8점]**: 주요 이슈 (신제품 출시, 대규모 계약 체결, 주요 애널리스트의 투자의견 변경)
        - **[4-6점]**: 일반 이슈 (섹터 전반의 움직임, 경쟁사 뉴스, 일반적인 실적 발표)
        - **[1-3점]**: 미미한 이슈 (단순 주가 등락 보도, 광고성 기사, 이미 알려진 사실의 재확인)

        ### 3. 요약 가이드라인 (Summary)
        - 반드시 **한국어**로 작성하십시오.
        - 뉴스의 핵심 원인과 결과를 포함하여 **한 문장**으로 요약하십시오.
        - 주어({symbol})를 명확히 하십시오.
        
        ### 출력 형식
        반드시 아래의 JSON 포맷을 지키십시오. 마크다운('''json) 태그나 추가 설명은 포함하지 마십시오.:
        {format_instructions}
        """

        # 휴먼 프롬프트: 실제 데이터 주입
        human_template = """
        종목(Symbol): {symbol}
        뉴스 내용:
        {news_context}
        """

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_template),
            ("human", human_template),
        ])

        chain = prompt | self.chatModel | parser

        try:
            response = chain.invoke({
                "news_context": news_context,
                "symbol": symbol,
                "format_instructions": parser.get_format_instructions()
            })
            return response.model_dump()
        except Exception as e:
            print(f"⚠️ 분석 실패: {e}")
            # 실패 시 기본값 반환 (시스템이 죽는 것 방지)
            return {"sentiment": "NEUTRAL", "importance": 0, "summary": "분석 실패"}

    def analyze_batch(self, news_list: List[Dict], symbol:str) -> List[Dict]:

        batch_parser = PydanticOutputParser(pydantic_object=NewsBatchResult)

        # 뉴스 리스트를 텍스트로 예쁘게 변환
        formatted_news = ""
        for item in news_list:
            formatted_news += f"\n[뉴스 ID: {item['id']}]\n내용: {item['content']}\n" + "-" * 30

        system_template = """
            당신은 월스트리트에서 20년 경력을 가진 '수석 금융 뉴스 애널리스트'입니다. 
            당신의 임무는 주어진 뉴스 텍스트를 분석하여 특정 종목({symbol})에 미칠 영향을 평가하고 구조화된 데이터로 추출하는 것입니다.

            ### 1. 감성 분석 기준 (Sentiment)
            뉴스가 **{symbol}의 주가**에 미칠 영향을 기준으로 판단하십시오.
            - **POSITIVE**: 주가 상승 요인 (실적 호조, M&A, 신제품 성공, 목표가 상향 등)
            - **NEGATIVE**: 주가 하락 요인 (실적 부진, 규제 이슈, 소송, 악재 루머 등)
            - **NEUTRAL**: 주가에 영향이 없거나, 시장 전반의 일반적인 시황, 또는 단순한 등락 정보

            ### 2. 중요도 평가 기준 (Importance, 1~10점)
            다음 가이드라인에 따라 주가 변동성에 미칠 파급력을 정수로 평가하십시오.
            - **[9-10점]**: 초대형 이슈 (인수합병, 어닝 서프라이즈/쇼크, CEO 교체, 주요 규제 변화, 거래 정지)
            - **[7-8점]**: 주요 이슈 (신제품 출시, 대규모 계약 체결, 주요 애널리스트의 투자의견 변경)
            - **[4-6점]**: 일반 이슈 (섹터 전반의 움직임, 경쟁사 뉴스, 일반적인 실적 발표)
            - **[1-3점]**: 미미한 이슈 (단순 주가 등락 보도, 광고성 기사, 이미 알려진 사실의 재확인)

            ### 3. 요약 가이드라인 (Summary)
            - 반드시 **한국어**로 작성하십시오.
            - 뉴스의 핵심 원인과 결과를 포함하여 **한 문장**으로 요약하십시오.
            - 주어({symbol})를 명확히 하십시오.
        
            ### 출력 형식
            반드시 아래의 JSON 포맷을 지키십시오. 마크다운('''json) 태그나 추가 설명은 포함하지 마십시오.:
            {format_instructions}
            """

        human_template = """
                종목(Symbol): {symbol}

                분석할 뉴스 목록:
                {formatted_news}
                """
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_template),
            ("human", human_template),
        ])

        chain = prompt | self.chatModel | batch_parser
        try:
            response = chain.invoke({
                "formatted_news": formatted_news,
                "symbol": symbol,
                "format_instructions": batch_parser.get_format_instructions()
            })

            # 결과에서 리스트 부분만 추출해서 반환
            return [res.model_dump() for res in response.results]

        except Exception as e:
            print(f"⚠️ 배치 분석 실패: {e}")
            return []




#테스트
async def main():
    load_dotenv()
    analyzer = QuickNewsAnalyzer(ChatOpenAI(model="gpt-4o-mini", temperature=0))
    import httpx
    async with httpx.AsyncClient() as client:
        collector = FinnhubNewsCollector(client)
        news = await collector.fetch_stock_news("AAPL", '2025-11-19', '2025-11-20')

        factory = CrawlerFactory(client)
        for item in news:
            source = item['source']
            url = item['url']

            # 1. 공장에 "이 소스 담당자 나와!" 요청
            crawler = factory.get_crawler(source)
            content = await crawler.fetch(url)

            item['content'] = content
        result = analyzer.analyze_batch(news[:10], "AAPL")
        print(result)
        print()

        for item in news[:10]:
            for res in result:
                if item['id'] == res['news_id']:
                    print(f"뉴스 ID: {item['id']}")
                    print(f"뉴스 finnhub 요약: {item['summary']}")
                    print(f"요약: {res['summary']}")
                    print(f"감성: {res['sentiment']}, 중요도: {res['importance']}")
                    print("-" * 40)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())