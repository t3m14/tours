# app/main.py - ИСПРАВЛЕННАЯ ВЕРСИЯ

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
from datetime import datetime

from app.config import settings
from app.api.v1 import tours, hotels, references, applications, sitemap
from app.api.websockets import websocket_manager
from app.tasks.cache_warmup import warm_up_cache
from app.tasks.random_tours_update import update_random_tours
from app.tasks.mass_directions_update import periodic_directions_update, initial_directions_collection
# Импорт автообновления кэша направлений
from app.tasks.directions_cache_update import start_directions_cache_update_task, stop_directions_cache_update_task
# НОВОЕ: Импорт автообновления кэша случайных туров
from app.tasks.random_tours_cache_update import start_random_tours_cache_update_task, stop_random_tours_cache_update_task
from app.utils.logger import setup_logger
from fastapi.staticfiles import StaticFiles
import os


logger = setup_logger(__name__)

# Глобальные переменные для задач
directions_cache_task = None
random_tours_cache_task = None
random_tours_task = None
mass_directions_task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    logger.info("🚀 Запуск приложения...")
    
    logger.info("🔧 Запуск фоновых задач...")
    
    # Глобальные переменные для управления задачами
    global directions_cache_task, random_tours_cache_task, random_tours_task, mass_directions_task
    
    try:
        # 1. Первоначальный сбор направлений (если необходимо)
        logger.info("🌍 Запуск первоначального сбора направлений...")
        asyncio.create_task(initial_directions_collection())
        
        # 2. Старая задача обновления случайных туров (оставляем для совместимости)
        logger.info("🎲 Запуск задачи обновления случайных туров (совместимость)...")
        random_tours_task = asyncio.create_task(update_random_tours())
        
        # 3. Периодическое обновление направлений (долгосрочная задача)
        logger.info("🔄 Запуск периодического обновления направлений...")
        mass_directions_task = asyncio.create_task(periodic_directions_update())
        
        # 4. Автообновление кэша направлений
        logger.info("📅 Запуск автообновления кэша направлений...")
        try:
            directions_cache_task = asyncio.create_task(start_directions_cache_update_task())
            logger.info("✅ Задача автообновления кэша направлений запущена")
        except Exception as e:
            logger.error(f"❌ Ошибка запуска автообновления кэша направлений: {e}")
        
        # 5. НОВОЕ: Автообновление кэша случайных туров
        logger.info("🎲 Запуск автообновления кэша случайных туров...")
        try:
            random_tours_cache_task = asyncio.create_task(start_random_tours_cache_update_task())
            logger.info("✅ Задача автообновления кэша случайных туров запущена")
        except Exception as e:
            logger.error(f"❌ Ошибка запуска автообновления кэша случайных туров: {e}")
        
        # 6. Прогрев кэша запускаем с задержкой, чтобы не перегружать API
        async def delayed_cache_warmup():
            await asyncio.sleep(600)  # 10 минут задержка
            await warm_up_cache()
        
        logger.info("🔥 Запуск прогрева кэша (с задержкой)...")
        asyncio.create_task(delayed_cache_warmup())
        
        logger.info("✅ Все фоновые задачи запущены успешно")
        
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске фоновых задач: {e}")
    
    yield
    
    # Shutdown - остановка всех задач
    logger.info("🛑 Остановка приложения...")
    
    # Остановка задачи автообновления кэша направлений
    if directions_cache_task:
        try:
            logger.info("📅 Остановка задачи автообновления кэша направлений...")
            await stop_directions_cache_update_task()
            directions_cache_task.cancel()
            try:
                await directions_cache_task
            except asyncio.CancelledError:
                logger.info("✅ Задача автообновления кэша направлений остановлена")
        except Exception as e:
            logger.error(f"❌ Ошибка остановки автообновления кэша направлений: {e}")
    
    # НОВОЕ: Остановка задачи автообновления кэша случайных туров
    if random_tours_cache_task:
        try:
            logger.info("🎲 Остановка задачи автообновления кэша случайных туров...")
            await stop_random_tours_cache_update_task()
            random_tours_cache_task.cancel()
            try:
                await random_tours_cache_task
            except asyncio.CancelledError:
                logger.info("✅ Задача автообновления кэша случайных туров остановлена")
        except Exception as e:
            logger.error(f"❌ Ошибка остановки автообновления кэша случайных туров: {e}")
    
    # Остановка других задач
    for task_name, task in [
        ("random_tours", random_tours_task),
        ("mass_directions", mass_directions_task)
    ]:
        if task and not task.done():
            try:
                logger.info(f"🛑 Остановка задачи {task_name}...")
                task.cancel()
                await task
            except asyncio.CancelledError:
                logger.info(f"✅ Задача {task_name} остановлена")
            except Exception as e:
                logger.error(f"❌ Ошибка остановки задачи {task_name}: {e}")
    
    logger.info("✅ Приложение остановлено")

app = FastAPI(
    title="Travel Agency Backend",
    description="Backend для турагентства с полным автообновлением кэша направлений и случайных туров",
    version="2.2.0",
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

# Подключение роутера направлений
from app.api.v1.directions import router as directions_router
app.include_router(
    directions_router, 
    prefix="/api/v1/directions", 
    tags=["Directions - Новый сервис направлений"]
)

# Подключение API управления кэшем направлений
from app.api.v1.directions_cache import router as directions_cache_router
app.include_router(
    directions_cache_router,
    prefix="/api/v1",
    tags=["Directions Cache Management"]
)

# НОВОЕ: Подключение API управления кэшем случайных туров
from app.api.v1.random_tours_cache import router as random_tours_cache_router
app.include_router(
    random_tours_cache_router,
    prefix="/api/v1",
    tags=["Random Tours Cache Management"]
)

# WebSocket endpoint
@app.websocket("/ws/tours/{request_id}")
async def websocket_tours(websocket: WebSocket, request_id: str):
    await websocket_manager.connect(websocket, request_id)

# ИСПРАВЛЕНО: Используем @app.get вместо @router.get
@app.get("/")
async def root():
    return {
        "message": "Travel Agency Backend API", 
        "version": "2.2.0",
        "features": [
            "Массовый сбор направлений из всех стран",
            "Автоматическое обновление кэша направлений каждые 24 часа",
            "Автоматическое обновление кэша случайных туров каждые 12 часов с hoteltypes фильтрацией",
            "Долгосрочное кэширование (30 дней)",
            "Автоматическое обновление направлений",
            "Real-time поиск туров через WebSocket",
            "Случайные туры с фильтрацией по типам отелей через TourVisor API",
            "Система заявок с email уведомлениями",
            "API управления всеми видами кэша"
        ],
        "cache_management": {
            "directions": {
                "auto_update": "каждые 24 часа",
                "status": "/api/v1/directions/cache/status",
                "force_update": "/api/v1/directions/cache/force-update",
                "health_check": "/api/v1/directions/cache/health"
            },
            "random_tours": {
                "auto_update": "каждые 12 часов", 
                "status": "/api/v1/random-tours/cache/status",
                "force_update": "/api/v1/random-tours/cache/force-update",
                "health_check": "/api/v1/random-tours/cache/health",
                "hotel_types": "/api/v1/random-tours/cache/hotel-types",
                "api_integration": "TourVisor hoteltypes фильтрация"
            }
        }
    }

@app.get("/health")
async def health_check():
    """Расширенная проверка здоровья системы с обеими системами кэширования"""
    try:
        from app.services.mass_directions_collector import mass_directions_collector
        from app.services.cache_service import cache_service
        from app.tasks.directions_cache_update import directions_cache_update_service
        # НОВОЕ: Импорт сервиса автообновления случайных туров
        from app.tasks.random_tours_cache_update import random_tours_cache_update_service
        
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
        
        # Проверяем состояние автообновления кэша направлений
        try:
            directions_cache_status = await directions_cache_update_service.get_update_status()
            
            health_status["components"]["directions_cache_auto_update"] = {
                "status": "running" if directions_cache_status.get("is_running") else "stopped",
                "last_update": directions_cache_status.get("last_update"),
                "scheduler_running": directions_cache_status.get("is_running", False)
            }
        except Exception as e:
            health_status["components"]["directions_cache_auto_update"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # НОВОЕ: Проверяем состояние автообновления кэша случайных туров
        try:
            random_tours_cache_status = await random_tours_cache_update_service.get_update_status()
            
            health_status["components"]["random_tours_cache_auto_update"] = {
                "status": "running" if random_tours_cache_status.get("is_running") else "stopped",
                "last_update": random_tours_cache_status.get("last_update"),
                "current_hotel_type": random_tours_cache_status.get("current_hotel_type"),
                "scheduler_running": random_tours_cache_status.get("is_running", False),
                "supported_hotel_types": len(random_tours_cache_status.get("hotel_types_supported", []))
            }
        except Exception as e:
            health_status["components"]["random_tours_cache_auto_update"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Определяем общий статус
        component_statuses = [comp["status"] for comp in health_status["components"].values()]
        if all(s in ["healthy", "needs_initialization", "running"] for s in component_statuses):
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
            "version": "2.2.0",
            "description": "Backend для турагентства с полным автообновлением кэша направлений и случайных туров"
        },
        "features": {
            "mass_directions_collection": {
                "description": "Массовый сбор направлений из всех доступных стран",
                "cache_duration": "30 дней",
                "automatic_updates": True,
                "real_photos": True,
                "price_calculation": True
            },
            "auto_directions_cache": {
                "description": "Автоматическое обновление кэша направлений каждые 24 часа",
                "interval": "24 часа",
                "batch_processing": True,
                "quality_control": True,
                "retry_mechanism": True,
                "api_management": True,
                "monitoring": True
            },
            "auto_random_tours_cache": {
                "description": "Автоматическое обновление кэша случайных туров с hoteltypes фильтрацией",
                "interval": "12 часов",
                "hotel_types": ["любой", "активный", "релакс", "семейный", "оздоровительный", "городской", "пляжный", "делюкс"],
                "api_integration": "TourVisor hoteltypes поле",
                "tours_per_type": 8,
                "generation_strategies": ["search", "hot_tours", "mock"],
                "quality_tracking": True,
                "api_management": True
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
                "refresh": "/api/v1/tours/directions/refresh",
                "new_service": {
                    "by_country": "/api/v1/directions/country/{country_id}",
                    "flat_format": "/api/v1/directions/country/{country_id}/flat",
                    "quick_mode": "/api/v1/directions/country/{country_id}/quick",
                    "countries_list": "/api/v1/directions/countries/list"
                }
            },
            "cache_management": {
                "directions": {
                    "status": "/api/v1/directions/cache/status",
                    "detailed_stats": "/api/v1/directions/cache/stats",
                    "health_check": "/api/v1/directions/cache/health",
                    "force_update": "/api/v1/directions/cache/force-update",
                    "scheduler": {
                        "start": "/api/v1/directions/cache/scheduler/start",
                        "stop": "/api/v1/directions/cache/scheduler/stop"
                    }
                },
                "random_tours": {
                    "status": "/api/v1/random-tours/cache/status",
                    "detailed_stats": "/api/v1/random-tours/cache/stats", 
                    "health_check": "/api/v1/random-tours/cache/health",
                    "force_update": "/api/v1/random-tours/cache/force-update",
                    "clear_cache": "/api/v1/random-tours/cache/clear",
                    "hotel_types": "/api/v1/random-tours/cache/hotel-types",
                    "generate_specific": "/api/v1/random-tours/cache/generate/{hotel_type}",
                    "preview": "/api/v1/random-tours/cache/preview/{hotel_type}",
                    "compare_strategies": "/api/v1/random-tours/cache/compare-strategies/{hotel_type}",
                    "scheduler": {
                        "start": "/api/v1/random-tours/cache/scheduler/start",
                        "stop": "/api/v1/random-tours/cache/scheduler/stop"
                    }
                }
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
            "directions_auto_cache": "Автоматическое обновление кэша направлений каждые 24 часа",
            "random_tours_auto_cache": "Автоматическое обновление кэша случайных туров каждые 12 часов с hoteltypes API",
            "directions_update": "Ежедневная проверка и обновление направлений", 
            "random_tours_update": "Ежедневное обновление случайных туров (совместимость)", 
            "cache_warmup": "Периодический прогрев кэша"
        },
        "configuration": {
            "directions_cache": {
                "update_interval": "24 часа (CACHE_UPDATE_INTERVAL_HOURS)",
                "batch_size": "3 страны (CACHE_UPDATE_BATCH_SIZE)",
                "search_timeout": "120 секунд (CACHE_SEARCH_TIMEOUT)",
                "auto_start": "Включен (CACHE_AUTO_START)"
            },
            "random_tours_cache": {
                "update_interval": "12 часов (RANDOM_TOURS_UPDATE_INTERVAL_HOURS)",
                "tours_per_type": "8 туров (RANDOM_TOURS_PER_TYPE)",
                "strategies": "search,hot_tours,mock (RANDOM_TOURS_STRATEGIES)",
                "countries": "1,2,4,9,8 (RANDOM_TOURS_COUNTRIES)",
                "hotel_types": "8 типов с hoteltypes API фильтрацией",
                "auto_start": "Включен (RANDOM_TOURS_AUTO_START)"
            }
        }
    }

# Статические файлы
static_path = os.path.join(os.path.dirname(__file__), "services", "mockup_images")
if os.path.exists(static_path):
    app.mount("/static/mockup_images", StaticFiles(directory=static_path), name="mockup_images")
    logger.info(f"📁 Статические файлы mockup_images подключены: {static_path}")
else:
    logger.warning(f"⚠️ Папка с картинками не найдена: {static_path}")
    # Создаем папку если её нет
    os.makedirs(static_path, exist_ok=True)
    logger.info(f"📁 Создана папка для картинок: {static_path}")

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )