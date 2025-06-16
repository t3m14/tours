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
from app.core.tourvisor_client import tourvisor_client
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()

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

@router.get("/random", response_model=List[HotTourInfo])
async def get_random_tours_get(
    count: int = Query(6, ge=1, le=20, description="Количество случайных туров")
):
    """
    Получение случайных туров через обычный поиск
    
    Использует реальный поиск туров вместо горящих туров
    """
    try:
        request = RandomTourRequest(count=count)
        logger.info(f"🎯 Запрос {request.count} случайных туров через поиск")
        
        result = await tour_service.get_random_tours(request)
        logger.info(f"✅ Возвращено {len(result)} туров через поиск")
        
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка при получении случайных туров: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/random", response_model=List[HotTourInfo])
async def get_random_tours_post(request: RandomTourRequest = None):
    """
    Получение случайных туров через обычный поиск (POST)
    
    Использует реальный поиск туров вместо горящих туров
    """
    try:
        if request is None:
            request = RandomTourRequest()
        
        logger.info(f"🎯 POST запрос {request.count} случайных туров через поиск")
        
        result = await tour_service.get_random_tours(request)
        logger.info(f"✅ Возвращено {len(result)} туров через поиск")
        
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка при получении случайных туров: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/random/generate", response_model=List[HotTourInfo])
async def generate_random_tours(
    count: int = Query(6, ge=1, le=20, description="Количество случайных туров")
):
    """
    Принудительная генерация новых случайных туров через поиск (без кэша)
    """
    try:
        logger.info(f"🔄 Принудительная генерация {count} туров через поиск")
        
        result = await tour_service._generate_random_tours_via_search(count)
        logger.info(f"✅ Сгенерировано {len(result)} туров")
        
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка при генерации туров: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/random/mock", response_model=List[HotTourInfo])
async def get_mock_random_tours(
    count: int = Query(6, ge=1, le=20, description="Количество туров")
):
    """
    Mock случайных туров для тестирования фронтенда
    (используется как fallback)
    """
    try:
        mock_tours = [
            {
                "countrycode": "1",
                "countryname": "Египет",
                "departurecode": "1", 
                "departurename": "Москва",
                "departurenamefrom": "Москвы",
                "operatorcode": "16",
                "operatorname": "Sunmar",
                "hotelcode": "470",
                "hotelname": "SULTANA BEACH RESORT",
                "hotelstars": 3,
                "hotelregioncode": "5",
                "hotelregionname": "Хургада",
                "hotelpicture": "https://via.placeholder.com/250x150/4a90e2/ffffff?text=Hotel+1",
                "fulldesclink": "https://example.com/hotel/470",
                "flydate": "20.06.2025",
                "nights": 7,
                "meal": "All Inclusive",
                "price": 45000.0,
                "priceold": 52000.0,
                "currency": "RUB"
            },
            {
                "countrycode": "4",
                "countryname": "Турция",
                "departurecode": "1",
                "departurename": "Москва", 
                "departurenamefrom": "Москвы",
                "operatorcode": "23",
                "operatorname": "Anex Tour",
                "hotelcode": "234",
                "hotelname": "CLUB HOTEL SERA",
                "hotelstars": 5,
                "hotelregioncode": "12",
                "hotelregionname": "Анталья",
                "hotelpicture": "https://via.placeholder.com/250x150/e74c3c/ffffff?text=Hotel+2",
                "fulldesclink": "https://example.com/hotel/234",
                "flydate": "22.06.2025",
                "nights": 10,
                "meal": "Ultra All Inclusive",
                "price": 68000.0,
                "priceold": 75000.0,
                "currency": "RUB"
            },
            {
                "countrycode": "22",
                "countryname": "Таиланд",
                "departurecode": "2",
                "departurename": "Санкт-Петербург",
                "departurenamefrom": "Санкт-Петербурга", 
                "operatorcode": "45",
                "operatorname": "Pegas Touristik",
                "hotelcode": "567",
                "hotelname": "PHUKET PARADISE RESORT",
                "hotelstars": 4,
                "hotelregioncode": "34",
                "hotelregionname": "Пхукет",
                "hotelpicture": "https://via.placeholder.com/250x150/2ecc71/ffffff?text=Hotel+3",
                "fulldesclink": "https://example.com/hotel/567",
                "flydate": "25.06.2025",
                "nights": 12,
                "meal": "Завтраки",
                "price": 95000.0,
                "priceold": 110000.0,
                "currency": "RUB"
            },
            {
                "countrycode": "15",
                "countryname": "ОАЭ",
                "departurecode": "1",
                "departurename": "Москва",
                "departurenamefrom": "Москвы",
                "operatorcode": "67",
                "operatorname": "Coral Travel",
                "hotelcode": "789",
                "hotelname": "ATLANTIS THE PALM",
                "hotelstars": 5,
                "hotelregioncode": "56",
                "hotelregionname": "Дубай",
                "hotelpicture": "https://via.placeholder.com/250x150/f39c12/ffffff?text=Hotel+4",
                "fulldesclink": "https://example.com/hotel/789",
                "flydate": "28.06.2025",
                "nights": 5,
                "meal": "Полупансион",
                "price": 125000.0,
                "priceold": 140000.0,
                "currency": "RUB"
            },
            {
                "countrycode": "8",
                "countryname": "Греция",
                "departurecode": "3",
                "departurename": "Екатеринбург",
                "departurenamefrom": "Екатеринбурга",
                "operatorcode": "89",
                "operatorname": "TEZ TOUR",
                "hotelcode": "345",
                "hotelname": "BLUE PALACE RESORT",
                "hotelstars": 4,
                "hotelregioncode": "78",
                "hotelregionname": "Крит",
                "hotelpicture": "https://via.placeholder.com/250x150/9b59b6/ffffff?text=Hotel+5",
                "fulldesclink": "https://example.com/hotel/345",
                "flydate": "30.06.2025",
                "nights": 8,
                "meal": "All Inclusive",
                "price": 58000.0,
                "priceold": 65000.0,
                "currency": "RUB"
            },
            {
                "countrycode": "35",
                "countryname": "Мальдивы",
                "departurecode": "1",
                "departurename": "Москва",
                "departurenamefrom": "Москвы",
                "operatorcode": "12",
                "operatorname": "ICS Travel Group",
                "hotelcode": "901",
                "hotelname": "SUN ISLAND RESORT",
                "hotelstars": 5,
                "hotelregioncode": "90",
                "hotelregionname": "Южный Мале Атолл",
                "hotelpicture": "https://via.placeholder.com/250x150/1abc9c/ffffff?text=Hotel+6",
                "fulldesclink": "https://example.com/hotel/901",
                "flydate": "02.07.2025",
                "nights": 9,
                "meal": "Полный пансион",
                "price": 180000.0,
                "priceold": 200000.0,
                "currency": "RUB"
            }
        ]
        
        # Возвращаем запрошенное количество туров
        selected_tours = mock_tours[:count]
        
        # Преобразуем в объекты HotTourInfo
        result = []
        for tour_data in selected_tours:
            try:
                tour = HotTourInfo(**tour_data)
                result.append(tour)
            except Exception as e:
                logger.warning(f"Ошибка при создании mock тура: {e}")
                continue
        
        logger.info(f"Возвращено {len(result)} mock туров")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при создании mock туров: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/random/mock-with-real-data", response_model=List[HotTourInfo])
async def get_mock_tours_with_real_data(
    count: int = Query(6, ge=1, le=20, description="Количество туров")
):
    """
    Mock туры на основе реальных справочников TourVisor
    """
    try:
        logger.info(f"🎭 Создание {count} mock туров на основе реальных данных")
        
        # Получаем реальные справочники
        countries_data = await tourvisor_client.get_references("country")
        departures_data = await tourvisor_client.get_references("departure")
        
        countries_list = countries_data.get("lists", {}).get("countries", {}).get("country", [])
        departures_list = departures_data.get("lists", {}).get("departures", {}).get("departure", [])
        
        # Создаем mock туры
        mock_tours = []
        popular_countries = ["Египет", "Турция", "Таиланд", "ОАЭ", "Греция", "Кипр", "Испания", "Италия"]
        popular_cities = ["Москва", "С.Петербург", "Екатеринбург", "Казань", "Новосибирск"]
        
        for i in range(count):
            # Выбираем случайные данные из реальных справочников
            country_name = popular_countries[i % len(popular_countries)]
            city_name = popular_cities[i % len(popular_cities)]
            
            # Находим реальные коды
            country_code = None
            for country in countries_list:
                if country.get("name") == country_name:
                    country_code = country.get("id")
                    break
            
            city_code = None
            city_name_from = None
            for departure in departures_list:
                if departure.get("name") == city_name:
                    city_code = departure.get("id")
                    city_name_from = departure.get("namefrom")
                    break
            
            # Генерируем mock данные
            base_price = 35000 + (i * 12000) + random.randint(-5000, 15000)
            
            mock_tour = {
                "countrycode": country_code or str(i + 1),
                "countryname": country_name,
                "departurecode": city_code or str((i % 5) + 1),
                "departurename": city_name,
                "departurenamefrom": city_name_from or f"{city_name[:-1]}ы" if city_name.endswith('а') else f"{city_name}а",
                "operatorcode": str(i + 10),
                "operatorname": f"Оператор {i+1}",
                "hotelcode": str(100 + i),
                "hotelname": f"HOTEL {country_name.upper()} RESORT {i+1}",
                "hotelstars": 3 + (i % 3),
                "hotelregioncode": str(50 + i),
                "hotelregionname": f"Курорт {country_name}",
                "hotelpicture": f"https://via.placeholder.com/250x150/{['4a90e2', 'e74c3c', '2ecc71', 'f39c12', '9b59b6', '1abc9c', 'e67e22', '34495e'][i % 8]}/ffffff?text=Hotel+{i+1}",
                "fulldesclink": f"https://example.com/hotel/{100+i}",
                "flydate": (datetime.now() + timedelta(days=7 + i)).strftime("%d.%m.%Y"),
                "nights": 7 + (i % 8),
                "meal": ["Завтраки", "Полупансион", "All Inclusive", "Ultra All Inclusive", "Полный пансион"][i % 5],
                "price": float(base_price),
                "priceold": float(base_price + random.randint(3000, 8000)),
                "currency": "RUB"
            }
            
            mock_tours.append(HotTourInfo(**mock_tour))
        
        logger.info(f"✅ Создано {len(mock_tours)} mock туров на основе реальных справочников")
        return mock_tours
        
    except Exception as e:
        logger.error(f"❌ Ошибка при создании mock туров: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/random/status")
async def get_random_tours_system_status():
    """
    Проверка статуса системы случайных туров
    """
    try:
        # Проверяем кэш
        cached_tours = await tour_service.cache.get("random_tours_from_search")
        
        # Проверяем работу поиска
        search_working = False
        try:
            test_params = {
                "departure": 1,
                "country": 1,
                "datefrom": (datetime.now() + timedelta(days=7)).strftime("%d.%m.%Y"),
                "dateto": (datetime.now() + timedelta(days=14)).strftime("%d.%m.%Y"),
                "nightsfrom": 7,
                "nightsto": 10,
                "adults": 2,
                "child": 0
            }
            test_request_id = await tourvisor_client.search_tours(test_params)
            search_working = bool(test_request_id)
        except:
            pass
        
        return {
            "cache": {
                "has_data": bool(cached_tours),
                "tours_count": len(cached_tours) if cached_tours else 0,
                "cache_key": "random_tours_from_search"
            },
            "search_system": {
                "working": search_working,
                "method": "regular_search_instead_of_hot_tours"
            },
            "recommendations": {
                "primary_endpoint": "/api/v1/tours/random",
                "fallback_endpoint": "/api/v1/tours/random/mock",
                "force_regenerate": "/api/v1/tours/random/generate"
            }
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "recommendation": "use_mock_endpoint"
        }

@router.get("/test-search")
async def test_search_functionality():
    """
    Тестирование функциональности поиска туров
    """
    try:
        # Создаем тестовый поисковый запрос
        search_params = {
            "departure": 1,  # Москва
            "country": 1,    # Египет
            "datefrom": (datetime.now() + timedelta(days=7)).strftime("%d.%m.%Y"),
            "dateto": (datetime.now() + timedelta(days=14)).strftime("%d.%m.%Y"),
            "nightsfrom": 7,
            "nightsto": 10,
            "adults": 2,
            "child": 0
        }
        
        logger.info(f"🧪 Тестируем поиск с параметрами: {search_params}")
        
        # 1. Запускаем поиск
        request_id = await tourvisor_client.search_tours(search_params)
        logger.info(f"📝 Получен request_id: {request_id}")
        
        # 2. Проверяем статус несколько раз
        statuses = []
        for i in range(5):
            await asyncio.sleep(1)
            status_result = await tourvisor_client.get_search_status(request_id)
            status_data = status_result.get("data", {}).get("status", {})
            statuses.append({
                "attempt": i + 1,
                "state": status_data.get("state"),
                "progress": status_data.get("progress"),
                "hotels_found": status_data.get("hotelsfound"),
                "tours_found": status_data.get("toursfound"),
                "min_price": status_data.get("minprice")
            })
            
            if status_data.get("state") == "finished":
                break
        
        # 3. Получаем результаты
        results = await tourvisor_client.get_search_results(request_id, 1, 5)
        
        return {
            "success": True,
            "search_params": search_params,
            "request_id": request_id,
            "status_progression": statuses,
            "final_results": {
                "has_data": bool(results.get("data")),
                "has_hotels": bool(results.get("data", {}).get("result", {}).get("hotel")),
                "sample_keys": list(results.keys()) if results else []
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка при тестировании поиска: {e}")
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

@router.get("/directions", response_model=List[DirectionInfo])
async def get_directions():
    """
    Получение списка направлений с минимальными ценами
    
    Теперь использует обычный поиск вместо горящих туров
    """
    try:
        logger.info("🌍 Получение направлений через поиск")
        result = await tour_service.get_directions_with_prices()
        logger.info(f"✅ Получено {len(result)} направлений")
        return result
    except Exception as e:
        logger.error(f"❌ Ошибка при получении направлений: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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