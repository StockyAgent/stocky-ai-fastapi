import decimal
from typing import List, Optional
import yfinance as yf
# from duckduckgo_search import DDGS
from langchain_community.tools import DuckDuckGoSearchRun
from langchain.tools import tool
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field

from app.db.repositories.StockNewsRepository import news_repo
from app.jobs.Daily_report_agent.state.state import StockReportSchema
# from app.services.aws_service import fetch_news_by_date
import pandas as pd


# 가격 조회 tool

class PriceInput(BaseModel): # 가격 조회 입력 스키마
    symbol: str = Field(description="종목 코드 (예: AAPL, TSLA)")

def calculate_rsi(series, period=14):
    """RSI(상대강도지수)를 계산합니다."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    return 100 - (100 / (1 + rs))

@tool(args_schema=PriceInput)
async def fetch_stock_price_for_traders(symbol: str) -> dict:
    """트레이더들을 위한 데이터들을 수집합니다 (rsi, rvol, 지지선/저항선, 이동평균선 등)"""
    try:
        ticker = yf.Ticker(symbol)

        hist = ticker.history(period="3mo")
        if hist.empty:
            return {
                "error": "데이터 없음",
                "summary": f"'{symbol}'에 대한 주가 데이터를 찾을 수 없습니다. 티커를 확인해주세요."
            }

        # 현재가 및 기본 정보
        current_price = hist['Close'].iloc[-1]
        prev_close = hist['Close'].iloc[-2]

        # rsi 계산
        hist['RSI'] = calculate_rsi(hist['Close'])
        current_rsi = hist['RSI'].iloc[-1]

        rsi_status = "(중립)"
        if current_rsi >= 70:
            rsi_status = "(🔥과매수 - 조정 주의)"
        elif current_rsi <= 30:
            rsi_status = "(💧과매도 - 반등 가능성)"
        elif current_rsi >= 60:
            rsi_status = "(상승 모멘텀 강함)"
        elif current_rsi <= 40:
            rsi_status = "(하락세 우세)"

        #거래량 비율
        vol_today = hist['Volume'].iloc[-1]
        vol_ma20 = hist['Volume'].iloc[-21:-1].mean()

        # RVOL 계산 (평소 대비 몇 %인가?)
        if vol_ma20 == 0 or pd.isna(vol_ma20):
            rvol_percent = 100  # 데이터 부족 시 기본값
        else:
            rvol_percent = (vol_today / vol_ma20) * 100

            # RVOL 상태 해석
            vol_comment = "평소 수준"
            if rvol_percent > 300:
                vol_comment = "🔥폭발적 거래량 (강한 세력/이슈 발생)"
            elif rvol_percent > 150:
                vol_comment = "거래 활발 (평소의 1.5배)"
            elif rvol_percent < 50:
                vol_comment = "거래 절벽 (시장 소외)"
            elif rvol_percent < 80:
                vol_comment = "거래 감소 (눈치보기)"

        # 3. 지지선 & 저항선 (최근 60일(분기) 기준 - 더 의미있는 저항선)
        recent_60 = hist.tail(60)
        support_line = recent_60['Low'].min()
        resistance_line = recent_60['High'].max()

        # 4. 이동평균선 배열 및 추세 판단
        ma5 = hist['Close'].rolling(window=5).mean().iloc[-1]
        ma20 = hist['Close'].rolling(window=20).mean().iloc[-1]
        ma60 = hist['Close'].rolling(window=60).mean().iloc[-1]  # 수급선 추가

        trend_status = "횡보/박스권"
        # 정배열 조건: 5 > 20 > 60
        if ma5 > ma20 and ma20 > ma60:
            trend_status = "🚀 확고한 상승 추세 (정배열)"
        # 역배열 조건: 5 < 20 < 60
        elif ma5 < ma20 and ma20 < ma60:
            trend_status = "☠️ 확고한 하락 추세 (역배열)"
        elif current_price > ma20:
            trend_status = "↗️ 단기 상승세 (20일선 위)"
        elif current_price < ma20:
            trend_status = "↘️ 단기 조정/하락 (20일선 아래)"

        # 최근 7일치(휴일 제외)만 남깁니다.
        recent_7_days = hist.tail(7)

        history_list = []
        for date, row in recent_7_days.iterrows():
            date_str = date.strftime('%Y-%m-%d')
            history_list.append({
                "date": date_str,
                "close": round(row['Close'], 2),
                "volume": int(row['Volume'])
            })


        # 등락률 계산
        change_amount = current_price - prev_close
        change_pct = (change_amount / prev_close) * 100

        #  LLM을 위한 요약 텍스트 생성
        trend_str = " -> ".join([f"{h['close']}" for h in history_list])

        summary = (
            f"[{symbol} 최신 주가 정보]\n"
            f"- 현재가: ${current_price:.2f} ({change_pct:+.2f}%)\n"
            f"- 최근 7일 추세: {trend_str}"
        )

        technical_analysis = {
            "RSI": f"{current_rsi:.1f} {rsi_status}",
            # 여기가 변경되었습니다: Volume Ratio -> RVOL
            "RVOL": f"평소의 {rvol_percent:.0f}% 수준 - {vol_comment}",
            "Trend": trend_status,
            "Key_Levels": {
                "Support_60d": f"${support_line:.2f}",
                "Resistance_60d": f"${resistance_line:.2f}"
            },
            "Moving_Averages": {
                "MA5": f"${ma5:.1f}",
                "MA20": f"${ma20:.1f}",
                "MA60": f"${ma60:.1f}"
            }
        }

        return {
            "symbol": symbol,
            "current_price": current_price,
            "change_pct": round(change_pct, 2),
            "history_7_days": history_list,  # 그래프 그리기용 데이터
            "technical_analysis": technical_analysis,
            "summary": summary  # LLM이 읽을 자연어 요약
        }

    except Exception as e:
        return {
            "error": str(e),
            "summary": f"주가 조회 중 에러 발생: {e}"
        }



@tool(args_schema=PriceInput)
async def fetch_stock_price_for_investor(symbol: str) -> dict:
    """주식의 최근 7일간 가격 정보를 조회합니다."""
    try:
        ticker = yf.Ticker(symbol)

        hist = ticker.history(period="1mo")
        if hist.empty:
            return {
                "error": "데이터 없음",
                "summary": f"'{symbol}'에 대한 주가 데이터를 찾을 수 없습니다. 티커를 확인해주세요."
            }

        # 최근 7일치(휴일 제외)만 남깁니다.
        recent_7_days = hist.tail(7)

        history_list = []
        for date, row in recent_7_days.iterrows():
            date_str = date.strftime('%Y-%m-%d')
            history_list.append({
                "date": date_str,
                "close": round(row['Close'], 2),
                "volume": int(row['Volume'])
            })

        # 현재(오늘) 데이터 기준 지표 계산
        current_data = hist.iloc[-1]  # 가장 최신 데이터
        prev_data = hist.iloc[-2]  # 전일 데이터 (등락률 계산용)

        current_price = float(current_data['Close'])
        prev_close = float(prev_data['Close'])

        # 등락률 계산
        change_amount = current_price - prev_close
        change_pct = (change_amount / prev_close) * 100

        #  LLM을 위한 요약 텍스트 생성
        trend_str = " -> ".join([f"{h['close']}" for h in history_list])

        summary = (
            f"[{symbol} 최신 주가 정보]\n"
            f"- 현재가: ${current_price:.2f} ({change_pct:+.2f}%)\n"
            f"- 거래량: {int(current_data['Volume']):,}\n"
            f"- 최근 7일 추세: {trend_str}"
        )

        return {
            "symbol": symbol,
            "current_price": current_price,
            "change_pct": round(change_pct, 2),
            "volume": int(current_data['Volume']),
            "history_7_days": history_list,  # 그래프 그리기용 데이터
            "summary": summary  # LLM이 읽을 자연어 요약
        }

    except Exception as e:
        return {
            "error": str(e),
            "summary": f"주가 조회 중 에러 발생: {e}"
        }

# 주식 뉴스 조회 tool
class DBNewsInput(BaseModel):
    symbol: str = Field(description="종목 코드")
    days: int = Field(default=1, description="오늘로부터 몇일분 뉴스를 조회할지 (기본값: 1일) 오늘 만약 월요일이면 3일로 설정해")
    min_importance: int = Field(default=6, description="중요도 필터")


@tool(args_schema=DBNewsInput)
async def fetch_db_news(symbol: str, days: int = 1, min_importance: int = 6) -> List[dict]:
    """DynamoDB에서 특정 기간의 중요도 있는 뉴스를 조회합니다."""

    # UTC 기준으로 날짜 계산
    now_utc = datetime.now(timezone.utc)
    from_date = now_utc - timedelta(days=days)

    # from_date의 00:00:00
    from_dt = from_date.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    # to_date(현재)
    to_dt = now_utc.timestamp()

    print(f"📚 [Tool] DynamoDB 조회: {symbol} (지난 {days}일)")

    try:
        # 실제 AWS 서비스 호출
        raw_items = await news_repo.fetch_news_by_date(symbol, from_dt, to_dt, min_importance=min_importance)


        if not raw_items:
            print("조회된 뉴스가 없습니다.")
            return []

        simplified_items = []
        for item in raw_items:
            raw_date = item.get('datetime')
            timestamp = int(raw_date)
            #날짜 변환 (추후 수정)
            date_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')

            impact = item.get('impact_score')
            if impact >=8 :
                content = item.get('content')
            else:
                content = item.get('summary', '내용없음')

            url = item.get('url')
            impact = str(impact)


            simplified_items.append({
                "date": date_str,
                "content": content,
                "url": url,
                "impact_score": impact
            })

        return simplified_items

    except Exception as e:
        print(f"⚠️ DB 조회 에러: {e}")
        return []

class SearchInput(BaseModel):
    query: str = Field(description="검색할 구체적인 질문 또는 키워드 (예: 'Reason for AAPL stock drop today')")


@tool(args_schema=SearchInput) # 실제 툴로 쓸 때는 주석 해제
async def search_market_issues(query: str) -> List[dict]:
    """DuckDuckGo를 통해 시장 이슈를 검색합니다."""

    print(f"🌐 [Tool] DuckDuckGo 검색 실행: '{query}'")

    try:
        from langchain_community.tools import DuckDuckGoSearchResults
        search = DuckDuckGoSearchResults(backend="news")
        # keywords: 검색어, region: 지역, safesearch: 'off', timelimit: 'd'(1일)/'w'(1주)/'m'(1달)
        results = search.invoke(query)
        print("⚠️ results: " , results)

        # 결과가 없으면 처리
        if not results:
            return [{"source": "DuckDuckGo", "content": "검색 결과가 없습니다."}]

            # 문자열 결과를 그대로 반환
        return [{
            "source": "DuckDuckGo News",
            "content": results
        }]

    except Exception as e:
        print(f"⚠️ 검색 실패: {e}")
        return [{"source": "System", "content": f"검색 중 에러 발생: {e}"}]


def render_html_report(symbol: str, data: StockReportSchema) -> str:
    """JSON 데이터를 받아 이메일 친화적인 HTML 코드로 변환 (Inline Style 적용 버전)"""

    # --- [Style Constants] CSS를 Python 변수로 관리 (유지보수 용이성) ---

    # 1. 컨테이너 & 레이아웃
    S_CONTAINER = "max-width: 600px; margin: 0 auto; background-color: #ffffff; border: 1px solid #e1e4e8; border-radius: 12px; font-family: -apple-system, BlinkMacSystemFont, 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; overflow: hidden;"
    S_BODY_PADDING = "padding: 24px;"

    # 2. 헤더 영역 (심플해진 디자인)
    S_HEADER_BOX = "padding: 24px 24px 20px 24px; border-bottom: 1px solid #f0f0f0; background-color: #ffffff;"
    S_SYMBOL_BOX = "display: inline-block; background-color: #2a5298; color: #ffffff; font-weight: 800; font-size: 14px; padding: 4px 10px; border-radius: 6px; margin-bottom: 8px;"
    S_DATE_TEXT = "float: right; color: #888; font-size: 12px; margin-top: 4px;"
    S_HEADLINE = "font-size: 20px; font-weight: 800; color: #111; line-height: 1.4; margin: 0 0 8px 0; letter-spacing: -0.5px;"
    S_METAPHOR = "font-size: 14px; color: #666; font-style: italic; margin: 0;"

    # 3. 섹션 공통
    S_SECTION_TITLE = "font-size: 15px; font-weight: 700; color: #2a5298; margin: 30px 0 12px 0; text-transform: uppercase; letter-spacing: 0.5px; border-left: 4px solid #2a5298; padding-left: 10px;"
    S_TEXT_BODY = "font-size: 15px; line-height: 1.7; color: #333; margin: 0; text-align: left;"  # 양쪽 정렬 제거

    # 4. 카드 디자인 (그림자 제거, 플랫하게)
    S_CARD = "background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 8px; padding: 16px; margin-bottom: 16px;"
    S_BADGE_BASE = "display: inline-block; font-size: 11px; font-weight: 800; padding: 3px 8px; border-radius: 4px; margin-right: 8px; color: #ffffff;"
    S_CARD_TITLE = "font-weight: 700; font-size: 15px; color: #222;"
    S_FACT_BOX = "font-size: 13px; color: #555; margin: 10px 0 8px 0; line-height: 1.5;"
    S_ANALYSIS_BOX = "font-size: 13px; color: #444; background-color: #ffffff; padding: 12px; border-radius: 6px; border: 1px solid #eee; line-height: 1.5;"

    # 5. 버튼 & 인사이트
    S_BTN_LINK = "display: inline-block; margin-top: 10px; font-size: 12px; font-weight: 600; color: #2a5298; text-decoration: none;"
    S_INSIGHT_BOX = "background-color: #e8f5e9; border: 1px solid #c8e6c9; border-radius: 8px; padding: 16px; color: #2e7d32; font-size: 14px; line-height: 1.6; font-weight: 500;"

    # 카테고리별 뱃지 색상 (배경색만 변경)
    color_map = {
        "호재": "#D32F2F",  # 빨강
        "악재": "#1976D2",  # 파랑
        "소송": "#F57C00",  # 주황
        "정보": "#388E3C",  # 초록
        "불확실": "#757575"  # 회색
    }

    current_date_str = datetime.now().strftime("%Y.%m.%d")

    # --- [Logic] 1. 이슈 카드 HTML 생성 ---
    issues_html = ""
    for issue in data.key_issues:
        badge_color = color_map.get(issue.category, "#546e7a")

        # 버튼 로직
        url_button = ""
        if issue.url and issue.url.strip():
            url_button = f"""
            <div style="text-align: right;">
                <a href="{issue.url}" target="_blank" style="{S_BTN_LINK}">
                    원문 보기 →
                </a>
            </div>
            """

        issues_html += f"""
        <div style="{S_CARD}">
            <div style="margin-bottom: 8px;">
                <span style="{S_BADGE_BASE} background-color: {badge_color};">{issue.category}</span>
                <span style="{S_CARD_TITLE}">{issue.title}</span>
            </div>

            <div style="{S_FACT_BOX}">
                <strong style="color:#000;">[Fact]</strong> {issue.fact}
            </div>
            <div style="{S_ANALYSIS_BOX}">
                <strong style="color:#2a5298;">[Analysis]</strong><br>
                {issue.analysis}
            </div>
            {url_button}
        </div>
        """

    # --- [Logic] 2. 전체 HTML 조립 (Inline Styles applied) ---
    # 주의: 여기서 <html>, <body> 태그는 넣지 않습니다 (Spring이 감싸줄 것이므로)

    final_html = f"""
    <div style="{S_CONTAINER}">

        <div style="{S_HEADER_BOX}">
            <div>
                <span style="{S_SYMBOL_BOX}">{symbol} Daily Brief</span>
                <span style="{S_DATE_TEXT}">{current_date_str}</span>
            </div>
            <div style="{S_HEADLINE}">{data.headline}</div>
            <div style="{S_METAPHOR}">"{data.metaphor}"</div>
        </div>

        <div style="{S_BODY_PADDING}">

            <div style="{S_SECTION_TITLE}">📊 심층 주가 분석</div>
            <p style="{S_TEXT_BODY}">
                {data.price_analysis}
            </p>

            <div style="{S_SECTION_TITLE}">🔥 주요 이슈 분석</div>
            {issues_html}

            <div style="{S_SECTION_TITLE}">💡 Stocky's Insight</div>
            <div style="{S_INSIGHT_BOX}">
                {data.insight}
            </div>

        </div>

        </div>
    """

    return final_html


#테스트
# import asyncio
# async def main():
#     # 주식 뉴스 조회 테스트
#     news_items = await fetch_db_news("AAPL", days_back=1, min_importance=5)
#     for news in news_items:
#         print(news.get("ai_summary"))
#
# if __name__ == "__main__":
#     asyncio.run(main())