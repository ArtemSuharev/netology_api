import uvicorn
from dotenv import load_dotenv
from config.logging_config import setup_logging

# ─── Загрузка переменных из .env ───
load_dotenv()

# ─── Настройка структурированного JSON-логирования ───
setup_logging(level="INFO")

# ─── Создаём FastAPI приложение ───
from api.app import app
from api.routes import router

app.include_router(router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
