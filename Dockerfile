# 1. 파이썬 3.10 버전으로 시작
FROM python:3.10-slim

# 2. 작업 폴더 설정
WORKDIR /app

# 3. 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 소스 코드 전체 복사
COPY . .

# 5. (기본값) 아무 명령도 안 주면 그냥 API 서버 실행
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]