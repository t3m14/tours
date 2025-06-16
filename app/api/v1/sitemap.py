from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any
import asyncio

from app.core.tourvisor_client import tourvisor_client
from app.core.transliteration import transliterator
from app.services.cache_service import cache_service
from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()

@router.get("")
async def get_sitemap(
    type: str = Query(..., description="Тип sitemap: hotels, countries, regions")
):
    """
    Получение sitemap для различных типов контента
    
    Поддерживаемые типы:
    - hotels: список URL отелей
    - countries: список URL стран
    - regions: список URL курортов
    """
    try:
        if type == "hotels":
            return await _get_hotels_sitemap()
        elif type == "countries":
            return await _get_countries_sitemap()
        elif type == "regions":
            return await _get_regions_sitemap()
        else:
            raise HTTPException(
                status_code=400,
                detail="Поддерживаемые типы: hotels, countries, regions"
            )
    except Exception as e:
        logger.error(f"Ошибка при генерации sitemap типа {type}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def _get_hotels_sitemap() -> Dict[str, List[str]]:
    """Генерация sitemap для отелей"""
    cache_key = "sitemap_hotels"
    
    # Проверяем кэш
    cached_sitemap = await cache_service.get(cache_key)
    if cached_sitemap:
        return cached_sitemap
    
    hotels_urls = []
    
    try:
        # Получаем список популярных стран
        for country_code in settings.POPULAR_COUNTRIES:
            logger.info(f"Получение отелей для страны {country_code}")
            
            # Получаем отели для страны
            hotels_data = await tourvisor_client.get_references(
                "hotel",
                hotcountry=country_code
            )
            
            hotels = hotels_data.get("hotel", [])
            if not isinstance(hotels, list):
                hotels = [hotels] if hotels else []
            
            # Генерируем URL для каждого отеля
            for hotel in hotels:
                hotel_name = hotel.get("name", "")
                hotel_id = hotel.get("id", "")
                
                if hotel_name and hotel_id:
                    hotel_url = transliterator.to_hotel_url(hotel_name, hotel_id)
                    if hotel_url:  # Проверяем, что URL не пустой
                        hotels_urls.append(f"/hotels/{hotel_url}")
            
            # Добавляем небольшую задержку между запросами
            await asyncio.sleep(0.2)
        
        # Убираем дубликаты и сортируем
        hotels_urls = sorted(list(set(hotels_urls)))
        
        result = {
            "type": "hotels",
            "count": len(hotels_urls),
            "urls": hotels_urls
        }
        
        # Кэшируем результат на 6 часов
        await cache_service.set(cache_key, result, ttl=21600)
        
        logger.info(f"Сгенерировано {len(hotels_urls)} URL отелей")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при генерации sitemap отелей: {e}")
        # Возвращаем пустой результат в случае ошибки
        return {"type": "hotels", "count": 0, "urls": []}

async def _get_countries_sitemap() -> Dict[str, List[str]]:
    """Генерация sitemap для стран"""
    cache_key = "sitemap_countries"
    
    cached_sitemap = await cache_service.get(cache_key)
    if cached_sitemap:
        return cached_sitemap
    
    try:
        # Получаем список всех стран
        countries_data = await tourvisor_client.get_references("country")
        countries = countries_data.get("country", [])
        
        if not isinstance(countries, list):
            countries = [countries] if countries else []
        
        countries_urls = []
        for country in countries:
            country_name = country.get("name", "")
            country_id = country.get("id", "")
            
            if country_name and country_id:
                country_url = transliterator.to_url_slug(country_name)
                if country_url:
                    countries_urls.append(f"/countries/{country_url}")
        
        countries_urls = sorted(list(set(countries_urls)))
        
        result = {
            "type": "countries",
            "count": len(countries_urls),
            "urls": countries_urls
        }
        
        # Кэшируем на 24 часа
        await cache_service.set(cache_key, result, ttl=86400)
        
        logger.info(f"Сгенерировано {len(countries_urls)} URL стран")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при генерации sitemap стран: {e}")
        return {"type": "countries", "count": 0, "urls": []}

async def _get_regions_sitemap() -> Dict[str, List[str]]:
    """Генерация sitemap для курортов"""
    cache_key = "sitemap_regions"
    
    cached_sitemap = await cache_service.get(cache_key)
    if cached_sitemap:
        return cached_sitemap
    
    try:
        # Получаем список всех курортов
        regions_data = await tourvisor_client.get_references("region")
        regions = regions_data.get("region", [])
        
        if not isinstance(regions, list):
            regions = [regions] if regions else []
        
        regions_urls = []
        for region in regions:
            region_name = region.get("name", "")
            region_id = region.get("id", "")
            
            if region_name and region_id:
                region_url = transliterator.to_url_slug(region_name)
                if region_url:
                    regions_urls.append(f"/regions/{region_url}")
        
        regions_urls = sorted(list(set(regions_urls)))
        
        result = {
            "type": "regions",
            "count": len(regions_urls),
            "urls": regions_urls
        }
        
        # Кэшируем на 24 часа
        await cache_service.set(cache_key, result, ttl=86400)
        
        logger.info(f"Сгенерировано {len(regions_urls)} URL курортов")
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при генерации sitemap курортов: {e}")
        return {"type": "regions", "count": 0, "urls": []}

@router.get("/refresh")
async def refresh_sitemap(
    type: str = Query(..., description="Тип sitemap для обновления: hotels, countries, regions, all")
):
    """
    Принудительное обновление sitemap
    """
    try:
        refreshed_types = []
        
        if type == "all" or type == "hotels":
            await cache_service.delete("sitemap_hotels")
            await _get_hotels_sitemap()
            refreshed_types.append("hotels")
        
        if type == "all" or type == "countries":
            await cache_service.delete("sitemap_countries")
            await _get_countries_sitemap()
            refreshed_types.append("countries")
        
        if type == "all" or type == "regions":
            await cache_service.delete("sitemap_regions")
            await _get_regions_sitemap()
            refreshed_types.append("regions")
        
        return {
            "success": True,
            "message": f"Sitemap обновлен для типов: {', '.join(refreshed_types)}"
        }
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении sitemap: {e}")
        raise HTTPException(status_code=500, detail=str(e))