import logging
from typing import Literal

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.constants import END
from langgraph.graph import StateGraph
from pydantic import BaseModel, Field

from app.jobs.Daily_report_agent.state.state import ReportState, StockReportSchema
from app.jobs.Daily_report_agent.tools.tools import fetch_stock_price_for_investor, fetch_db_news, \
    search_market_issues, \
    render_html_report, fetch_stock_price_for_traders
from datetime import datetime



logger = logging.getLogger("nodes")

# 환경변수 로드
load_dotenv()

# LLM 설정
llm_smart = ChatOpenAI(model="gpt-4o", temperature=0)
llm_fast = ChatOpenAI(model="gpt-4o-mini", temperature=0)

async def node_collector(state: ReportState):
    symbol = state["symbol"]
    logger.info(f"\n🚀 [1. Collector] 필수 데이터 수집 시작 ({symbol})...")

    # 월요일(0)이면 3일, 그 외는 1일
    today = datetime.now()
    weekday_value = today.weekday()
    if weekday_value == 6:
        days_to_fetch = 2
    elif weekday_value == 0:
        days_to_fetch = 3
    else:
        days_to_fetch = 1

    # 비동기 함수는 ainvoke + await
    investment_type = state.get("investment_type", "investor")
    if investment_type == "trader":
        price_data = await fetch_stock_price_for_traders.ainvoke({"symbol": symbol})
    else:
        price_data = await fetch_stock_price_for_investor.ainvoke({"symbol": symbol})

    news_data = await fetch_db_news.ainvoke({"symbol": symbol, "days": days_to_fetch})

    # news_data = []
    logger.info(f"   - 주가 정보 확보 완료")
    logger.info(f"   - 내부 DB 뉴스: {len(news_data)}건 확보")

    return {
        "price_data": price_data,
        "news_data": news_data
    }


class AnalysisResult(BaseModel):
    is_sufficient: bool = Field(description="정보 충분 여부")
    missing_reason: str = Field(..., description="불충분할 경우 그 이유 (한 문장 요약)")
    search_keyword: str = Field(..., description="불충분할 경우 추가 검색할 영어 키워드 (충분하면 빈 문자열)")


def node_analyzer(state: ReportState):
    logger.info(f"🧠 [2. Analyzer] 데이터 분석 중...")
    symbol = state["symbol"]
    news_data = state["news_data"]
    price_change = state.get("price_data", {}).get("change_pct", 0.0)

    if not news_data:
        news_context = "수집된 뉴스 없음."
    else:
        news_context = "\n".join(
            [f"- [{n.get('date', 'Date Unknown')}] {n.get('title')}: {n.get('content', '')}..."
             for n in news_data]
        )

    prompt = ChatPromptTemplate.from_template("""
    당신은 '수석 주식 애널리스트'입니다. 
    현재 수집된 뉴스 데이터가 투자 리포트를 작성하기에 충분한지 평가하십시오.

    [분석 대상]
    - 종목: {symbol}
    - 오늘 주가 변동률: {price_change}%
    - 수집된 뉴스 목록:
    {news_context}

    [평가 기준 (Checklist)]
    1. **최신성 (Recency)**: 뉴스가 최근 24~48시간 이내의 것인가? (오래된 뉴스는 무의미함)
    2. **인과관계 (Causality) - *가장 중요***:
   - **Case A: 주가 변동폭이 큽니까? (절대값 3% 이상)**
     - **필수:** 뉴스가 이 큰 변동의 **직접적인 원인**을 명확히 설명해야 합니다.
     - 설명하지 못한다면 -> `is_sufficient: False` (이유: 급등락 원인 불명)

   - **Case B: 주가 변동폭이 작습니까? (절대값 3% 미만)**
     - **주의:** 작은 변동(예: 0.2%, -0.5%)은 통상적인 시장 노이즈입니다.
     - **지침:** 뉴스가 주가 변동을 설명할 필요가 **없습니다.** - 뉴스 내용이 유익하고 구체적이라면, 주가 변동과 상관없이 `is_sufficient: True`로 판단하십시오.
     - **경고:** "0.5% 하락의 원인을 설명하지 못해서 불충분하다"라고 판단하면 **감점**입니다.

    3. **구체성 (Specificity)**: 구체적인 수치(실적 발표, 계약 규모)나 사건(CEO 사임, 규제 발표)이 포함되어 있는가?
       - 단순히 "시장 변동성", "기술적 분석" 같은 뜬구름 잡는 소리는 -> '불충분'

    [출력 지침]
- 위 로직에 따라 판단 결과(`is_sufficient`)를 결정하십시오.
- `is_sufficient`가 False라면, 부족한 정보를 찾기 위한 검색어로는 그냥 회사명만 주세요. 검색 도구를 활용할 때 그게 가장 결과가 좋습니다. 검색어로 그냥 symbol의 회사 이름만 주세요 
- `is_sufficient`가 True라면, 검색어는 빈 문자열로 두십시오.
    """)
    chain = prompt | llm_fast.with_structured_output(AnalysisResult)
    result = chain.invoke({
        "symbol": symbol,
        "news_context": news_context,
        "price_change": price_change
    })

    # 로그 출력
    if result.is_sufficient:
        logger.info(f"   ✅ 판단: 충분함.")
    else:
        logger.info(f"   ⚠️ 판단: 불충분함. ({result.missing_reason})")
        logger.info(f"   🔍 추가 검색어: {result.search_keyword}")

    return {
        "is_data_sufficient": result.is_sufficient,
        "missing_info_reason": result.missing_reason,
        "search_keyword": result.search_keyword
    }


async def node_searcher(state: ReportState):
    print(f"🔎 [3. Searcher] 추가 검색: {state['search_keyword']}")
    web_news = await search_market_issues.ainvoke({"query": state["search_keyword"]})
    return {"news_data": state["news_data"] + web_news}


async def node_writer(state: ReportState):
    logger.info("📝 [4. Writer] 리포트 json 데이터 생성 중...")
    investment_type = state.get("investment_type")
    current_date = datetime.now().strftime("%Y-%m-%d")

    TRADER_PROMPT = """
        당신은 월스트리트의 전설적인 20년 차 **'데이 트레이더(Day Trader)'**입니다.
        당신의 고객은 **"내일 주가가 오를까? 내릴까?"**에만 관심 있는 공격적인 단기 투자자입니다.

        [필수 지침]
        1. **어조**: 빠르고, 직관적이며, 긴박하게 작성하세요. "천천히 지켜봅시다" 같은 말은 금지입니다.
        2. **Headline**: 기업 비전보다는 지금 시장을 움직이는 **'재료(Catalyst)'**를 자극적으로 뽑으세요.
        3. **Price Analysis**: 
           - 제공된 기술적 지표(RSI, 지지/저항선, 거래량)를 반드시 활용하여 기술적 분석을 수행하세요.
           - "차트상 과열권", "단기 골든크로스", "손절 라인 위협" 등 트레이더 용어를 사용하세요.
        4. **Key Issues**: 이 뉴스가 **내일 시초가(Gap)**에 영향을 줄지 판단하여 호재/악재를 가르세요.
        5. **Insight**: 구체적인 **매매 전략(Action Plan)**을 제시하세요. (예: "$180 돌파 시 추격 매수 유효")

        """

    INVESTOR_PROMPT = """
            당신은 한국의 개인 투자자를 위한 **심층 분석 금융 전문 에디터**입니다.
            제공된 데이터를 바탕으로 독자가 고개를 끄덕일 수 있는 **논리적인 한국어 리포트**를 작성하세요.

            [입력 데이터]
            - 기준일: {current_date}
            - 종목: {symbol}
            - 주가 데이터: {price_data}
            - 뉴스 데이터: {news_data}

            [필수 작성 규칙]
            1. **Headline & Metaphor:** {symbol}의 현재 상황을 찰진 비유(예: "폭풍 전야", "날개 단 호랑이")를 섞어 한 줄로 요약하세요.
            2. **Key Issues (이슈 분석):**
               - 뉴스 내용을 분석하여 **'호재'**, **'악재'**, **'소송'**, **'실적'** 등으로 분류하세요.
               - **Fact (사실):** 육하원칙에 의거하여 작성하되, **"이 사건의 배경(Context)"**을 반드시 한 줄 이상 포함하세요. (예: 지난달부터 이어진 ~~논란이 결국...)
               - **Analysis (해석):** **"결과만 말하지 말고 과정을 설명하세요." *포맷 엄수*:** 해석은 줄글로 길게 쓰지 말고, 반드시 아래 **3단 구조와 아이콘**을 사용하여 **줄바꿈**으로 구분해 작성하세요.
               [작성 포맷 예시]
                 <br>💡 의미: 이 뉴스가 해당 기업의 매출/이익 구조에 구체적으로 어떤 영향을 주는가?
                 <br>🌊 파급: 이것이 시장이나 경쟁사에 어떤 변화를 가져오는가?
                 <br>⚖️ 결론: 그래서 이것이 왜 주가에 긍정적/부정적인가?
               - 막연히 "좋다/나쁘다"가 아니라, "수수료 수익이 10% 감소할 우려가 있어 악재다"처럼 구체적으로 쓰세요.
            3. **Insight:** 한국 투자자 관점에서 지금 사야 할지, 관망해야 할지 구체적인 행동 가이드를 제시하세요.
            """

    system_instruction = TRADER_PROMPT if investment_type == "trader" else INVESTOR_PROMPT

    base_prompt = ChatPromptTemplate.from_template("""
              {system_instruction}

              [입력 데이터]
              - 기준일: {current_date}
              - 종목: {symbol}
              - 주가/지표 데이터: {price_data}
              - 뉴스 데이터: {news_data}

              [출력 형식 (JSON)]
              StockReportSchema에 맞춰 **반드시 한국어**로 작성하십시오.
              Key Issues 작성 시 Fact(사실)와 Analysis(해석 - 페르소나 관점)를 명확히 분리하십시오.
          """)
    chain = base_prompt | llm_smart.with_structured_output(StockReportSchema)

    report_data = chain.invoke({
        "system_instruction": system_instruction,
        "symbol": state["symbol"],
        "current_date": current_date,
        "price_data": str(state["price_data"]),
        "news_data": str(state["news_data"])
    })

    return {"draft": report_data}


class ReportReviewResult(BaseModel):
    is_hallucination: bool = Field(description="할루시네이션 여부")
    is_pass: bool = Field(description="내용이 정확한지 여부")
    feedback: str = Field(
        description="할루시네이션이 발견된 경우거나 , 이를 바로잡기 위해 구체적인 피드백 제공"
    )


def node_reviewer(state: ReportState):
    logger.info("🔍 [5. Reviewer] 리포트 검수 중...")

    symbol = state["symbol"]
    news_data = state["news_data"]
    price_data = state["price_data"]
    draft = state["draft"]

    if not draft:
        return {"is_hallucination": False, "feedback": "No Draft to review."}

    reviewer_prompt = ChatPromptTemplate.from_template("""
        당신은 리포트 검수 편집장입니다.
        아래 [뉴스 데이터]와 [작성된 리포트]를 대조하여 거짓 정보(Hallucination)가 있는지 확인하세요.
        또한 이슈들의 내용 구성이 주어진 정보를 토대로 적합한지를 검수하세요.

        [가격 데이터]
        {price_data}

        [뉴스 데이터]
        {news_data}


        [작성된 리포트]
        제목: {headline}
        내용: {price_analysis}
        이슈: {key_issues}

        [판단 기준]
        1. 뉴스에 없는 구체적인 숫자(가격, 날짜, 수익률)를 지어냈는가? -> is_hallucination: True
        2. 뉴스 내용과 정반대로 해석했는가? -> is_hallucination: True
        3. 팩트에 기반하여 정확한가? -> is_hallucination: False
        4. 중요도를 고려해서 이슈를 적절히 선정하여 작성했는가? -> is_pass: True
        5. 더 중요한 이슈가 있는데 이를 빼먹었는가 -> is_pass: False

        문제가 있다면 'feedback'에 무엇을 보완해야 할지를 적으세요.
        """)

    chain = reviewer_prompt | llm_smart.with_structured_output(ReportReviewResult)
    result = chain.invoke({
        "symbol": symbol,
        "news_data": news_data,
        "price_data": price_data,
        "headline": draft.headline,
        "price_analysis": draft.price_analysis,
        "key_issues": str(draft.key_issues)
    })

    # 검수 로직 구현 (생략)
    print(result)
    return {"is_hallucination": result.is_hallucination, "is_pass": result.is_pass, "feedback": result.feedback}


def decide_route(state: ReportState):
    if not state["is_data_sufficient"]:
        return "searcher"
    else:
        return "writer"  # 추후 수정


def route_after_review(state):
    if state["is_hallucination"]:
        return "writer"  # 검수 통과 -> 종료
    elif not state["is_pass"]:
        return "writer"
    else:
        return "END"  # 검수 실패 -> 다시 검색


# ================================
workflow = StateGraph(ReportState)
workflow.add_node("collector", node_collector)
workflow.add_node("analyzer", node_analyzer)
workflow.add_node("searcher", node_searcher)
workflow.add_node("writer", node_writer)
workflow.add_node("reviewer", node_reviewer)

workflow.set_entry_point("collector")
workflow.add_edge("collector", "analyzer")
workflow.add_conditional_edges("analyzer", decide_route, {"writer": "writer", "searcher": "searcher"})
workflow.add_edge("searcher", "writer")
workflow.add_edge("writer", "reviewer")
workflow.add_conditional_edges("reviewer", route_after_review, {"writer": "writer", "END": END})
# workflow.add_edge("writer", END)

app = workflow.compile()


async def write_report(symbol: str, investment_type: Literal["trader", "investor"] = "investor"):
    initial_state = {
        "symbol": symbol,
        "investment_type": investment_type,
        "news_data": [],
        "price_data": {},
        "is_data_sufficient": False,
        "search_keyword": "",
        "draft": None,
        "feedback": None,
        "is_pass": True,
        "is_hallucination": False,

    }

    final_state = await app.ainvoke(initial_state)
    report_data = final_state["draft"]
    if report_data:
        logger.info("\n🎨 [Renderer] HTML 리포트 생성 완료")
        final_html = render_html_report(symbol, report_data)

        print("\n" + "=" * 50)
        print(final_html)
        print("=" * 50)
        return final_html
    else:
        logger.info("❌ 리포트 생성 실패")

#
# async def main():
#     symbol = "NVDA"
#     print(f"----- [{symbol} Stocky Agent (Korean + Color Fix)] -----")
#
#     initial_state = {
#         "symbol": symbol,
#         "news_data": [],
#         "price_data": {},
#         "is_data_sufficient": False,
#         "search_keyword": "",
#         "draft": None,
#         "feedback": None,
#         "is_pass": True,
#         "is_hallucination": False,
#
#     }
#     final_state = await app.ainvoke(initial_state)
#     analysis = (str(final_state["is_data_sufficient"]) + ", "
#                 + str(final_state["search_keyword"]) + ", "
#                 )
#
#     report_data = final_state["draft"]
#     if report_data:
#         print("\n🎨 [Renderer] HTML 리포트 생성 완료")
#         final_html = render_html_report(symbol, report_data)
#
#         print("\n" + "=" * 50)
#         print(final_html)
#         print("=" * 50)
#     else:
#         print("❌ 리포트 생성 실패")
#     print(f"\n🏁 최종 상태: {analysis}")
#
# if __name__ == "__main__":
#     import asyncio
#     asyncio.run(main())