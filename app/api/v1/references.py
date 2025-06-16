from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional

from app.core.tourvisor_client import tourvisor_client
from app.services.cache_service import cache_service
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()

@router.get("/departure")
async def get_departure_cities() -> Dict[str, Any]:
    """
    Получение списка городов вылета
    """
    try:
        cache_key = "reference:departure"
        
        # Проверяем кэш
        cached_data = await cache_service.get(cache_key)
        if cached_data:
            return cached_data
        
        # Получаем данные от TourVisor
        data = await tourvisor_client.get_references("departure")
        
        # Кэшируем на 24 часа
        await cache_service.set(cache_key, data, ttl=86400)
        
        return data
        
    except Exception as e:
        logger.error(f"Ошибка при получении городов вылета: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/countries")
async def get_countries(
    departure_city: Optional[int] = Query(None, description="Код города вылета для фильтрации")
) -> Dict[str, Any]:
    """
    Получение списка стран
    
    Если указан departure_city, возвращает только страны с вылетами из этого города
    """
    try:
        if departure_city:
            cache_key = f"reference:countries_from_{departure_city}"
            
            cached_data = await cache_service.get(cache_key)
            if cached_data:
                return cached_data
            
            data = await tourvisor_client.get_references("country", cndep=departure_city)
        else:
            cache_key = "reference:country"
            
            cached_data = await cache_service.get(cache_key)
            if cached_data:
                return cached_data
            
            data = await tourvisor_client.get_references("country")
        
        # Кэшируем на 24 часа
        await cache_service.set(cache_key, data, ttl=86400)
        
        return data
        
    except Exception as e:
        logger.error(f"Ошибка при получении стран: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/regions")
async def get_regions(
    country_code: Optional[int] = Query(None, description="Код страны для фильтрации")
) -> Dict[str, Any]:
    """
    Получение списка курортов
    
    Если указан country_code, возвращает только курорты этой страны
    """
    try:
        if country_code:
            cache_key = f"reference:regions_country_{country_code}"
            
            cached_data = await cache_service.get(cache_key)
            if cached_data:
                return cached_data
            
            data = await tourvisor_client.get_references("region", regcountry=country_code)
        else:
            cache_key = "reference:region"
            
            cached_data = await cache_service.get(cache_key)
            if cached_data:
                return cached_data
            
            data = await tourvisor_client.get_references("region")
        
        # Кэшируем на 24 часа
        await cache_service.set(cache_key, data, ttl=86400)
        
        return data
        
    except Exception as e:
        logger.error(f"Ошибка при получении курортов: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/subregions")
async def get_subregions(
    country_code: Optional[int] = Query(None, description="Код страны для фильтрации")
) -> Dict[str, Any]:
    """
    Получение списка вложенных курортов (районов)
    """
    try:
        if country_code:
            cache_key = f"reference:subregions_country_{country_code}"
            
            cached_data = await cache_service.get(cache_key)
            if cached_data:
                return cached_data
            
            data = await tourvisor_client.get_references("subregion", regcountry=country_code)
        else:
            cache_key = "reference:subregion"
            
            cached_data = await cache_service.get(cache_key)
            if cached_data:
                return cached_data
            
            data = await tourvisor_client.get_references("subregion")
        
        # Кэшируем на 24 часа
        await cache_service.set(cache_key, data, ttl=86400)
        
        return data
        
    except Exception as e:
        logger.error(f"Ошибка при получении вложенных курортов: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/meal-types")
async def get_meal_types() -> Dict[str, Any]:
    """
    Получение списка типов питания
    """
    try:
        cache_key = "reference:meal"
        
        cached_data = await cache_service.get(cache_key)
        if cached_data:
            return cached_data
        
        data = await tourvisor_client.get_references("meal")
        
        # Кэшируем на 24 часа
        await cache_service.set(cache_key, data, ttl=86400)
        
        return data
        
    except Exception as e:
        logger.error(f"Ошибка при получении типов питания: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/hotel-categories")
async def get_hotel_categories() -> Dict[str, Any]:
    """
    Получение списка категорий отелей (звездность)
    """
    try:
        cache_key = "reference:stars"
        
        cached_data = await cache_service.get(cache_key)
        if cached_data:
            return cached_data
        
        data = await tourvisor_client.get_references("stars")
        
        # Кэшируем на 24 часа
        await cache_service.set(cache_key, data, ttl=86400)
        
        return data
        
    except Exception as e:
        logger.error(f"Ошибка при получении категорий отелей: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/operators")
async def get_operators(
    departure_city: Optional[int] = Query(None, description="Код города вылета"),
    country_code: Optional[int] = Query(None, description="Код страны")
) -> Dict[str, Any]:
    """
    Получение списка туроператоров
    
    Можно фильтровать по городу вылета и стране
    """
    try:
        # Формируем ключ кэша
        cache_parts = ["reference", "operator"]
        if departure_city:
            cache_parts.append(f"dep_{departure_city}")
        if country_code:
            cache_parts.append(f"country_{country_code}")
        
        cache_key = ":".join(cache_parts)
        
        cached_data = await cache_service.get(cache_key)
        if cached_data:
            return cached_data
        
        # Формируем параметры запроса
        params = {}
        if departure_city:
            params["flydeparture"] = departure_city
        if country_code:
            params["flycountry"] = country_code
        
        data = await tourvisor_client.get_references("operator", **params)
        
        # Кэшируем на 24 часа
        await cache_service.set(cache_key, data, ttl=86400)
        
        return data
        
    except Exception as e:
        logger.error(f"Ошибка при получении туроператоров: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/hotel-services")
async def get_hotel_services() -> Dict[str, Any]:
    """
    Получение списка услуг в отелях
    """
    try:
        cache_key = "reference:services"
        
        cached_data = await cache_service.get(cache_key)
        if cached_data:
            return cached_data
        
        data = await tourvisor_client.get_references("services")
        
        # Кэшируем на 24 часа
        await cache_service.set(cache_key, data, ttl=86400)
        
        return data
        
    except Exception as e:
        logger.error(f"Ошибка при получении услуг отелей: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/flight-dates")
async def get_flight_dates(
    departure_city: int = Query(..., description="Код города вылета"),
    country_code: int = Query(..., description="Код страны")
) -> Dict[str, Any]:
    """
    Получение списка доступных дат вылета для календаря
    """
    try:
        cache_key = f"reference:flydate_{departure_city}_{country_code}"
        
        cached_data = await cache_service.get(cache_key)
        if cached_data:
            return cached_data
        
        data = await tourvisor_client.get_references(
            "flydate",
            flydeparture=departure_city,
            flycountry=country_code
        )
        
        # Кэшируем на 6 часов (даты могут изменяться чаще)
        await cache_service.set(cache_key, data, ttl=21600)
        
        return data
        
    except Exception as e:
        logger.error(f"Ошибка при получении дат вылета: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/currency-rates")
async def get_currency_rates() -> Dict[str, Any]:
    """
    Получение курсов валют туроператоров
    """
    try:
        cache_key = "reference:currency"
        
        cached_data = await cache_service.get(cache_key)
        if cached_data:
            return cached_data
        
        data = await tourvisor_client.get_references("currency")
        
        # Кэшируем на 1 час (курсы могут изменяться часто)
        await cache_service.set(cache_key, data, ttl=3600)
        
        return data
        
    except Exception as e:
        logger.error(f"Ошибка при получении курсов валют: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/refresh")
async def refresh_references():
    """
    Принудительное обновление всех справочников
    """
    try:
        # Удаляем все справочники из кэша
        reference_keys = await cache_service.get_keys_pattern("reference:*")
        
        for key in reference_keys:
            await cache_service.delete(key)
        
        logger.info(f"Удалено {len(reference_keys)} справочников из кэша")
        
        return {
            "success": True,
            "message": f"Обновлено {len(reference_keys)} справочников"
        }
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении справочников: {e}")
        raise HTTPException(status_code=500, detail=str(e))