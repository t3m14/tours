from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import asyncio
from datetime import datetime, timedelta

from app.core.tourvisor_client import tourvisor_client
from app.tasks.random_tours_cache_update import random_tours_cache_update_service
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/debug-tours", tags=["Debug Tours"])

@router.get("/test-search-extraction/{hotel_type}")
async def test_search_extraction(hotel_type: str) -> Dict[str, Any]:
    """
    Тестирование извлечения туров из поиска для отладки
    """
    try:
        if hotel_type not in random_tours_cache_update_service.hotel_types_mapping:
            raise HTTPException(status_code=400, detail=f"Неизвестный тип отеля: {hotel_type}")
        
        hotel_type_info = random_tours_cache_update_service.hotel_types_mapping[hotel_type]
        api_param = hotel_type_info["api_param"]
        
        logger.info(f"🔍 ДИАГНОСТИКА извлечения туров для {hotel_type}")
        
        # Простой поиск туров
        tomorrow = datetime.now() + timedelta(days=1)
        week_later = datetime.now() + timedelta(days=8)
        
        search_params = {
            "departure": 1,  # Москва
            "country": 4,    # Турция (должна дать результаты)
            "datefrom": tomorrow.strftime("%d.%m.%Y"),
            "dateto": week_later.strftime("%d.%m.%Y"),
            "nightsfrom": 7,
            "nightsto": 10,
            "adults": 2,
            "format": "xml",
            "onpage": 10
        }
        
        if api_param:
            search_params["hoteltypes"] = api_param
        
        # Запуск поиска
        logger.info(f"🚀 Запуск диагностического поиска с параметрами: {search_params}")
        request_id = await tourvisor_client.search_tours(search_params)
        
        # Ждем 15 секунд
        logger.info(f"⏰ Ожидание 15 секунд для завершения поиска {request_id}")
        await asyncio.sleep(15)
        
        # Получаем статус
        status_result = await tourvisor_client.get_search_status(request_id)
        logger.info(f"📊 Статус поиска: {status_result}")
        
        # Получаем результаты
        search_results = await tourvisor_client.get_search_results(request_id)
        logger.info(f"📥 Получены результаты поиска")
        
        # Анализ структуры
        structure_analysis = {
            "request_id": request_id,
            "search_params_used": search_params,
            "status_response": status_result,
            "results_top_level_keys": list(search_results.keys()),
            "results_type": type(search_results).__name__
        }
        
        # Детальный анализ data
        if "data" in search_results:
            data = search_results["data"]
            structure_analysis["data_type"] = type(data).__name__
            
            if isinstance(data, dict):
                structure_analysis["data_keys"] = list(data.keys())
                
                # Анализ result
                if "result" in data:
                    result = data["result"]
                    structure_analysis["result_type"] = type(result).__name__
                    
                    if isinstance(result, dict):
                        structure_analysis["result_keys"] = list(result.keys())
                        
                        # Анализ hotel
                        if "hotel" in result:
                            hotels = result["hotel"]
                            structure_analysis["hotels_type"] = type(hotels).__name__
                            structure_analysis["hotels_count"] = len(hotels) if isinstance(hotels, list) else (1 if hotels else 0)
                            
                            # Анализ первого отеля
                            if hotels:
                                first_hotel = hotels[0] if isinstance(hotels, list) else hotels
                                if isinstance(first_hotel, dict):
                                    structure_analysis["first_hotel_keys"] = list(first_hotel.keys())
                                    structure_analysis["first_hotel_name"] = first_hotel.get("hotelname", "Unknown")
                                    
                                    # Анализ туров в отеле
                                    if "tours" in first_hotel:
                                        tours_block = first_hotel["tours"]
                                        structure_analysis["tours_block_type"] = type(tours_block).__name__
                                        
                                        if isinstance(tours_block, dict) and "tour" in tours_block:
                                            tours = tours_block["tour"]
                                            structure_analysis["tours_type"] = type(tours).__name__
                                            structure_analysis["tours_count"] = len(tours) if isinstance(tours, list) else (1 if tours else 0)
                                            
                                            # Анализ первого тура
                                            if tours:
                                                first_tour = tours[0] if isinstance(tours, list) else tours
                                                if isinstance(first_tour, dict):
                                                    structure_analysis["first_tour_keys"] = list(first_tour.keys())
                                                    structure_analysis["first_tour_price"] = first_tour.get("price", "No price")
        
        # Пробуем извлечь туры через наш метод
        try:
            extracted_tours = await random_tours_cache_update_service._extract_tours_from_search_results(
                search_results, 5, hotel_type
            )
            extraction_result = {
                "success": True,
                "extracted_count": len(extracted_tours),
                "extracted_tours": extracted_tours[:2] if extracted_tours else []  # Первые 2 тура
            }
        except Exception as extraction_error:
            extraction_result = {
                "success": False,
                "error": str(extraction_error),
                "traceback": str(extraction_error.__traceback__)
            }
        
        return {
            "success": True,
            "hotel_type": hotel_type,
            "api_param": api_param,
            "structure_analysis": structure_analysis,
            "extraction_result": extraction_result,
            "raw_results_sample": str(search_results)[:2000] + "..." if len(str(search_results)) > 2000 else str(search_results)
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка диагностики: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/raw-search/{country_id}")
async def get_raw_search_results(country_id: int = 4) -> Dict[str, Any]:
    """
    Получение сырых результатов поиска для анализа
    """
    try:
        tomorrow = datetime.now() + timedelta(days=1)
        week_later = datetime.now() + timedelta(days=8)
        
        search_params = {
            "departure": 1,
            "country": country_id,
            "datefrom": tomorrow.strftime("%d.%m.%Y"),
            "dateto": week_later.strftime("%d.%m.%Y"),
            "nightsfrom": 7,
            "nightsto": 10,
            "adults": 2,
            "format": "xml",
            "onpage": 5
        }
        
        # Запуск поиска
        request_id = await tourvisor_client.search_tours(search_params)
        logger.info(f"🚀 Raw поиск запущен: {request_id}")
        
        # Ждем 10 секунд
        await asyncio.sleep(10)
        
        # Получаем результаты
        search_results = await tourvisor_client.get_search_results(request_id)
        
        return {
            "success": True,
            "request_id": request_id,
            "search_params": search_params,
            "raw_results": search_results
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка raw поиска: {e}")
        raise HTTPException(status_code=500, detail=str(e))