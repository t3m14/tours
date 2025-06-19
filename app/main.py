# app/main.py

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio

from app.config import settings
from app.api.v1 import tours, hotels, references, applications, sitemap
from app.api.websockets import websocket_manager
from app.tasks.cache_warmup import warm_up_cache
from app.tasks.random_tours_update import update_random_tours
from app.tasks.mass_directions_update import periodic_directions_update, initial_directions_collection
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    logger.info("🚀 Запуск приложения...")
    
    logger.info("🔧 Запуск фоновых задач...")
    
    try:
        # 1. Первоначальный сбор направлений (если необходимо)
        logger.info("🌍 Запуск первоначального сбора направлений...")
        asyncio.create_task(initial_directions_collection())
        
        # 2. Задача обновления случайных туров
        logger.info("🎲 Запуск задачи обновления случайных туров...")
        asyncio.create_task(update_random_tours())
        
        # 3. Периодическое обновление направлений (долгосрочная задача)
        logger.info("🔄 Запуск периодического обновления направлений...")
        asyncio.create_task(periodic_directions_update())
        
        # 4. Прогрев кэша запускаем с задержкой, чтобы не перегружать API
        async def delayed_cache_warmup():
            await asyncio.sleep(600)  # 10 минут задержка
            await warm_up_cache()
        
        logger.info("🔥 Запуск прогрева кэша (с задержкой)...")
        asyncio.create_task(delayed_cache_warmup())
        
        logger.info("✅ Все фоновые задачи запущены успешно")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске фоновых задач: {e}")
    
    yield
    
    logger.info("🛑 Остановка приложения...")

app = FastAPI(
    title="Travel Agency Backend",
    description="Backend для турагентства с интеграцией TourVisor API и массовым сбором направлений",
    version="2.0.0",
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
        "version": "2.0.0",
        "features": [
            "Массовый сбор направлений из всех стран",
            "Долгосрочное кэширование (30 дней)",
            "Автоматическое обновление направлений",
            "Real-time поиск туров через WebSocket",
            "Случайные туры с фильтрацией",
            "Система заявок с email уведомлениями"
        ]
    }

@app.get("/health")
async def health_check():
    """Расширенная проверка здоровья системы"""
    try:
        from app.services.mass_directions_collector import mass_directions_collector
        from app.services.cache_service import cache_service
        
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "components": {}
        }
        
        # Проверяем кэш
        try:
            await cache_service.set("health_check", "test", ttl=60)
            test_value = await cache_service.get("health_check")
            await cache_service.delete("health_check")
            
            health_status["components"]["cache"] = {
                "status": "healthy" if test_value == "test" else "degraded"
            }
        except Exception as e:
            health_status["components"]["cache"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Проверяем состояние направлений
        try:
            directions_status = await mass_directions_collector.get_collection_status()
            master_cache = directions_status.get("master_cache", {})
            
            health_status["components"]["directions"] = {
                "status": "healthy" if master_cache.get("exists") else "needs_initialization",
                "directions_count": master_cache.get("directions_count", 0),
                "last_collection": master_cache.get("last_collection")
            }
        except Exception as e:
            health_status["components"]["directions"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Определяем общий статус
        component_statuses = [comp["status"] for comp in health_status["components"].values()]
        if all(s in ["healthy", "needs_initialization"] for s in component_statuses):
            health_status["status"] = "healthy"
        elif any(s == "unhealthy" for s in component_statuses):
            health_status["status"] = "unhealthy"
        else:
            health_status["status"] = "degraded"
        
        return health_status
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.get("/system-info")
async def get_system_info():
    """Информация о системе и её возможностях"""
    return {
        "application": {
            "name": "Travel Agency Backend",
            "version": "2.0.0",
            "description": "Backend для турагентства с массовым сбором направлений"
        },
        "features": {
            "mass_directions_collection": {
                "description": "Массовый сбор направлений из всех доступных стран",
                "cache_duration": "30 дней",
                "automatic_updates": True,
                "real_photos": True,
                "price_calculation": True
            },
            "random_tours": {
                "description": "Генерация случайных туров с фильтрацией",
                "hotel_type_filtering": True,
                "multiple_strategies": ["hot_tours", "search", "mock"]
            },
            "real_time_search": {
                "description": "Real-time поиск туров через WebSocket",
                "progress_tracking": True,
                "continue_search": True
            },
            "applications_system": {
                "description": "Система приема и обработки заявок",
                "email_notifications": True,
                "storage_duration": "30 дней"
            }
        },
        "endpoints": {
            "directions": {
                "get": "/api/v1/tours/directions",
                "collect_all": "/api/v1/tours/directions/collect-all",
                "status": "/api/v1/tours/directions/status",
                "refresh": "/api/v1/tours/directions/refresh"
            },
            "random_tours": {
                "get": "/api/v1/tours/random",
                "post": "/api/v1/tours/random",
                "generate": "/api/v1/tours/random/generate"
            },
            "search": {
                "start": "/api/v1/tours/search",
                "status": "/api/v1/tours/search/{id}/status",
                "results": "/api/v1/tours/search/{id}/results",
                "websocket": "/ws/tours/{id}"
            }
        },
        "background_tasks": {
            "directions_update": "Ежедневная проверка и обновление направлений",
            "random_tours_update": "Ежедневное обновление случайных туров", 
            "cache_warmup": "Периодический прогрев кэша"
        }
    }

if __name__ == "__main__":
    import uvicorn
    from datetime import datetime
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )