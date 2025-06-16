from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List, Optional

from app.core.tourvisor_client import tourvisor_client
from app.services.cache_service import cache_service
from app.services.tour_service import tour_service
from app.models.tour import HotelInfo
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()

@router.get("/list")
async def get_hotels_list(
    country_code: int = Query(..., description="Код страны"),
    region_code: Optional[int] = Query(None, description="Код курорта"),
    stars: Optional[int] = Query(None, description="Минимальная звездность"),
    rating: Optional[float] = Query(None, description="Минимальный рейтинг"),
    hotel_type: Optional[str] = Query(None, description="Тип отеля: active,relax,family,health,city,beach,deluxe")
) -> Dict[str, Any]:
    """
    Получение списка отелей с фильтрацией
    """
    try:
        # Формируем ключ кэша на основе параметров
        cache_parts = [f"hotels_list_country_{country_code}"]
        
        if region_code:
            cache_parts.append(f"region_{region_code}")
        if stars:
            cache_parts.append(f"stars_{stars}")
        if rating:
            cache_parts.append(f"rating_{rating}")
        if hotel_type:
            cache_parts.append(f"type_{hotel_type}")
        
        cache_key = "_".join(cache_parts)
        
        # Проверяем кэш
        cached_data = await cache_service.get(cache_key)
        if cached_data:
            return cached_data
        
        # Формируем параметры для API
        params = {"hotcountry": country_code}
        
        if region_code:
            params["hotregion"] = region_code
        if stars:
            params["hotstars"] = stars
        if rating:
            params["hotrating"] = rating
        
        # Добавляем фильтры по типу отеля
        if hotel_type:
            hotel_type_map = {
                "active": "hotactive",
                "relax": "hotrelax", 
                "family": "hotfamily",
                "health": "hothealth",
                "city": "hotcity",
                "beach": "hotbeach",
                "deluxe": "hotdeluxe"
            }
            
            if hotel_type in hotel_type_map:
                params[hotel_type_map[hotel_type]] = 1
        
        # Получаем данные от TourVisor
        data = await tourvisor_client.get_references("hotel", **params)
        
        # Кэшируем на 6 часов
        await cache_service.set(cache_key, data, ttl=21600)
        
        return data
        
    except Exception as e:
        logger.error(f"Ошибка при получении списка отелей: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{hotel_code}")
async def get_hotel_details(
    hotel_code: str,
    include_reviews: bool = Query(True, description="Включать отзывы"),
    big_images: bool = Query(True, description="Большие изображения (800px)")
) -> Dict[str, Any]:
    """
    Получение детальной информации об отеле
    """
    try:
        cache_key = f"hotel_details_{hotel_code}_reviews_{include_reviews}_big_{big_images}"
        
        # Проверяем кэш
        cached_data = await cache_service.get(cache_key)
        if cached_data:
            return cached_data
        
        # Получаем информацию об отеле
        data = await tourvisor_client.get_hotel_info(hotel_code)
        
        # Кэшируем на 24 часа
        await cache_service.set(cache_key, data, ttl=86400)
        
        return data
        
    except Exception as e:
        logger.error(f"Ошибка при получении информации об отеле {hotel_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{hotel_code}/tours")
async def get_hotel_tours(
    hotel_code: str,
    departure_city: int = Query(1, description="Код города вылета"),
    country_code: int = Query(..., description="Код страны")
) -> List[HotelInfo]:
    """
    Получение туров для конкретного отеля
    """
    try:
        cache_key = f"hotel_tours_{hotel_code}_{departure_city}_{country_code}"
        
        # Проверяем кэш
        cached_data = await cache_service.get(cache_key)
        if cached_data:
            return [HotelInfo(**hotel_data) for hotel_data in cached_data]
        
        # Получаем туры через сервис туров
        from app.models.tour import TourSearchRequest
        
        search_request = TourSearchRequest(
            departure=departure_city,
            country=country_code,
            hotels=hotel_code
        )
        
        # Запускаем поиск
        search_response = await tour_service.search_tours(search_request)
        
        # Ждем завершения поиска (максимум 30 секунд)
        import asyncio
        for _ in range(15):  # 15 попыток по 2 секунды
            await asyncio.sleep(2)
            status = await tour_service.get_search_status(search_response.request_id)
            
            if status.state == "finished":
                break
        
        # Получаем результаты
        search_results = await tour_service.get_search_results(search_response.request_id)
        
        hotels = search_results.result or []
        
        # Кэшируем на 2 часа
        await cache_service.set(
            cache_key,
            [hotel.model_dump() for hotel in hotels],
            ttl=7200
        )
        
        return hotels
        
    except Exception as e:
        logger.error(f"Ошибка при получении туров для отеля {hotel_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/search/by-name")
async def search_hotels_by_name(
    hotel_name: str = Query(..., min_length=3, description="Название отеля для поиска"),
    country_code: int = Query(..., description="Код страны")
) -> List[Dict[str, Any]]:
    """
    Поиск отелей по названию
    """
    try:
        cache_key = f"hotel_search_{hotel_name.lower()}_{country_code}"
        
        # Проверяем кэш
        cached_data = await cache_service.get(cache_key)
        if cached_data:
            return cached_data
        
        # Получаем список всех отелей страны
        hotels_data = await tourvisor_client.get_references(
            "hotel",
            hotcountry=country_code
        )
        
        hotels = hotels_data.get("hotel", [])
        if not isinstance(hotels, list):
            hotels = [hotels] if hotels else []
        
        # Фильтруем по названию
        matching_hotels = []
        search_name = hotel_name.lower()
        
        for hotel in hotels:
            hotel_name_lower = hotel.get("name", "").lower()
            if search_name in hotel_name_lower:
                matching_hotels.append(hotel)
        
        # Сортируем по релевантности (точные совпадения в начале)
        def relevance_score(hotel):
            name = hotel.get("name", "").lower()
            if name == search_name:
                return 0  # Точное совпадение
            elif name.startswith(search_name):
                return 1  # Начинается с поискового запроса
            else:
                return 2  # Содержит поисковый запрос
        
        matching_hotels.sort(key=relevance_score)
        
        # Ограничиваем результаты
        result = matching_hotels[:20]  # Максимум 20 отелей
        
        # Кэшируем на 6 часов
        await cache_service.set(cache_key, result, ttl=21600)
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при поиске отелей по названию: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/hot-tours")
async def get_hot_tours_by_hotels(
    city: int = Query(..., description="Код города вылета"),
    country_code: Optional[int] = Query(None, description="Код страны"),
    region_code: Optional[int] = Query(None, description="Код курорта"),
    stars: Optional[int] = Query(None, description="Минимальная звездность"),
    items: int = Query(10, ge=1, le=50, description="Количество туров")
) -> Dict[str, Any]:
    """
    Получение горящих туров с группировкой по отелям
    """
    try:
        # Формируем ключ кэша
        cache_parts = [f"hot_tours_hotels_city_{city}"]
        
        if country_code:
            cache_parts.append(f"country_{country_code}")
        if region_code:
            cache_parts.append(f"region_{region_code}")
        if stars:
            cache_parts.append(f"stars_{stars}")
        
        cache_parts.append(f"items_{items}")
        cache_key = "_".join(cache_parts)
        
        # Проверяем кэш
        cached_data = await cache_service.get(cache_key)
        if cached_data:
            return cached_data
        
        # Формируем параметры для горящих туров
        params = {"city": city, "items": items}
        
        if country_code:
            params["countries"] = str(country_code)
        if region_code:
            params["regions"] = str(region_code)
        if stars:
            params["stars"] = stars
        
        # Получаем горящие туры
        hot_tours_data = await tourvisor_client.get_hot_tours(**params)
        
        # Группируем по отелям
        hotels_dict = {}
        tours_list = hot_tours_data.get("hottours", [])
        
        for tour in tours_list:
            hotel_code = tour.get("hotelcode")
            
            if hotel_code not in hotels_dict:
                hotels_dict[hotel_code] = {
                    "hotel_code": hotel_code,
                    "hotel_name": tour.get("hotelname"),
                    "hotel_stars": tour.get("hotelstars"),
                    "region_name": tour.get("hotelregionname"),
                    "country_name": tour.get("countryname"),
                    "hotel_picture": tour.get("hotelpicture"),
                    "tours": []
                }
            
            hotels_dict[hotel_code]["tours"].append(tour)
        
        # Сортируем отели по минимальной цене
        hotels_list = list(hotels_dict.values())
        for hotel in hotels_list:
            hotel["min_price"] = min(tour.get("price", float('inf')) for tour in hotel["tours"])
        
        hotels_list.sort(key=lambda x: x["min_price"])
        
        result = {
            "hotels_count": len(hotels_list),
            "total_tours": len(tours_list),
            "hotels": hotels_list
        }
        
        # Кэшируем на 1 час (горящие туры обновляются часто)
        await cache_service.set(cache_key, result, ttl=3600)
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при получении горящих туров по отелям: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/refresh-cache")
async def refresh_hotels_cache(
    country_code: Optional[int] = Query(None, description="Код страны для обновления")
):
    """
    Принудительное обновление кэша отелей
    """
    try:
        if country_code:
            # Удаляем кэш для конкретной страны
            pattern = f"hotels_list_country_{country_code}*"
            hotel_keys = await cache_service.get_keys_pattern(pattern)
            
            pattern2 = f"hotel_details_*"
            detail_keys = await cache_service.get_keys_pattern(pattern2)
            
            all_keys = hotel_keys + detail_keys
        else:
            # Удаляем весь кэш отелей
            patterns = ["hotels_list_*", "hotel_details_*", "hotel_tours_*", "hotel_search_*"]
            all_keys = []
            
            for pattern in patterns:
                keys = await cache_service.get_keys_pattern(pattern)
                all_keys.extend(keys)
        
        # Удаляем ключи
        for key in all_keys:
            await cache_service.delete(key)
        
        logger.info(f"Удалено {len(all_keys)} ключей кэша отелей")
        
        return {
            "success": True,
            "message": f"Обновлен кэш для {len(all_keys)} записей отелей"
        }
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении кэша отелей: {e}")
        raise HTTPException(status_code=500, detail=str(e))