import time
import random
import requests
from bs4 import BeautifulSoup
from typing import List
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class FinvizStockCollector:
    """
    Finviz에서 시가총액 상위 심볼 크롤링(레이트 리밋 대응 포함)
    """
    def __init__(self, max_retries: int = 5, backoff_factor: float = 1.5):
        # requests.Session: 연결을 재사용해서 효율적으로 여러 요청을 보낼 수 있음
        self.session = requests.Session()
        self.BASE_URL = "https://finviz.com/screener.ashx?v=152&f=cap_largeover&o=-marketcap&r={}"

        # Retry 객체: HTTP 요청 실패 시 자동으로 재시도하는 정책 설정
        retry = Retry(
            total=max_retries,  # 최대 재시도 횟수
            backoff_factor=backoff_factor,  # 재시도 간격: 1.5초, 3초, 4.5초... (지수적 증가)
            status_forcelist=(429, 500, 502, 503, 504),  # 이 status code들이 오면 자동 재시도
            allowed_methods=frozenset(["GET"]),  # GET 요청만 재시도 허용
            raise_on_status=False,  # 에러 발생 시 예외를 던지지 않고 응답 객체 반환
        )

        # HTTPAdapter: Session에 재시도 정책을 적용하는 어댑터
        adapter = HTTPAdapter(max_retries=retry)
        # https:// 와 http:// 로 시작하는 모든 URL에 이 어댑터 적용
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        # HTTP 요청 헤더: 일반 브라우저처럼 보이게 위장 (봇 차단 우회)
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Referer": "https://finviz.com/",  # 어디서 왔는지 (finviz 내부에서 온 것처럼)
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",  # 캐시 사용 안함
        }
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def crawl_top_symbols(self, pages: int = 5, delay_range: tuple[float, float] = (1.5, 3.5)) -> List[str]:
        """
        여러 페이지를 순회하며 symbol 리스트를 수집
        - pages: 페이지 수(페이지당 20개)
        - delay_range: 각 요청 사이 랜덤 슬립 범위(초)
        """
        all_symbols: List[str] = []
        for page in range(pages):
            # offset 계산: 1페이지=1, 2페이지=21, 3페이지=41, ...
            offset = page * 20 + 1

            # 각 페이지에서 심볼들을 가져옴
            symbols = self._fetch_symbols_from_page(offset)
            all_symbols.extend(symbols)

            # 요청 간 랜덤 지연: 너무 빠르게 요청하면 봇으로 인식되어 차단됨
            # 1.5~3.5초 사이의 랜덤한 시간만큼 대기
            time.sleep(random.uniform(*delay_range))

        # 중복 제거 후 정렬: set()으로 중복 제거, sorted()로 알파벳 순 정렬
        return sorted(set(all_symbols))

    def _fetch_symbols_from_page(self, r: int) -> List[str]:
        """
        개별 페이지에서 symbol 추출(429 대응: 지수 백오프 재시도)

        429 에러 = "Too Many Requests": 서버가 짧은 시간에 너무 많은 요청을 받았다고 판단
        이 경우 점점 더 긴 시간을 기다렸다가 재시도 (지수 백오프)
        """
        url = self.BASE_URL.format(r)

        attempt = 0  # 시도 횟수
        while True:  # 성공하거나 최대 재시도 초과할 때까지 무한 반복
            attempt += 1

            # HTTP GET 요청 실행
            resp = self.session.get(url, headers=self.headers, timeout=15)
            status = resp.status_code

            # 성공 케이스: 200 OK
            if status == 200:
                # BeautifulSoup로 HTML 파싱
                soup = BeautifulSoup(resp.text, "html.parser")

                # CSS 선택자로 심볼 링크 찾기
                # "table.screener_table" 테이블 안의 "a.tab-link" 링크들
                elements = soup.select("table.screener_table a.tab-link")

                # 각 링크의 텍스트(심볼)를 추출, 공백 제거
                return [el.text.strip() for el in elements if el.text.strip()]

            # 실패 케이스: 429 (레이트 리밋) 에러이고 아직 재시도 횟수가 남았다면
            if status == 429 and attempt <= self.max_retries:
                # 지수 백오프: 1.5^1=1.5초, 1.5^2=2.25초, 1.5^3=3.375초, ...
                # + 지터(jitter): 0.2~0.8초 랜덤 추가 (모든 클라이언트가 동시에 재시도하는 것 방지)
                sleep_sec = (self.backoff_factor ** attempt) + random.uniform(0.2, 0.8)
                print(f"429 에러 발생, {sleep_sec:.2f}초 대기 후 재시도 ({attempt}/{self.max_retries})")
                time.sleep(sleep_sec)
                continue  # while 루프 처음으로 돌아가서 재시도

            # 기타 에러 (400, 500 등) 또는 재시도 횟수 초과
            # raise_for_status(): 에러 상태 코드면 예외 발생
            resp.raise_for_status()

crawler = FinvizStockCollector()
    # 45페이지 = 900개의 심볼 수집 (페이지당 20개)
    # 주의: 많은 페이지를 크롤링하면 시간이 오래 걸림 (페이지당 2~3초 대기)
top_symbols = crawler.crawl_top_symbols(pages=5)
print(f"총 {len(top_symbols)}개 심볼 수집:")
print(top_symbols)