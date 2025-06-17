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

# ========== СЛУЧАЙНЫЕ ТУРЫ ==========

@router.get("/random", response_model=List[HotTourInfo])
async def get_random_tours_get(
    count: int = Query(6, ge=1, le=20, description="Количество случайных туров")
):
    """
    Получение случайных туров через обычный поиск
    """
    try:
        request = RandomTourRequest(count=count)
        logger.info(f"🎯 Запрос {request.count} случайных туров")
        
        result = await random_tours_service.get_random_tours(request)
        logger.info(f"✅ Возвращено {len(result)} туров")
        
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка при получении случайных туров: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/random", response_model=List[HotTourInfo])
async def get_random_tours_post(request: RandomTourRequest = None):
    """
    Получение случайных туров через обычный поиск (POST)
    """
    try:
        if request is None:
            request = RandomTourRequest()
        
        logger.info(f"🎯 POST запрос {request.count} случайных туров")
        
        result = await random_tours_service.get_random_tours(request)
        logger.info(f"✅ Возвращено {len(result)} туров")
        
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка при получении случайных туров: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/random/generate", response_model=List[HotTourInfo])
async def generate_random_tours(
    count: int = Query(6, ge=1, le=20, description="Количество случайных туров")
):
    """
    Принудительная генерация новых случайных туров (без кэша)
    """
    try:
        logger.info(f"🔄 Принудительная генерация {count} туров")
        
        result = await random_tours_service._generate_random_tours_via_search(count)
        logger.info(f"✅ Сгенерировано {len(result)} туров")
        
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка при генерации туров: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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

@router.get("/directions/status")
async def get_directions_status():
    """
    Статус системы направлений
    """
    try:
        return await directions_service.get_directions_status()
    except Exception as e:
        return {
            "error": str(e),
            "recommendation": "use_refresh_endpoint"
        }

@router.get("/directions/fix-cache")
async def fix_directions_cache():
    """
    Исправление проблем с кэшированием направлений
    """
    try:
        return await directions_service.fix_cache_issues()
    except Exception as e:
        logger.error(f"❌ Ошибка при исправлении кэша: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ========== ДИАГНОСТИКА ФОТОГРАФИЙ ==========

@router.get("/directions/test-photo/{country_code}")
async def test_country_photo(country_code: int):
    """
    Тестирование получения фотографии для конкретной страны
    """
    try:
        country_name = tour_service._get_country_name(country_code)
        logger.info(f"🧪 Тестирование получения фото для {country_name} ({country_code})")
        
        # Тестируем все методы получения фото
        results = {}
        
        # 1. Горящие туры
        try:
            hot_tours_photo = await photo_service._get_photo_via_hot_tours(country_code, country_name)
            results["hot_tours"] = {
                "success": bool(hot_tours_photo),
                "photo_url": hot_tours_photo,
                "method": "Hot tours API"
            }
        except Exception as e:
            results["hot_tours"] = {
                "success": False,
                "error": str(e),
                "method": "Hot tours API"
            }
        
        # 2. Справочник отелей  
        try:
            reference_photo = await photo_service._get_photo_from_hotels_reference(country_code, country_name)
            results["hotels_reference"] = {
                "success": bool(reference_photo),
                "photo_url": reference_photo,
                "method": "Hotels reference"
            }
        except Exception as e:
            results["hotels_reference"] = {
                "success": False,
                "error": str(e),
                "method": "Hotels reference"
            }
        
        # 3. Поиск туров
        try:
            search_photo = await photo_service._get_photo_via_search(country_code, country_name)
            results["tours_search"] = {
                "success": bool(search_photo),
                "photo_url": search_photo,
                "method": "Tours search"
            }
        except Exception as e:
            results["tours_search"] = {
                "success": False,
                "error": str(e),
                "method": "Tours search"
            }
        
        # 4. Fallback
        fallback_photo = photo_service.get_fallback_image(country_code, country_name)
        results["fallback"] = {
            "success": True,
            "photo_url": fallback_photo,
            "method": "Fallback placeholder"
        }
        
        # Определяем лучший результат
        best_photo = None
        for method in ["hot_tours", "hotels_reference", "tours_search"]:
            if results[method]["success"] and results[method].get("photo_url"):
                best_photo = results[method]["photo_url"]
                break
        
        if not best_photo:
            best_photo = fallback_photo
        
        return {
            "country_code": country_code,
            "country_name": country_name,
            "best_photo": best_photo,
            "test_results": results,
            "recommendation": "Use the best_photo URL for this country"
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка при тестировании фото для страны {country_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/directions/diagnose")
async def diagnose_directions_system():
    """
    Полная диагностика системы получения направлений
    """
    try:
        logger.info("🔬 Начинаем полную диагностику системы направлений")
        
        diagnosis = {
            "timestamp": datetime.now().isoformat(),
            "countries": {},
            "summary": {},
            "recommendations": []
        }
        
        # Тестируем каждую страну
        from app.config import settings
        countries_to_test = settings.POPULAR_COUNTRIES[:3]  # Первые 3 страны
        
        for country_code in countries_to_test:
            country_name = tour_service._get_country_name(country_code)
            logger.info(f"🔬 Диагностируем {country_name} ({country_code})")
            
            country_diagnosis = {
                "country_code": country_code,
                "country_name": country_name,
                "photo_sources": {},
                "price_search": {},
                "issues": [],
                "working_methods": []
            }
            
            # 1. Тестируем горящие туры
            try:
                hot_tours_start = datetime.now()
                hot_tours_data = await tourvisor_client.get_hot_tours(
                    city=1, items=5, countries=str(country_code)
                )
                hot_tours_time = (datetime.now() - hot_tours_start).total_seconds()
                
                tours_list = hot_tours_data.get("hottours", [])
                if not isinstance(tours_list, list):
                    tours_list = [tours_list] if tours_list else []
                
                photos_found = 0
                for tour in tours_list:
                    if tour.get("hotelpicture") and not photo_service.is_placeholder_image(tour.get("hotelpicture")):
                        photos_found += 1
                
                country_diagnosis["photo_sources"]["hot_tours"] = {
                    "success": True,
                    "response_time": hot_tours_time,
                    "tours_found": len(tours_list),
                    "photos_found": photos_found,
                    "working": photos_found > 0
                }
                
                if photos_found > 0:
                    country_diagnosis["working_methods"].append("hot_tours")
                else:
                    country_diagnosis["issues"].append("No photos in hot tours")
                    
            except Exception as e:
                country_diagnosis["photo_sources"]["hot_tours"] = {
                    "success": False,
                    "error": str(e),
                    "working": False
                }
                country_diagnosis["issues"].append(f"Hot tours error: {str(e)}")
            
            # 2. Тестируем цены
            try:
                price_start = datetime.now()
                min_price = await price_service.get_country_min_price(country_code, country_name)
                price_time = (datetime.now() - price_start).total_seconds()
                
                country_diagnosis["price_search"] = {
                    "success": True,
                    "response_time": price_time,
                    "min_price": min_price,
                    "working": min_price > 0,
                    "is_default": min_price in price_service.get_default_prices().values()
                }
                
            except Exception as e:
                country_diagnosis["price_search"] = {
                    "success": False,
                    "error": str(e),
                    "working": False
                }
            
            diagnosis["countries"][country_code] = country_diagnosis
            
            # Небольшая задержка между странами
            await asyncio.sleep(1)
        
        # Анализируем результаты
        total_countries = len(diagnosis["countries"])
        working_countries = 0
        photo_issues = 0
        price_issues = 0
        
        for country_data in diagnosis["countries"].values():
            if country_data["working_methods"]:
                working_countries += 1
            if not country_data["working_methods"]:
                photo_issues += 1
            if not country_data["price_search"].get("working", False):
                price_issues += 1
        
        diagnosis["summary"] = {
            "total_countries_tested": total_countries,
            "countries_with_photos": working_countries,
            "countries_with_photo_issues": photo_issues,
            "countries_with_price_issues": price_issues,
            "success_rate": f"{(working_countries/total_countries)*100:.1f}%" if total_countries > 0 else "0%"
        }
        
        # Рекомендации
        if photo_issues > 0:
            diagnosis["recommendations"].append("Проблемы с получением фото отелей - проверьте доступность API TourVisor")
        if price_issues > 0:
            diagnosis["recommendations"].append("Проблемы с получением цен - возможно, нет туров на указанные даты")
        if working_countries == total_countries:
            diagnosis["recommendations"].append("Система работает корректно!")
        
        logger.info(f"🔬 Диагностика завершена: {diagnosis['summary']['success_rate']} успеха")
        return diagnosis
        
    except Exception as e:
        logger.error(f"❌ Ошибка при диагностике: {e}")
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