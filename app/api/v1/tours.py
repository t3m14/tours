# app/api/v1/tours.py - ОЧИЩЕННАЯ ВЕРСИЯ

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
import asyncio
from datetime import datetime, timedelta

from app.models.tour import (
    TourSearchRequest, SearchResponse, SearchResult, SearchStatus,
    RandomTourRequest, HotTourInfo, TourActualizationRequest,
    DetailedTourInfo, HotelInfo
)
from app.services.tour_service import tour_service
from app.services.random_tours_service import random_tours_service
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

# ========== СЛУЧАЙНЫЕ ТУРЫ И НАПРАВЛЕНИЯ ==========

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
        logger.error(f"❌ Ошибка при генерации случайных туров: {e}")
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

# ========== ОТЛАДОЧНЫЕ ENDPOINTS ==========

@router.post("/debug-raw-actualize")
async def debug_raw_actualize(request: TourActualizationRequest):
    """
    Получение сырых данных актуализации без обработки Pydantic
    """
    try:
        logger.info(f"🐛 RAW DEBUG: Запрос сырых данных тура {request.tour_id}")
        
        # Получаем сырые данные от TourVisor
        basic_info = await tourvisor_client.actualize_tour(
            request.tour_id,
            request.request_check
        )
        
        detailed_info = await tourvisor_client.get_detailed_actualization(
            request.tour_id
        )
        
        # Возвращаем сырые данные для анализа
        response = {
            "tour_id": request.tour_id,
            "basic_info": basic_info,
            "detailed_info": detailed_info,
            "basic_info_type": str(type(basic_info)),
            "detailed_info_type": str(type(detailed_info)),
            "basic_keys": list(basic_info.keys()) if isinstance(basic_info, dict) else "not dict",
            "detailed_keys": list(detailed_info.keys()) if isinstance(detailed_info, dict) else "not dict"
        }
        
        # Если есть flights, анализируем их структуру
        if isinstance(detailed_info, dict) and "flights" in detailed_info:
            flights = detailed_info["flights"]
            response["flights_analysis"] = {
                "flights_type": str(type(flights)),
                "flights_count": len(flights) if isinstance(flights, list) else "not list",
                "first_flight_structure": {}
            }
            
            if isinstance(flights, list) and len(flights) > 0:
                first_flight = flights[0]
                response["flights_analysis"]["first_flight_structure"] = {
                    "type": str(type(first_flight)),
                    "keys": list(first_flight.keys()) if isinstance(first_flight, dict) else "not dict"
                }
                
                # Анализируем структуру forward/backward
                if isinstance(first_flight, dict):
                    for direction in ["forward", "backward"]:
                        if direction in first_flight:
                            segments = first_flight[direction]
                            response["flights_analysis"][f"{direction}_analysis"] = {
                                "type": str(type(segments)),
                                "count": len(segments) if isinstance(segments, list) else "not list"
                            }
                            
                            if isinstance(segments, list) and len(segments) > 0:
                                first_segment = segments[0]
                                response["flights_analysis"][f"{direction}_segment_structure"] = {
                                    "type": str(type(first_segment)),
                                    "keys": list(first_segment.keys()) if isinstance(first_segment, dict) else "not dict"
                                }
                                
                                # Анализируем departure/arrival
                                if isinstance(first_segment, dict):
                                    for point in ["departure", "arrival"]:
                                        if point in first_segment:
                                            point_data = first_segment[point]
                                            response["flights_analysis"][f"{direction}_{point}_structure"] = {
                                                "type": str(type(point_data)),
                                                "keys": list(point_data.keys()) if isinstance(point_data, dict) else "not dict"
                                            }
                                            
                                            # Анализируем port
                                            if isinstance(point_data, dict) and "port" in point_data:
                                                port_data = point_data["port"]
                                                response["flights_analysis"][f"{direction}_{point}_port"] = {
                                                    "type": str(type(port_data)),
                                                    "value": port_data,
                                                    "keys": list(port_data.keys()) if isinstance(port_data, dict) else "not dict"
                                                }
        
        return response
        
    except Exception as e:
        logger.error(f"🐛 RAW DEBUG ERROR: {e}")
        return {
            "error": str(e),
            "error_type": str(type(e)),
            "tour_id": request.tour_id
        }

@router.get("/test-random-search")
async def test_random_search():
    """
    Тестирование генерации случайных туров
    """
    try:
        logger.info("🧪 Тестирование генерации случайных туров")
        
        test_request = RandomTourRequest(count=3)
        result = await random_tours_service.get_random_tours(test_request)
        
        return {
            "success": True,
            "tours_generated": len(result),
            "sample_tours": [
                {
                    "hotel_name": tour.hotelname,
                    "country": tour.countryname,
                    "price": tour.price,
                    "operator": tour.operatorname
                }
                for tour in result[:3]
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка тестирования случайных туров: {e}")
        return {
            "success": False,
            "error": str(e)
        }

@router.get("/test-api-connection")
async def test_api_connection():
    """
    Тестирование подключения к TourVisor API
    """
    try:
        logger.info("🧪 Тестирование подключения к TourVisor API")
        
        # Тестируем получение справочника
        countries_data = await tourvisor_client.get_references("country")
        regions_data = await tourvisor_client.get_references("region", regcountry=1)
        
        return {
            "success": True,
            "message": "API TourVisor работает",
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