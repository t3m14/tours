from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio

from app.config import settings
from app.api.v1 import tours, hotels, references, applications, sitemap
from app.api.websockets import websocket_manager
from app.tasks.cache_warmup import warm_up_cache
from app.tasks.random_tours_update import update_random_tours
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    logger.info("🚀 Запуск приложения...")
    
    logger.info("🔧 Запуск фоновых задач...")
    
    try:
        # Запуск задачи обновления случайных туров
        asyncio.create_task(update_random_tours())
        logger.info("✅ Задача обновления случайных туров запущена")
        
        # Прогрев кэша запускаем с задержкой, чтобы не перегружать API
        async def delayed_cache_warmup():
            await asyncio.sleep(300)  # 5 минут задержка
            await warm_up_cache()
        
        asyncio.create_task(delayed_cache_warmup())
        logger.info("✅ Задача прогрева кэша запущена (с задержкой)")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске фоновых задач: {e}")
    
    yield
    
    logger.info("🛑 Остановка приложения...")

app = FastAPI(
    title="Travel Agency Backend",
    description="Backend для турагентства с интеграцией TourVisor API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_HOSTS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(tours.router, prefix="/api/v1/tours", tags=["tours"])
app.include_router(hotels.router, prefix="/api/v1/hotels", tags=["hotels"])
app.include_router(references.router, prefix="/api/v1/references", tags=["references"])
app.include_router(applications.router, prefix="/api/v1/applications", tags=["applications"])
app.include_router(sitemap.router, prefix="/sitemap", tags=["sitemap"])

# WebSocket endpoint
@app.websocket("/ws/tours/{request_id}")
async def websocket_tours(websocket: WebSocket, request_id: str):
    await websocket_manager.connect(websocket, request_id)

@app.get("/")
async def root():
    return {"message": "Travel Agency Backend API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )