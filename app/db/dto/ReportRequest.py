from typing import Literal

from pydantic import BaseModel


class ReportRequest(BaseModel):
    symbol: str
    investment_type: Literal["trader", "investor"]

class ManySymbolReportRequest(BaseModel):
    symbols: list[str]