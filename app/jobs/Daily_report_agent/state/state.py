from typing import TypedDict, List, Optional, Annotated, Literal
import operator

from pydantic import BaseModel, Field


#데이터 스키마
class IssueItem(BaseModel):
    """개별 뉴스 이슈 항목"""
    # LLM이 이 5가지만 선택하도록 제한
    category: Literal["호재", "악재", "정보", "소송", "불확실"] = Field(
        description="이슈의 성격을 판단하여 선택. 긍정적이면 '호재', 부정적이면 '악재', 단순 사실은 '정보', 법적 분쟁은 '소송'"
    )
    title: str = Field(description="이슈의 핵심 제목 (한국어로 작성)")
    fact: str = Field(description="[Fact] 객관적인 사실 내용 (한국어로 작성, 1~2문장)")
    analysis: str = Field(description="[Analysis] 주가 영향 및 해석 (한국어로 작성, 2~3문장)")
    url:str = Field(description="이슈 관련 출처 뉴스 URL")


class StockReportSchema(BaseModel):
    """전체 리포트 구조"""
    headline: str = Field(description="주식 상황을 빗댄 강렬한 비유적 헤드라인 (한국어)")
    metaphor: str = Field(description="헤드라인을 뒷받침하는 구체적인 상황 묘사 (한국어)")
    price_analysis: str = Field(description="주가 흐름에 대한 심층 분석 (한국어)")
    key_issues: List[IssueItem] = Field(description="가장 중요한 이슈 리스트 (최소 3개, 호재와 악재를 균형 있게 포함할 것)")
    insight: str = Field(description="투자자를 위한 구체적인 대응 전략 (한국어)")




class ReportState(TypedDict):
    # 1. 초기 입력
    symbol: str

    #투자 성향 페르소나
    investment_type: Literal["trader", "investor"]

    # 2. 수집된 데이터 (계속 누적됨)
    news_data: List[dict]  # DynamoDB + WebSearch 결과
    price_data: str # 시가, 종가, 등락률 등

    # 3. 판단 플래그
    is_data_sufficient: bool  # 정보 검수관의 판단 결과
    search_keyword: str  # "주가 하락 원인 불명" 등

    draft: Optional[StockReportSchema]

    feedback: Optional[str]
    is_pass: Optional[bool]
    is_hallucination: Optional[bool]

    # 4. 작성 및 검수
    # draft_report: str  # Writer가 쓴 초안
    # critique_feedback: str  # 검수관의 지적사항
    # revision_count: int  # 수정 횟수 (무한루프 방지)

