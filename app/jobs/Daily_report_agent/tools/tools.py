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
    """JSON 데이터를 받아 HTML 코드로 변환 (UI/UX 강화 버전)"""
    current_date = datetime.now().strftime("%Y-%m-%d")

    # 카테고리별 색상 매핑
    color_map = {
        "호재": "#D32F2F",  # 빨강
        "악재": "#1976D2",  # 파랑
        "소송": "#F57C00",  # 주황
        "정보": "#388E3C",  # 초록
        "불확실": "#757575"  # 회색
    }

    # 1. 이슈 카드 HTML 생성
    issues_html = ""
    for issue in data.key_issues:
        badge_bg = color_map.get(issue.category, "#546e7a")

        # [수정 포인트] URL이 있을 때만 버튼 생성
        url_button = ""
        if issue.url and issue.url.strip():
            url_button = f"""
            <div class="link-container">
                <a href="{issue.url}" target="_blank" class="btn-read-more">
                    원문 전체보기 <span class="arrow">→</span>
                </a>
            </div>
            """

        issues_html += f"""
        <div class="issue-card">
            <div class="issue-header">
                <span class="badge" style="background-color: {badge_bg};">{issue.category}</span>
                <span class="issue-title-text">{issue.title}</span>
            </div>
            <div class="issue-body">
                <div class="fact-box">
                    <strong>[Fact]</strong> 
                    {issue.fact}
                </div>
                <div class="analysis-box">
                    <strong>[Analysis]</strong> 
                    {issue.analysis}
                </div>
                {url_button}
            </div>
        </div>
        """

    # 2. 전체 HTML 조립 (CSS 대폭 강화)
    html_template = f"""
    <div class="report-container">
        <style>
            /* 기본 설정 */
            .report-container {{ font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Pretendard", sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; border-radius: 20px; overflow: hidden; background: #ffffff; box-shadow: 0 10px 30px rgba(0,0,0,0.12); border: 1px solid #eaeaea; }}

            /* 헤더 디자인 */
            .header {{ background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); padding: 35px 25px; color: white; position: relative; }}
            .symbol-tag {{ background: rgba(255,255,255,0.15); padding: 5px 12px; border-radius: 30px; font-size: 0.8rem; font-weight: 700; margin-bottom: 12px; display: inline-block; letter-spacing: 0.5px; backdrop-filter: blur(5px); border: 1px solid rgba(255,255,255,0.2); }}
            .headline {{ font-size: 1.7rem; font-weight: 800; margin-bottom: 8px; line-height: 1.35; letter-spacing: -0.5px; text-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            .metaphor {{ font-style: italic; opacity: 0.9; font-size: 1rem; font-weight: 300; margin-top: 5px; }}

            /* 섹션 타이틀 */
            .section-title {{ font-size: 1.25rem; font-weight: 800; margin: 35px 25px 15px; display: flex; align-items: center; color: #1a1a1a; letter-spacing: -0.3px; }}
            .section-title::before {{ content: ''; display: inline-block; width: 6px; height: 24px; background: #2a5298; margin-right: 10px; border-radius: 3px; }}

            /* 본문 박스 */
            .content-box {{ padding: 0 25px; color: #444; font-size: 0.98rem; text-align: justify; line-height: 1.7; letter-spacing: -0.2px; }}

            /* 이슈 카드 디자인 (핵심) */
            .issue-card {{ background: #ffffff; margin: 0 20px 24px; border-radius: 16px; border: 1px solid #f0f0f0; box-shadow: 0 4px 12px rgba(0,0,0,0.03); transition: transform 0.2s ease; overflow: hidden; }}
            .issue-card:hover {{ transform: translateY(-2px); box-shadow: 0 8px 16px rgba(0,0,0,0.06); }}

            .issue-header {{ padding: 16px 20px; background: #fafafa; border-bottom: 1px solid #eee; display: flex; align-items: start; }}
            .badge {{ padding: 4px 8px; border-radius: 6px; color: white; font-size: 0.7rem; margin-right: 10px; font-weight: 700; white-space: nowrap; margin-top: 3px; }}
            .issue-title-text {{ font-weight: 700; font-size: 1.05rem; color: #333; line-height: 1.4; }}

            .issue-body {{ padding: 20px; }}
            .fact-box {{ margin-bottom: 12px; color: #555; font-size: 0.95rem; }}
            .analysis-box {{ color: #444; font-size: 0.95rem; background: #f8faff; padding: 12px; border-radius: 8px; border-left: 3px solid #2a5298; }}

            /* 버튼 디자인 (Call To Action) */
            .link-container {{ text-align: right; margin-top: 15px; }}
            .btn-read-more {{ 
                display: inline-flex; align-items: center; justify-content: center;
                padding: 8px 16px; 
                background-color: #ffffff; 
                color: #555; 
                border: 1px solid #ddd; 
                border-radius: 50px; 
                text-decoration: none; 
                font-size: 0.85rem; 
                font-weight: 600; 
                transition: all 0.2s ease; 
            }}
            .btn-read-more:hover {{ 
                background-color: #2a5298; 
                color: #ffffff; 
                border-color: #2a5298; 
                box-shadow: 0 2px 8px rgba(42, 82, 152, 0.25);
            }}
            .arrow {{ margin-left: 6px; transition: transform 0.2s; }}
            .btn-read-more:hover .arrow {{ transform: translateX(3px); }}

            /* 인사이트 & 푸터 */
            .insight-box {{ background: linear-gradient(to right, #e8f5e9, #f1f8e9); margin: 20px 25px; padding: 20px; border-radius: 12px; color: #2e7d32; border: 1px solid #c8e6c9; font-weight: 500; font-size: 0.95rem; line-height: 1.7; }}
            .footer {{ text-align: center; font-size: 0.75rem; color: #aaa; padding: 25px; border-top: 1px solid #f0f0f0; background: #fafafa; letter-spacing: 0.5px; }}
            strong {{ color: #222; font-weight: 700; }}
        </style>

        <div class="header">
            <div class="symbol-tag">{symbol} Daily Brief</div>
            <div class="headline">{data.headline}</div>
            <div class="metaphor">"{data.metaphor}"</div>
        </div>

        <div class="section-title">📊 심층 주가 분석</div>
        <div class="content-box">
            {data.price_analysis}
        </div>

        <div class="section-title">🔥 주요 이슈 분석 (Top Picks)</div>
        {issues_html}

        <div class="section-title">💡 Stocky's Insight</div>
        <div class="insight-box">
            {data.insight}
        </div>

        <div class="footer">
            Generated by Stocky AI • {current_date}
        </div>
    </div>
    """
    return html_template



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