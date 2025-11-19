from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 환경 구분
    APP_ENV: str = "development"

    #Finnhub API Key
    FINNHUB_API_KEY: str

    #OpenAI API Key
    OPENAI_API_KEY: str

    # --- 2. 로컬 개발용 DynamoDB 설정 ---
    # APP_ENV가 "development"일 때만 사용될 주소입니다.
    # 우리가 Docker에서 8000번 포트로 열었기 때문입니다.
    DYNAMODB_ENDPOINT_URL: Optional[str] = "http://localhost:8000"

    #AWS 설정
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str = "ap-northeast-2"

    # 이 모든 정보들을 ".env"에서 가져옴
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
