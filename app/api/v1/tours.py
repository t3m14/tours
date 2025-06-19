from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
import asyncio
import random
from datetime import datetime, timedelta

from app.models.tour import (
    TourSearchRequest, SearchResponse, SearchResult, SearchStatus,
    RandomTourRequest, HotTourInfo, DirectionInfo, TourActualizationRequest,
    DetailedTourInfo, HotelInfo
)
from app.services.tour_service import tour_service
from app.services.random_tours_service import random_tours_service
from app.services.directions_service import directions_service
from app.services.photo_service import photo_service
from app.services.price_service import price_service
from app.core.tourvisor_client import tourvisor_client
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()

# ========== ОСНОВНЫЕ ENDPOINTS ПОИСКА ТУРОВ ==========

@router.post("/search", response_model=SearchResponse)
async def search_tours(search_request: TourSearchRequest):
    """
    Запуск поиска туров
    
    Возвращает request_id для отслеживания статуса поиска
    """
    try:
        return await tour_service.search_tours(search_request)
    except Exception as e:
        logger.error(f"Ошибка при поиске туров: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search/{request_id}/status", response_model=SearchStatus)
async def get_search_status(request_id: str):
    """
    Получение статуса поиска туров
    """
    try:
        return await tour_service.get_search_status(request_id)
    except Exception as e:
        logger.error(f"Ошибка при получении статуса: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search/{request_id}/results", response_model=SearchResult)
async def get_search_results(
    request_id: str,
    page: int = Query(1, ge=1, description="Номер страницы"),
    onpage: int = Query(25, ge=1, le=100, description="Количество результатов на странице")
):
    """
    Получение результатов поиска туров
    """
    try:
        return await tour_service.get_search_results(request_id, page, onpage)
    except Exception as e:
        logger.error(f"Ошибка при получении результатов: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/search/{request_id}/continue")
async def continue_search(request_id: str):
    """
    Продолжение поиска для получения большего количества результатов
    """
    try:
        return await tour_service.continue_search(request_id)
    except Exception as e:
        logger.error(f"Ошибка при продолжении поиска: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== ПОЛНОСТЬЮ РАНДОМНЫЕ ТУРЫ С ФИЛЬТРАЦИЕЙ ==========

@router.get("/random", response_model=List[HotTourInfo])
async def get_random_tours_get(
    count: int = Query(6, ge=1, le=20, description="Количество случайных туров"),
    hotel_types: Optional[str] = Query(
        None, 
        description="Типы отелей через запятую: active,relax,family,health,city,beach,deluxe"
    )
):
    """
    Получение абсолютно случайных туров из любых стран и городов (GET метод)
    
    Параметры:
    - count: количество туров (1-20)
    - hotel_types: типы отелей через запятую (необязательно)
    
    Примеры:
    - /api/v1/tours/random?count=8
    - /api/v1/tours/random?count=6&hotel_types=beach,relax
    - /api/v1/tours/random?count=10&hotel_types=deluxe
    """
    try:
        # Парсим типы отелей
        hotel_types_list = None
        if hotel_types:
            hotel_types_list = [ht.strip() for ht in hotel_types.split(",") if ht.strip()]
        
        request = RandomTourRequest(count=count, hotel_types=hotel_types_list)
        logger.info(f"🎯 GET запрос {request.count} рандомных туров")
        if request.hotel_types:
            logger.info(f"🏨 С фильтрацией по типам: {request.hotel_types}")
        
        result = await random_tours_service.get_random_tours(request)
        logger.info(f"✅ Возвращено {len(result)} туров")
        
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка при получении случайных туров: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/random", response_model=List[HotTourInfo])
async def get_random_tours_post(request: RandomTourRequest = None):
    """
    Получение абсолютно случайных туров из любых стран и городов (POST метод)
    
    Пример запроса:
    {
        "count": 8,
        "hotel_types": ["beach", "relax", "deluxe"]
    }
    """
    try:
        if request is None:
            request = RandomTourRequest()
        
        logger.info(f"🎯 POST запрос {request.count} рандомных туров")
        if request.hotel_types:
            logger.info(f"🏨 С фильтрацией по типам: {request.hotel_types}")
        
        result = await random_tours_service.get_random_tours(request)
        logger.info(f"✅ Возвращено {len(result)} туров")
        
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка при получении случайных туров: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/random/generate", response_model=List[HotTourInfo])
async def generate_random_tours(
    count: int = Query(6, ge=1, le=20, description="Количество случайных туров"),
    hotel_types: Optional[str] = Query(
        None,
        description="Типы отелей через запятую: active,relax,family,health,city,beach,deluxe"
    )
):
    """
    Принудительная генерация новых случайных туров (без кэша)
    
    Этот endpoint всегда генерирует новые туры, игнорируя кэш
    """
    try:
        # Парсим типы отелей
        hotel_types_list = None
        if hotel_types:
            hotel_types_list = [ht.strip() for ht in hotel_types.split(",") if ht.strip()]
        
        request = RandomTourRequest(count=count, hotel_types=hotel_types_list)
        logger.info(f"🔄 Принудительная генерация {request.count} туров")
        if request.hotel_types:
            logger.info(f"🏨 С фильтрацией по типам: {request.hotel_types}")
        
        result = await random_tours_service._generate_fully_random_tours(request)
        logger.info(f"✅ Сгенерировано {len(result)} туров")
        
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка при генерации туров: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/random/clear-cache")
async def clear_random_tours_cache():
    """
    Очистка кэша случайных туров
    """
    try:
        cleared_count = await random_tours_service.clear_random_tours_cache()
        
        return {
            "success": True,
            "message": f"Очищено {cleared_count} записей кэша случайных туров",
            "cleared_cache_keys": cleared_count
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка при очистке кэша: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== ИНФОРМАЦИЯ О ФИЛЬТРАХ ==========

@router.get("/random/hotel-types")
async def get_available_hotel_types():
    """
    Получение списка доступных типов отелей для фильтрации
    """
    return {
        "available_hotel_types": [
            {"code": "active", "name": "Активный отдых", "description": "Отели для активного отдыха"},
            {"code": "relax", "name": "Спокойный отдых", "description": "Отели для спокойного отдыха"},
            {"code": "family", "name": "Семейный отдых", "description": "Семейные отели"},
            {"code": "health", "name": "Здоровье", "description": "SPA и wellness отели"},
            {"code": "city", "name": "Городской", "description": "Городские отели"},
            {"code": "beach", "name": "Пляжный", "description": "Пляжные отели"},
            {"code": "deluxe", "name": "Люкс (VIP)", "description": "Роскошные отели"}
        ],
        "usage_examples": [
            "GET /api/v1/tours/random?hotel_types=beach,relax",
            "GET /api/v1/tours/random?count=10&hotel_types=deluxe",
            "POST /api/v1/tours/random с body: {\"count\": 8, \"hotel_types\": [\"family\", \"beach\"]}"
        ]
    }

@router.get("/random/stats")
async def get_random_tours_stats():
    """
    Статистика системы случайных туров
    """
    try:
        # Получаем информацию о кэше
        cache_keys = await random_tours_service.cache.get_keys_pattern("random_tours_count_*")
        
        cache_info = {}
        for key in cache_keys:
            try:
                cached_data = await random_tours_service.cache.get(key)
                if cached_data:
                    cache_info[key] = {
                        "tours_count": len(cached_data),
                        "sample_countries": list(set([tour.get("countryname", "Unknown") for tour in cached_data[:5]])),
                        "sample_cities": list(set([tour.get("departurename", "Unknown") for tour in cached_data[:5]]))
                    }
            except:
                cache_info[key] = {"error": "Cannot read cache"}
        
        return {
            "system_info": {
                "total_countries_available": len(random_tours_service.all_countries),
                "total_cities_available": len(random_tours_service.all_cities),
                "cache_ttl_seconds": 3600,
                "max_tours_per_request": 20
            },
            "cache_status": {
                "cached_variants": len(cache_keys),
                "cache_details": cache_info
            },
            "supported_hotel_types": ["active", "relax", "family", "health", "city", "beach", "deluxe"],
            "features": {
                "fully_random_countries": True,
                "fully_random_cities": True,
                "hotel_type_filtering": True,
                "random_dates": True,
                "random_duration": True,
                "random_tourists_count": True
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка при получении статистики: {e}")
        return {
            "error": str(e),
            "message": "Не удалось получить статистику"
        }

# ========== НАПРАВЛЕНИЯ С ФОТОГРАФИЯМИ ==========

@router.get("/directions", response_model=List[DirectionInfo])
async def get_directions():
    """
    Получение списка направлений с минимальными ценами и фотографиями отелей
    """
    try:
        logger.info("🌍 Получение направлений с фото отелей")
        result = await directions_service.get_directions_with_prices()
        logger.info(f"✅ Получено {len(result)} направлений")
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка при получении направлений: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/directions/refresh")
async def refresh_directions():
    """
    Принудительное обновление направлений с фотографиями отелей
    """
    try:
        logger.info("🔄 Принудительное обновление направлений")
        
        result = await directions_service.refresh_directions()
        
        return {
            "success": True,
            "message": f"Обновлено {len(result)} направлений с фотографиями",
            "directions": [direction.dict() for direction in result]
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении направлений: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== АКТУАЛИЗАЦИЯ ТУРОВ ==========

@router.post("/actualize", response_model=DetailedTourInfo)
async def actualize_tour(request: TourActualizationRequest):
    """
    Актуализация тура с получением детальной информации и рейсов
    """
    try:
        return await tour_service.actualize_tour(request)
    except Exception as e:
        logger.error(f"Ошибка при актуализации тура: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tour/{tour_id}", response_model=DetailedTourInfo)
async def get_tour_by_id(tour_id: str):
    """
    Получение информации о туре по его ID
    """
    try:
        result = await tour_service.search_tour_by_id(tour_id)
        if not result:
            raise HTTPException(status_code=404, detail="Тур не найден")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении тура: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search-by-hotel", response_model=List[HotelInfo])
async def search_tours_by_hotel(
    hotel_name: str = Query(..., description="Название отеля"),
    country_code: int = Query(..., description="Код страны")
):
    """
    Поиск туров по названию отеля
    """
    try:
        return await tour_service.search_tours_by_hotel_name(hotel_name, country_code)
    except Exception as e:
        logger.error(f"Ошибка при поиске по отелю: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== ТЕСТИРОВАНИЕ И СТАТУС ==========

@router.get("/test-random-search")
async def test_random_search():
    """
    Тестирование генерации одного случайного тура для диагностики
    """
    try:
        logger.info("🧪 Тестирование генерации случайного тура")
        
        # Генерируем один тур для тестирования
        request = RandomTourRequest(count=1)
        result = await random_tours_service._generate_fully_random_tours(request)
        
        if result:
            tour = result[0]
            return {
                "success": True,
                "message": "Генерация случайного тура работает",
                "test_tour": {
                    "hotel_name": tour.hotelname,
                    "country": tour.countryname,
                    "departure_city": tour.departurename,
                    "nights": tour.nights,
                    "price": tour.price,
                    "stars": tour.hotelstars
                }
            }
        else:
            return {
                "success": False,
                "message": "Не удалось сгенерировать тестовый тур"
            }
            
    except Exception as e:
        logger.error(f"❌ Ошибка при тестировании: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@router.get("/test-connection")
async def test_tourvisor_connection():
    """
    Тестирование подключения к TourVisor API
    """
    try:
        logger.info("Тестирование подключения к TourVisor API...")
        
        # Простой запрос справочника городов
        result = await tourvisor_client.get_references("departure")
        
        if result:
            return {
                "success": True,
                "message": "Подключение к TourVisor API успешно",
                "data_keys": list(result.keys()),
                "sample_data": str(result)[:200] + "..." if len(str(result)) > 200 else str(result)
            }
        else:
            return {
                "success": False,
                "message": "TourVisor API вернул пустой ответ"
            }
            
    except Exception as e:
        logger.error(f"Ошибка при тестировании TourVisor API: {e}")
        return {
            "success": False,
            "message": f"Ошибка подключения: {str(e)}"
        }

@router.get("/status")
async def get_system_status():
    """
    Общий статус системы туров
    """
    try:
        # Проверяем разные компоненты системы
        status = {
            "timestamp": datetime.now().isoformat(),
            "components": {},
            "overall_health": "unknown"
        }
        
        # Проверяем TourVisor API
        try:
            test_result = await tourvisor_client.get_references("departure")
            status["components"]["tourvisor_api"] = {
                "status": "healthy" if test_result else "degraded",
                "response_time": "< 1s"
            }
        except Exception as e:
            status["components"]["tourvisor_api"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Проверяем кэш
        try:
            test_key = "health_check_test"
            await tour_service.cache.set(test_key, "test", ttl=60)
            test_value = await tour_service.cache.get(test_key)
            await tour_service.cache.delete(test_key)
            
            status["components"]["cache"] = {
                "status": "healthy" if test_value == "test" else "degraded"
            }
        except Exception as e:
            status["components"]["cache"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Определяем общее состояние
        all_statuses = [comp["status"] for comp in status["components"].values()]
        if all(s == "healthy" for s in all_statuses):
            status["overall_health"] = "healthy"
        elif any(s == "unhealthy" for s in all_statuses):
            status["overall_health"] = "unhealthy"
        else:
            status["overall_health"] = "degraded"
        
        return status
        
    except Exception as e:
        return {
            "timestamp": datetime.now().isoformat(),
            "overall_health": "unhealthy",
            "error": str(e) 
        }