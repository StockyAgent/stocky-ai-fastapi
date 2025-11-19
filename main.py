from fastapi import FastAPI
from app.routers import stock
import uvicorn

app = FastAPI(
    title="Stock Analysis API",
    description="FastAPI + DynamoDB (Local) S"
)

# 3.2에서 만든 라우터를 앱에 포함시킵니다.
app.include_router(stock.router, prefix="/api/v1", tags=["Stock"])

@app.get("/")
def read_root():
    print("Hello World")
    return {"Hello": "World"}
    return {"message": "Welcome to Stock API"}

if __name__ == "__main__":
    # uvicorn.run(app, host="0.0.0.0", port=8080)
    import yfinance as yf
    apple = yf.Ticker("AAPL")
    print(apple.info)
