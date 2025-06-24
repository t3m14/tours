from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
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
from app.services.photo_service import photo_service
from app.services.price_service import price_service
from app.core.tourvisor_client import tourvisor_client
from app.utils.logger import setup_logger
from app.services.specific_tour_service import specific_tour_service
from app.models.tour import FoundTourInfo, SpecificTourSearchRequest, TourSearchError

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
# ========== НАПРАВЛЕНИЯ ==========

@router.get("/destinations")
async def get_destinations():
    """
    Получение 15 туристических направлений
    
    Возвращает направления из популярных стран (Египет, Турция, Таиланд) с:
    - Названием города/курорта
    - Country ID  
    - Минимальной ценой среди всех туров
    - Фотографией любого отеля в этом городе
    
    Кэшируется на 24 часа.
    """
    try:
        from app.services.destinations_service import destinations_service
        
        logger.info("🏖️ Запрос направлений")
        
        result = await city_directions_service.get_all_city_directions(
            country_id=country_id,
            limit_per_country=limit_per_country
        )
        
        logger.info(f"✅ Получено {result.total_countries} стран, {result.total_cities} городов")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Ошибка при получении направлений по городам: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/directions/popular")
async def get_popular_directions(
    limit: int = Query(6, ge=1, le=20, description="Количество популярных направлений")
):
    """
    Получение популярных направлений (ограниченное количество)
    """
    try:
        logger.info(f"🌟 Получение {limit} популярных направлений")
        result = await directions_service.get_directions_subset(limit=limit)
        logger.info(f"✅ Получено {len(result)} популярных направлений")
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка при получении популярных направлений: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/directions/collect-all")
async def collect_all_directions(
    force_rebuild: bool = Query(False, description="Принудительный пересбор даже если кэш существует")
):
    """
    Запуск массового сбора направлений из ВСЕХ доступных стран
    
    Этот endpoint может выполняться долго (несколько минут)
    """
    try:
        logger.info(f"🌍 Запуск массового сбора направлений (force_rebuild={force_rebuild})")
        
        # Запускаем массовый сбор
        result = await directions_service.collect_all_directions(force_rebuild=force_rebuild)
        
        # Получаем статистику
        status = await directions_service.get_directions_status()
        
        return {
            "destinations": destinations,
            "total": len(destinations)
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения направлений: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/destinations/refresh")
async def refresh_destinations():
    """Принудительное обновление направлений"""
    try:
        from app.services.destinations_service import destinations_service
        
        logger.info("🔄 Обновление направлений")
        
        destinations = await destinations_service.refresh()
        
        return {
            "message": "Направления обновлены",
            "destinations": destinations,
            "total": len(destinations)
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка обновления направлений: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@router.get("/destinations/status")
async def get_destinations_status():
    """
    Статус системы туристических направлений
    """
    try:
        from tourvisor_middleware.travel_agency_backend.app.services.destinations_service import tourist_destinations_service
        
        status = await tourist_destinations_service.get_cache_status()
        
        return {
            "system": "tourist_destinations",
            "timestamp": datetime.now().isoformat(),
            "cache_status": status,
            "popular_countries": {
                1: "Египет",
                4: "Турция", 
                22: "Таиланд"
            },
            "endpoints": {
                "get_destinations": "/api/v1/tours/destinations",
                "refresh_destinations": "/api/v1/tours/destinations/refresh",
                "check_status": "/api/v1/tours/destinations/status"
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения статуса: {e}")
        raise HTTPException(status_code=500, detail=str(e))
# Добавьте этот endpoint после других направлений endpoints
@router.get("/directions/debug-api")
async def debug_tourvisor_api():
    """Диагностика API TourVisor для отладки"""
    try:
        # Проверяем что возвращает API стран
        countries_data = await tourvisor_client.get_references("country")
        
        # Проверяем что возвращает API курортов для известной страны
        regions_data = await tourvisor_client.get_references("region", regcountry=1)  # Египет
        
        return {
            "countries_response": {
                "keys": list(countries_data.keys()) if countries_data else [],
                "sample_data": str(countries_data)[:500] if countries_data else "No data",
                "type": type(countries_data).__name__
            },
            "regions_response": {
                "keys": list(regions_data.keys()) if regions_data else [],
                "sample_data": str(regions_data)[:500] if regions_data else "No data", 
                "type": type(regions_data).__name__
            }
        }
        
    except Exception as e:
        return {"error": str(e)}

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
@router.post("/random/clear-hotel-type-cache")
async def clear_hotel_type_cache():
    """
    Очистка кэша туров по типам отелей
    """
    try:
        cleared_count = await random_tours_service.clear_hotel_type_cache()
        
        return {
            "success": True,
            "message": f"Очищено {cleared_count} записей кэша туров по типам отелей",
            "cleared_cache_keys": cleared_count
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка при очистке кэша типов отелей: {e}")
        raise HTTPException(status_code=500, detail=str(e))





# ========== ПОИСК КОНКРЕТНОГО ТУРА ==========

@router.get("/find-tour")
async def find_specific_tour(
    # Основные параметры поиска
    departure: int = Query(..., description="Код города вылета"),
    country: int = Query(..., description="Код страны"),
    
    # Фильтры отеля
    hotel_stars: Optional[int] = Query(None, ge=1, le=5, description="Звездность отеля"),
    hotel_name: Optional[str] = Query(None, min_length=3, description="Название отеля (поиск по подстроке)"),
    hotel_id: Optional[str] = Query(None, description="ID отеля"),
    region_code: Optional[int] = Query(None, description="Код курорта"),
    
    # Фильтры тура
    nights: Optional[int] = Query(None, ge=1, le=30, description="Количество ночей"),
    adults: int = Query(2, ge=1, le=8, description="Количество взрослых"),
    children: int = Query(0, ge=0, le=4, description="Количество детей"),
    meal_type: Optional[int] = Query(None, description="Тип питания (код)"),
    
    # Фильтры цены
    max_price: Optional[int] = Query(None, gt=0, description="Максимальная цена"),
    min_price: Optional[int] = Query(None, gt=0, description="Минимальная цена"),
    
    # Фильтры дат
    date_from: Optional[str] = Query(None, description="Дата от (дд.мм.гггг)"),
    date_to: Optional[str] = Query(None, description="Дата до (дд.мм.гггг)"),
    
    # Дополнительные фильтры
    rating: Optional[float] = Query(None, ge=1.0, le=5.0, description="Минимальный рейтинг отеля"),
    hotel_type: Optional[str] = Query(None, description="Тип отеля: beach,city,family,deluxe,etc"),
):
    """
    Поиск конкретного тура по заданным параметрам
    
    Возвращает ОДИН тур, наиболее подходящий под критерии, или ошибку если ничего не найдено.
    
    Примеры запросов:
    - /find-tour?departure=1&country=4&hotel_stars=4&meal_type=2
    - /find-tour?departure=1&country=1&hotel_name=hilton&nights=7
    - /find-tour?departure=2&country=22&max_price=100000&hotel_stars=5
    """
    try:
        logger.info(f"🔎 Поиск конкретного тура: страна {country}, город вылета {departure}")
        
        # Создаем объект запроса
        search_request = SpecificTourSearchRequest(
            departure=departure,
            country=country,
            hotel_stars=hotel_stars,
            hotel_name=hotel_name,
            hotel_id=hotel_id,
            region_code=region_code,
            nights=nights,
            adults=adults,
            children=children,
            meal_type=meal_type,
            max_price=max_price,
            min_price=min_price,
            date_from=date_from,
            date_to=date_to,
            rating=rating,
            hotel_type=hotel_type
        )
        
        # Выполняем поиск через сервис
        found_tour = await specific_tour_service.find_specific_tour(search_request)
        
        logger.info(f"✅ Найден тур: {found_tour.hotel_name} - {found_tour.price} руб.")
        return found_tour
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"❌ Тур не найден: {e}")
        
        # Создаем объект запроса для получения предложений
        search_request = SpecificTourSearchRequest(
            departure=departure,
            country=country,
            hotel_stars=hotel_stars,
            hotel_name=hotel_name,
            hotel_id=hotel_id,
            region_code=region_code,
            nights=nights,
            adults=adults,
            children=children,
            meal_type=meal_type,
            max_price=max_price,
            min_price=min_price,
            date_from=date_from,
            date_to=date_to,
            rating=rating,
            hotel_type=hotel_type
        )
        
        suggestions = specific_tour_service.get_search_suggestions(search_request)
        
        raise HTTPException(
            status_code=404,
            detail=TourSearchError(
                error="Тур не найден",
                message="По заданным критериям туры не найдены",
                suggestions=suggestions
            ).dict()
        )
    except Exception as e:
        logger.error(f"❌ Ошибка при поиске конкретного тура: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/find-tour/by-hotel", response_model=FoundTourInfo)
async def find_tour_by_hotel(
    hotel_name: str = Query(..., min_length=3, description="Название отеля"),
    departure: int = Query(..., description="Код города вылета"),
    country: int = Query(..., description="Код страны"),
    nights: Optional[int] = Query(7, description="Количество ночей"),
    adults: int = Query(2, description="Количество взрослых"),
):
    """
    Упрощенный поиск тура по названию отеля
    
    Пример: /find-tour/by-hotel?hotel_name=hilton&departure=1&country=4&nights=7
    """
    try:
        found_tour = await specific_tour_service.find_tour_by_hotel_name(
            hotel_name=hotel_name,
            departure=departure,
            country=country,
            nights=nights,
            adults=adults
        )
        return found_tour
    except Exception as e:
        logger.error(f"❌ Ошибка поиска по отелю: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/find-tour/by-criteria", response_model=FoundTourInfo)
async def find_tour_by_criteria(
    departure: int = Query(..., description="Код города вылета"),
    country: int = Query(..., description="Код страны"),
    hotel_stars: int = Query(..., ge=1, le=5, description="Звездность отеля"),
    meal_type: int = Query(..., description="Тип питания"),
    max_price: Optional[int] = Query(None, description="Максимальная цена"),
    nights: int = Query(7, description="Количество ночей"),
    adults: int = Query(2, description="Количество взрослых"),
):
    """
    Поиск тура по основным критериям (как в примере фронтендера)
    
    Пример: /find-tour/by-criteria?departure=1&country=4&hotel_stars=4&meal_type=2
    """
    try:
        found_tour = await specific_tour_service.find_tour_by_criteria(
            departure=departure,
            country=country,
            hotel_stars=hotel_stars,
            meal_type=meal_type,
            max_price=max_price,
            nights=nights,
            adults=adults
        )
        return found_tour
    except Exception as e:
        logger.error(f"❌ Ошибка поиска по критериям: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/find-tour", response_model=FoundTourInfo)
async def find_tour_post(search_request: SpecificTourSearchRequest):
    """
    Поиск конкретного тура через POST запрос с телом
    
    Пример тела запроса:
    {
        "departure": 1,
        "country": 4,
        "hotel_stars": 4,
        "meal_type": 2,
        "nights": 7,
        "adults": 2,
        "max_price": 80000
    }
    """
    try:
        found_tour = await specific_tour_service.find_specific_tour(search_request)
        return found_tour
    except Exception as e:
        logger.error(f"❌ Ошибка POST поиска тура: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== ИНФОРМАЦИОННЫЕ ENDPOINTS ==========

@router.get("/find-tour/meal-types")
async def get_meal_types():
    """
    Получение списка типов питания с кодами
    """
    try:
        # Получаем справочник типов питания
        meal_data = await tourvisor_client.get_references("meal")
        
        return {
            "meal_types": meal_data.get("meal", []),
            "usage_info": {
                "description": "Используйте код типа питания в параметре meal_type",
                "example": "meal_type=2 для завтрака"
            }
        }
    except Exception as e:
        logger.error(f"❌ Ошибка получения типов питания: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/find-tour/hotel-types")
async def get_hotel_types():
    """
    Получение списка типов отелей
    """
    return {
        "hotel_types": [
            {"code": "active", "name": "Активный отдых"},
            {"code": "relax", "name": "Спокойный отдых"},
            {"code": "family", "name": "Семейный отдых"},
            {"code": "health", "name": "Здоровье/SPA"},
            {"code": "city", "name": "Городской отель"},
            {"code": "beach", "name": "Пляжный отель"},
            {"code": "deluxe", "name": "Люкс/VIP отель"}
        ],
        "usage_info": {
            "description": "Используйте код типа отеля в параметре hotel_type",
            "example": "hotel_type=beach для пляжных отелей"
        }
    }

@router.get("/find-tour/examples")
async def get_search_examples():
    """
    Примеры использования API поиска конкретного тура
    """
    return {
        "examples": {
            "by_criteria": {
                "description": "Поиск по основным критериям (как просил фронтендер)",
                "url": "/api/v1/tours/find-tour/by-criteria?departure=1&country=4&hotel_stars=4&meal_type=2",
                "parameters": {
                    "departure": "1 (Москва)",
                    "country": "4 (Турция)",
                    "hotel_stars": "4 (4 звезды)",
                    "meal_type": "2 (завтрак)"
                }
            },
            "by_hotel_name": {
                "description": "Поиск по названию отеля",
                "url": "/api/v1/tours/find-tour/by-hotel?hotel_name=hilton&departure=1&country=4",
                "parameters": {
                    "hotel_name": "hilton",
                    "departure": "1 (Москва)",
                    "country": "4 (Турция)"
                }
            },
            "detailed_search": {
                "description": "Детальный поиск с множеством параметров",
                "url": "/api/v1/tours/find-tour?departure=1&country=22&hotel_stars=5&nights=10&max_price=150000&hotel_type=beach&rating=4.0",
                "parameters": {
                    "departure": "1 (Москва)",
                    "country": "22 (Таиланд)",
                    "hotel_stars": "5 звезд",
                    "nights": "10 ночей",
                    "max_price": "до 150,000 руб",
                    "hotel_type": "beach (пляжный)",
                    "rating": "рейтинг от 4.0"
                }
            },
            "post_request": {
                "description": "POST запрос с JSON телом",
                "url": "/api/v1/tours/find-tour (POST)",
                "body": {
                    "departure": 1,
                    "country": 4,
                    "hotel_stars": 4,
                    "meal_type": 2,
                    "nights": 7,
                    "adults": 2,
                    "max_price": 80000
                }
            }
        },
        "common_codes": {
            "departure_cities": {
                "1": "Москва",
                "2": "Пермь", 
                "3": "Екатеринбург",
                "5": "Санкт-Петербург"
            },
            "countries": {
                "1": "Египет",
                "4": "Турция",
                "8": "Греция",
                "15": "ОАЭ",
                "22": "Таиланд",
                "35": "Мальдивы"
            },
            "meal_types": {
                "1": "Без питания",
                "2": "Завтрак",
                "3": "Полупансион", 
                "4": "Полный пансион",
                "5": "Всё включено",
                "7": "All Inclusive"
            }
        },
        "tips": [
            "Если тур не найден, API вернет предложения по изменению критериев",
            "Параметры hotel_name и hotel_id взаимоисключающие",
            "Для поиска по отелю лучше использовать /find-tour/by-hotel",
            "Система автоматически применяет fallback стратегии при отсутствии точных совпадений",
            "Результат кэшируется на 30 минут для ускорения повторных запросов"
        ]
    }

@router.get("/find-tour/test")
async def test_find_tour():
    """
    Тестовый endpoint для проверки работы поиска конкретного тура
    """
    try:
        logger.info("🧪 Тестирование поиска конкретного тура")
        
        # Простой тестовый поиск
        test_request = SpecificTourSearchRequest(
            departure=1,  # Москва
            country=4,    # Турция
            hotel_stars=4,
            nights=7,
            adults=2
        )
        
        found_tour = await specific_tour_service.find_specific_tour(test_request)
        
        return {
            "success": True,
            "message": "Поиск конкретного тура работает",
            "test_result": {
                "hotel_name": found_tour.hotel_name,
                "hotel_stars": found_tour.hotel_stars,
                "price": found_tour.price,
                "nights": found_tour.nights,
                "operator": found_tour.operator_name,
                "region": found_tour.region_name
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка тестирования: {e}")
        return {
            "success": False,
            "error": str(e),
            "message": "Тестирование не прошло, проверьте логи"
        }

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

async def _build_tour_search_params(
    departure: int,
    country: int,
    hotel_stars: Optional[int] = None,
    hotel_name: Optional[str] = None,
    hotel_id: Optional[str] = None,
    region_code: Optional[int] = None,
    nights: Optional[int] = None,
    adults: int = 2,
    children: int = 0,
    meal_type: Optional[int] = None,
    max_price: Optional[int] = None,
    min_price: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    rating: Optional[float] = None,
    hotel_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Построение параметров поиска для TourVisor API"""
    
    # Базовые параметры
    params = {
        "departure": departure,
        "country": country,
        "adults": adults,
        "child": children,
    }
    
    # Даты (если не указаны, берем ближайшие 2 недели)
    if not date_from:
        start_date = datetime.now() + timedelta(days=7)
        params["datefrom"] = start_date.strftime("%d.%m.%Y")
    else:
        params["datefrom"] = date_from
    
    if not date_to:
        end_date = datetime.now() + timedelta(days=21)
        params["dateto"] = end_date.strftime("%d.%m.%Y")
    else:
        params["dateto"] = date_to
    
    # Ночи
    if nights:
        params["nightsfrom"] = nights
        params["nightsto"] = nights
    else:
        params["nightsfrom"] = 7
        params["nightsto"] = 10
    
    # Фильтры отеля
    if hotel_id:
        params["hotels"] = hotel_id
    
    if hotel_stars:
        params["stars"] = hotel_stars
        params["starsbetter"] = 1  # Включать лучшие категории
    
    if region_code:
        params["regions"] = str(region_code)
    
    if rating:
        # Конвертируем рейтинг в формат TourVisor
        if rating >= 4.5:
            params["rating"] = 5  # >= 4.5
        elif rating >= 4.0:
            params["rating"] = 4  # >= 4.0
        elif rating >= 3.5:
            params["rating"] = 3  # >= 3.5
        elif rating >= 3.0:
            params["rating"] = 2  # >= 3.0
    
    if hotel_type:
        params["hoteltypes"] = hotel_type
    
    # Фильтры питания
    if meal_type:
        params["meal"] = meal_type
        params["mealbetter"] = 1
    
    # Фильтры цены
    if min_price:
        params["pricefrom"] = min_price
    if max_price:
        params["priceto"] = max_price
    
    # Дополнительные параметры
    params["format"] = "xml"
    params["pricetype"] = 0  # Цена за номер
    
    return params

async def _execute_specific_tour_search(search_params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Выполнение точного поиска тура"""
    try:
        # Если указано название отеля, сначала найдем его ID
        hotel_name = search_params.pop("hotel_name", None)
        if hotel_name and "hotels" not in search_params:
            hotel_id = await _find_hotel_id_by_name(hotel_name, search_params["country"])
            if hotel_id:
                search_params["hotels"] = hotel_id
                logger.info(f"🏨 Найден ID отеля '{hotel_name}': {hotel_id}")
            else:
                logger.warning(f"🏨 Отель '{hotel_name}' не найден")
                return None
        
        # Запускаем поиск
        request_id = await tourvisor_client.search_tours(search_params)
        
        # Ждем результатов (максимум 10 секунд)
        for attempt in range(10):
            await asyncio.sleep(1)
            
            status = await tourvisor_client.get_search_status(request_id)
            status_data = status.get("data", {}).get("status", {})
            
            if status_data.get("state") == "finished" or status_data.get("hotelsfound", 0) > 0:
                break
        
        # Получаем результаты
        results = await tourvisor_client.get_search_results(request_id, 1, 5)
        
        # Извлекаем первый подходящий тур
        tour = await _extract_best_tour_from_results(results, search_params)
        return tour
        
    except Exception as e:
        logger.error(f"❌ Ошибка выполнения поиска: {e}")
        return None

async def _execute_fallback_tour_search(original_params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Fallback поиск с ослабленными критериями"""
    try:
        logger.info("🔄 Выполняем fallback поиск с ослабленными критериями")
        
        # Создаем копию параметров для изменения
        fallback_params = original_params.copy()
        
        # Ослабляем критерии поиска
        fallback_strategies = [
            # Стратегия 1: Убираем точное количество ночей
            lambda p: {**p, "nightsfrom": max(1, p.get("nightsfrom", 7) - 3), "nightsto": p.get("nightsto", 10) + 3},
            
            # Стратегия 2: Убираем фильтр по звездности
            lambda p: {k: v for k, v in p.items() if k not in ["stars", "starsbetter"]},
            
            # Стратегия 3: Расширяем ценовой диапазон
            lambda p: {**{k: v for k, v in p.items() if k not in ["pricefrom", "priceto"]}, 
                      "priceto": p.get("priceto", 200000) * 1.5 if p.get("priceto") else None},
            
            # Стратегия 4: Убираем фильтр по типу отеля
            lambda p: {k: v for k, v in p.items() if k not in ["hoteltypes"]},
            
            # Стратегия 5: Расширяем диапазон дат
            lambda p: _expand_date_range(p),
        ]
        
        for i, strategy in enumerate(fallback_strategies):
            try:
                logger.info(f"🔄 Fallback стратегия {i+1}")
                
                modified_params = strategy(fallback_params)
                
                if modified_params:
                    tour = await _execute_specific_tour_search(modified_params)
                    if tour:
                        logger.info(f"✅ Fallback стратегия {i+1} успешна")
                        tour["is_fallback"] = True
                        tour["fallback_strategy"] = i + 1
                        return tour
                
            except Exception as e:
                logger.debug(f"Fallback стратегия {i+1} не сработала: {e}")
                continue
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Ошибка fallback поиска: {e}")
        return None

def _expand_date_range(params: Dict[str, Any]) -> Dict[str, Any]:
    """Расширение диапазона дат для поиска"""
    try:
        expanded_params = params.copy()
        
        # Расширяем диапазон на ±7 дней
        if "datefrom" in params:
            date_from = datetime.strptime(params["datefrom"], "%d.%m.%Y")
            new_date_from = date_from - timedelta(days=7)
            expanded_params["datefrom"] = new_date_from.strftime("%d.%m.%Y")
        
        if "dateto" in params:
            date_to = datetime.strptime(params["dateto"], "%d.%m.%Y")
            new_date_to = date_to + timedelta(days=7)
            expanded_params["dateto"] = new_date_to.strftime("%d.%m.%Y")
        
        return expanded_params
        
    except Exception:
        return params

async def _find_hotel_id_by_name(hotel_name: str, country_code: int) -> Optional[str]:
    """Поиск ID отеля по названию"""
    try:
        # Ищем в справочнике отелей
        hotels_data = await tourvisor_client.get_references(
            "hotel",
            hotcountry=country_code
        )
        
        hotels = hotels_data.get("hotel", [])
        if not isinstance(hotels, list):
            hotels = [hotels] if hotels else []
        
        # Ищем отель по названию (нечеткий поиск)
        hotel_name_lower = hotel_name.lower()
        
        for hotel in hotels:
            hotel_api_name = hotel.get("name", "").lower()
            if hotel_name_lower in hotel_api_name or hotel_api_name in hotel_name_lower:
                return hotel.get("id")
        
        return None
        
    except Exception as e:
        logger.error(f"❌ Ошибка поиска ID отеля: {e}")
        return None

async def _extract_best_tour_from_results(results: Dict[str, Any], search_params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Извлечение лучшего тура из результатов поиска"""
    try:
        data = results.get("data", {})
        result_data = data.get("result", {})
        hotel_list = result_data.get("hotel", [])
        
        if not isinstance(hotel_list, list):
            hotel_list = [hotel_list] if hotel_list else []
        
        if not hotel_list:
            return None
        
        # Собираем все туры
        all_tours = []
        
        for hotel in hotel_list:
            tours_data = hotel.get("tours", {}).get("tour", [])
            
            if not isinstance(tours_data, list):
                tours_data = [tours_data] if tours_data else []
            
            for tour_data in tours_data:
                # Создаем объединенную информацию о туре
                combined_tour = {
                    # Информация об отеле
                    "hotel_id": hotel.get("hotelcode"),
                    "hotel_name": hotel.get("hotelname"),
                    "hotel_stars": hotel.get("hotelstars"),
                    "hotel_rating": hotel.get("hotelrating"),
                    "hotel_description": hotel.get("hoteldescription"),
                    "hotel_picture": hotel.get("picturelink"),
                    "hotel_review_link": hotel.get("reviewlink"),
                    "country_name": hotel.get("countryname"),
                    "region_name": hotel.get("regionname"),
                    "sea_distance": hotel.get("seadistance"),
                    
                    # Информация о туре
                    "tour_id": tour_data.get("tourid"),
                    "operator_name": tour_data.get("operatorname"),
                    "fly_date": tour_data.get("flydate"),
                    "nights": tour_data.get("nights"),
                    "price": tour_data.get("price"),
                    "fuel_charge": tour_data.get("fuelcharge"),
                    "meal": tour_data.get("mealrussian", tour_data.get("meal")),
                    "room_type": tour_data.get("room"),
                    "adults": tour_data.get("adults"),
                    "children": tour_data.get("child"),
                    "currency": tour_data.get("currency"),
                    "tour_link": tour_data.get("tourlink"),
                    
                    # Дополнительная информация
                    "is_regular": tour_data.get("regular") == 1,
                    "is_promo": tour_data.get("promo") == 1,
                    "is_on_request": tour_data.get("onrequest") == 1,
                    "flight_status": tour_data.get("flightstatus"),
                    "hotel_status": tour_data.get("hotelstatus"),
                }
                
                all_tours.append(combined_tour)
        
        if not all_tours:
            return None
        
        # Сортируем туры по релевантности
        sorted_tours = _sort_tours_by_relevance(all_tours, search_params)
        
        # Возвращаем лучший тур
        best_tour = sorted_tours[0]
        
        # Добавляем метаинформацию
        best_tour["search_results_count"] = len(all_tours)
        best_tour["hotels_found"] = len(hotel_list)
        
        return best_tour
        
    except Exception as e:
        logger.error(f"❌ Ошибка извлечения тура: {e}")
        return None

def _sort_tours_by_relevance(tours: List[Dict[str, Any]], search_params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Сортировка туров по релевантности поисковому запросу"""
    
    def calculate_relevance_score(tour: Dict[str, Any]) -> float:
        score = 0.0
        
        # Очки за соответствие звездности
        if "stars" in search_params and tour.get("hotel_stars"):
            requested_stars = search_params["stars"]
            hotel_stars = tour["hotel_stars"]
            if hotel_stars == requested_stars:
                score += 100
            elif hotel_stars > requested_stars:
                score += 80  # Лучше чем запрошено
            else:
                score += max(0, 50 - (requested_stars - hotel_stars) * 10)
        
        # Очки за количество ночей
        if "nightsfrom" in search_params and tour.get("nights"):
            requested_nights = search_params["nightsfrom"]
            tour_nights = tour["nights"]
            if tour_nights == requested_nights:
                score += 80
            else:
                score += max(0, 40 - abs(tour_nights - requested_nights) * 5)
        
        # Очки за рейтинг отеля
        if tour.get("hotel_rating"):
            rating = float(tour["hotel_rating"])
            score += rating * 10  # До 50 очков за рейтинг
        
        # Очки за цену (предпочитаем средние цены)
        if tour.get("price"):
            price = float(tour["price"])
            # Нормализуем цену (оптимальная цена = больше очков)
            if 30000 <= price <= 150000:  # Разумный диапазон
                score += 30
            elif price < 30000:
                score += 20  # Очень дешево - может быть подозрительно
            else:
                score += max(0, 30 - (price - 150000) / 10000)  # Очень дорого
        
        # Очки за статус (не "под запрос")
        if not tour.get("is_on_request", False):
            score += 20
        
        # Очки за наличие фотографии
        if tour.get("hotel_picture"):
            score += 10
        
        # Штраф за регулярные рейсы (могут быть доплаты)
        if tour.get("is_regular", False):
            score -= 10
        
        return score
    
    # Сортируем по убыванию релевантности
    tours_with_scores = [(tour, calculate_relevance_score(tour)) for tour in tours]
    tours_with_scores.sort(key=lambda x: x[1], reverse=True)
    
    return [tour for tour, score in tours_with_scores]

def _generate_find_tour_cache_key(search_params: Dict[str, Any]) -> str:
    """Генерация ключа кэша для поиска конкретного тура"""
    # Создаем хэш параметров для уникального ключа
    import hashlib
    import json
    
    # Сортируем параметры для консистентности
    sorted_params = json.dumps(search_params, sort_keys=True, default=str)
    params_hash = hashlib.md5(sorted_params.encode()).hexdigest()
    
    return f"find_tour:{params_hash}"

async def _get_search_suggestions(search_params: Dict[str, Any]) -> List[str]:
    """Получение предложений для улучшения поиска"""
    suggestions = []
    
    # Предложения по ослаблению критериев
    if "stars" in search_params:
        suggestions.append(f"Попробуйте отели {search_params['stars']-1}* или без фильтра по звездности")
    
    if "priceto" in search_params:
        suggestions.append(f"Увеличьте максимальную цену до {int(search_params['priceto'] * 1.3):,} руб.")
    
    if "nightsfrom" in search_params:
        nights = search_params["nightsfrom"]
        suggestions.append(f"Попробуйте {nights-2}-{nights+2} ночей вместо точно {nights}")
    
    if "hotels" in search_params:
        suggestions.append("Попробуйте поиск без указания конкретного отеля")
    
    # Общие предложения
    suggestions.extend([
        "Измените даты поездки на ±7 дней",
        "Выберите другой город вылета",
        "Попробуйте соседние курорты"
    ])
    
    return suggestions[:5]  # Возвращаем не более 5 предложений