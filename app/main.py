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
    
    # Запуск фоновых задач
    logger.info("🔧 Запуск фоновых задач...")
    
    # Задача обновления случайных туров (быстрая)
    random_tours_task = asyncio.create_task(update_random_tours())
    logger.info("✅ Задача обновления случайных туров запущена")
    
    # Задача прогрева кэша (медленная, запускаем с задержкой)
    async def delayed_cache_warmup():
        await asyncio.sleep(30)  # Ждем 30 секунд после старта
        await warm_up_cache()
    
    cache_warmup_task = asyncio.create_task(delayed_cache_warmup())
    logger.info("✅ Задача прогрева кэша запущена (с задержкой)")
    
    yield
    
    logger.info("🛑 Остановка приложения...")
    
    # Отменяем фоновые задачи
    random_tours_task.cancel()
    cache_warmup_task.cancel()
    
    try:
        await random_tours_task
    except asyncio.CancelledError:
        logger.info("❌ Задача случайных туров отменена")
    
    try:
        await cache_warmup_task
    except asyncio.CancelledError:
        logger.info("❌ Задача прогрева кэша отменена")

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
    return {
        "message": "Travel Agency Backend API", 
        "version": "1.0.0",
        "status": "running",
        "features": [
            "tour_search",
            "random_tours", 
            "hotel_info",
            "references",
            "applications",
            "websocket_support",
            "sitemap_generation"
        ]
    }

@app.get("/health")
async def health_check():
    """Проверка здоровья приложения"""
    try:
        # Проверяем кэш
        from app.services.cache_service import cache_service
        cache_working = await cache_service.exists("health_check")
        await cache_service.set("health_check", "ok", ttl=60)
        
        # Проверяем TourVisor API (легкий запрос)
        from app.core.tourvisor_client import tourvisor_client
        api_working = False
        try:
            references = await tourvisor_client.get_references("departure")
            api_working = bool(references)
        except:
            api_working = False
        
        return {
            "status": "healthy",
            "timestamp": asyncio.get_event_loop().time(),
            "components": {
                "cache": "ok" if cache_working else "error",
                "tourvisor_api": "ok" if api_working else "error"
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка health check: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

@app.get("/status")
async def get_system_status():
    """Расширенная информация о состоянии системы"""
    try:
        from app.services.cache_service import cache_service
        
        # Проверяем различные кэши
        caches_status = {}
        cache_keys = [
            "random_tours_from_search",
            "reference:departure", 
            "reference:country",
            "hot_tours:city_1"
        ]
        
        for key in cache_keys:
            exists = await cache_service.exists(key)
            caches_status[key] = "present" if exists else "missing"
        
        return {
            "system": "travel_agency_backend",
            "version": "1.0.0",
            "uptime_info": "running",
            "cache_status": caches_status,
            "endpoints": {
                "tours": "/api/v1/tours/",
                "hotels": "/api/v1/hotels/",
                "references": "/api/v1/references/",
                "applications": "/api/v1/applications/",
                "sitemap": "/sitemap",
                "websocket": "/ws/tours/{request_id}"
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения статуса: {e}")
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )