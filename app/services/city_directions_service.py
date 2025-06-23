# app/services/city_directions_service.py

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.services.cache_service import cache_service
from app.services.photo_service import photo_service
from app.services.price_service import price_service
from app.core.tourvisor_client import tourvisor_client
from app.models.tour import DirectionInfo
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class CityDirectionsService:
    """Сервис для работы с направлениями по городам/курортам"""
    
    def __init__(self):
        self.cache = cache_service
        self.photo_service = photo_service
        self.price_service = price_service
        
        # Ключи кэша
        self.CITIES_CACHE_KEY = "city_directions_all"
        self.CACHE_TTL = 7200  # 2 часа
        
    async def get_city_directions(self, country_code: Optional[int] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Получение направлений по городам/курортам
        
        Args:
            country_code: Код страны для фильтрации (None = все страны)
            limit: Максимальное количество результатов
        """
        logger.info(f"🌍 Получение направлений по городам (страна: {country_code}, лимит: {limit})")
        
        try:
            # Формируем ключ кэша
            cache_key = f"{self.CITIES_CACHE_KEY}_{country_code or 'all'}_{limit or 'all'}"
            
            # Проверяем кэш
            cached_data = await self.cache.get(cache_key)
            if cached_data:
                logger.info(f"📦 Возвращено {len(cached_data)} направлений из кэша")
                return cached_data
            
            # Генерируем новые данные
            logger.info("🔄 Генерируем новые данные направлений")
            directions = await self._generate_city_directions(country_code, limit)
            
            # Сохраняем в кэш
            if directions:
                await self.cache.set(cache_key, directions, ttl=self.CACHE_TTL)
                logger.info(f"💾 Сохранено {len(directions)} направлений в кэш")
            
            return directions
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении направлений по городам: {e}")
            return await self._get_fallback_city_directions(country_code, limit)
    
    async def _generate_city_directions(self, country_code: Optional[int] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Генерация направлений по городам"""
        logger.info("🏗️ Начинаем генерацию направлений по городам")
        
        try:
            # Получаем список стран
            if country_code:
                countries_to_process = [{"id": country_code, "name": self._get_country_name(country_code)}]
            else:
                countries_data = await tourvisor_client.get_references("country")
                countries_list = countries_data.get("country", [])
                
                if not isinstance(countries_list, list):
                    countries_list = [countries_list] if countries_list else []
                
                # Фильтруем и валидируем страны
                countries_to_process = []
                for country in countries_list:
                    country_id = country.get("id")
                    country_name = country.get("name")
                    
                    if country_id and country_name:
                        try:
                            countries_to_process.append({
                                "id": int(country_id),
                                "name": country_name
                            })
                        except (ValueError, TypeError):
                            continue
                
                # Сортируем по популярности
                popular_countries = [1, 4, 22, 8, 15, 35]  # Египет, Турция, Таиланд и т.д.
                countries_to_process.sort(key=lambda x: 0 if x["id"] in popular_countries else 1)
                
                # Ограничиваем количество стран если не указана конкретная
                if limit:
                    max_countries = min(limit // 3, 10)  # Примерно 3 города на страну
                    countries_to_process = countries_to_process[:max_countries]
            
            logger.info(f"🌍 Найдено {len(countries_to_process)} валидных стран")
            
            all_directions = []
            
            # Обрабатываем каждую страну
            for country in countries_to_process:
                try:
                    country_directions = await self._get_cities_for_country(country["id"], country["name"])
                    all_directions.extend(country_directions)
                    
                    # Ограничиваем общее количество
                    if limit and len(all_directions) >= limit:
                        all_directions = all_directions[:limit]
                        break
                    
                    # Задержка между странами
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка при обработке страны {country['name']}: {e}")
                    continue
            
            logger.info(f"🏁 Генерация завершена: {len(all_directions)} направлений")
            return all_directions
            
        except Exception as e:
            logger.error(f"❌ Ошибка при генерации направлений: {e}")
            return []
    
    async def _get_cities_for_country(self, country_id: int, country_name: str) -> List[Dict[str, Any]]:
        """Получение городов/курортов для конкретной страны"""
        try:
            logger.debug(f"🏙️ Получение городов для {country_name}")
            
            # Получаем курорты страны
            regions_data = await tourvisor_client.get_references("region", regcountry=country_id)
            regions_list = regions_data.get("region", [])
            
            if not isinstance(regions_list, list):
                regions_list = [regions_list] if regions_list else []
            
            if not regions_list:
                logger.debug(f"⚠️ Нет курортов для {country_name}")
                return []
            
            city_directions = []
            
            # Ограничиваем количество курортов на страну
            max_regions = min(len(regions_list), 5)
            selected_regions = regions_list[:max_regions]
            
            for region in selected_regions:
                try:
                    region_id = region.get("id")
                    region_name = region.get("name")
                    
                    if not region_id or not region_name:
                        continue
                    
                    logger.debug(f"🏖️ Обрабатываем курорт {region_name}")
                    
                    # Получаем фото и цену параллельно
                    photo_task = self.photo_service.get_country_hotel_photo_fast(country_id, country_name)
                    price_task = self.price_service.get_country_min_price(country_id, country_name)
                    
                    try:
                        hotel_photo, min_price = await asyncio.wait_for(
                            asyncio.gather(photo_task, price_task, return_exceptions=True),
                            timeout=10.0
                        )
                    except asyncio.TimeoutError:
                        logger.debug(f"⏰ Таймаут для {region_name}")
                        hotel_photo = None
                        min_price = 50000.0
                    
                    # Обрабатываем возможные исключения
                    if isinstance(hotel_photo, Exception):
                        hotel_photo = None
                    if isinstance(min_price, Exception):
                        min_price = self.price_service.get_default_prices().get(country_id, 50000.0)
                    
                    # Fallback для фото
                    if not hotel_photo:
                        hotel_photo = self.photo_service.get_fallback_image(country_id, region_name)
                    
                    direction = {
                        "id": f"{country_id}_{region_id}",
                        "name": region_name,
                        "country_name": country_name,
                        "country_code": country_id,
                        "region_code": region_id,
                        "image_link": hotel_photo,
                        "min_price": float(min_price),
                        "type": "region"
                    }
                    
                    city_directions.append(direction)
                    logger.debug(f"✅ {region_name}: цена {min_price}")
                    
                    # Задержка между курортами
                    await asyncio.sleep(0.2)
                    
                except Exception as e:
                    logger.debug(f"❌ Ошибка при обработке курорта {region.get('name', 'Unknown')}: {e}")
                    continue
            
            logger.debug(f"🏙️ {country_name}: получено {len(city_directions)} курортов")
            return city_directions
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении городов для {country_name}: {e}")
            return []
    
    async def _get_fallback_city_directions(self, country_code: Optional[int] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fallback направления по городам"""
        logger.info("🎭 Создаем fallback направления по городам")
        
        fallback_data = [
            # Египет
            {"country_id": 1, "country_name": "Египет", "cities": [
                {"id": "1_5", "name": "Хургада", "region_code": 5, "price": 45000},
                {"id": "1_6", "name": "Шарм-эль-Шейх", "region_code": 6, "price": 50000},
                {"id": "1_25", "name": "Марса Алам", "region_code": 25, "price": 55000}
            ]},
            # Турция
            {"country_id": 4, "country_name": "Турция", "cities": [
                {"id": "4_8", "name": "Анталья", "region_code": 8, "price": 35000},
                {"id": "4_9", "name": "Кемер", "region_code": 9, "price": 38000},
                {"id": "4_10", "name": "Белек", "region_code": 10, "price": 45000},
                {"id": "4_11", "name": "Сиде", "region_code": 11, "price": 40000}
            ]},
            # Таиланд
            {"country_id": 22, "country_name": "Таиланд", "cities": [
                {"id": "22_45", "name": "Пхукет", "region_code": 45, "price": 95000},
                {"id": "22_46", "name": "Паттайя", "region_code": 46, "price": 85000},
                {"id": "22_47", "name": "Самуи", "region_code": 47, "price": 110000}
            ]},
            # Греция
            {"country_id": 8, "country_name": "Греция", "cities": [
                {"id": "8_15", "name": "Крит", "region_code": 15, "price": 55000},
                {"id": "8_16", "name": "Родос", "region_code": 16, "price": 52000},
                {"id": "8_17", "name": "Халкидики", "region_code": 17, "price": 58000}
            ]},
            # ОАЭ
            {"country_id": 15, "country_name": "ОАЭ", "cities": [
                {"id": "15_30", "name": "Дубай", "region_code": 30, "price": 75000},
                {"id": "15_31", "name": "Абу-Даби", "region_code": 31, "price": 80000},
                {"id": "15_32", "name": "Шарджа", "region_code": 32, "price": 65000}
            ]}
        ]
        
        all_directions = []
        
        for country_data in fallback_data:
            # Фильтрация по стране если указана
            if country_code and country_data["country_id"] != country_code:
                continue
            
            for city in country_data["cities"]:
                direction = {
                    "id": city["id"],
                    "name": city["name"],
                    "country_name": country_data["country_name"],
                    "country_code": country_data["country_id"],
                    "region_code": city["region_code"],
                    "image_link": self.photo_service.get_fallback_image(
                        country_data["country_id"], 
                        city["name"]
                    ),
                    "min_price": float(city["price"]),
                    "type": "region"
                }
                all_directions.append(direction)
        
        # Применяем лимит
        if limit:
            all_directions = all_directions[:limit]
        
        logger.info(f"🎭 Создано {len(all_directions)} fallback направлений")
        return all_directions
    
    def _get_country_name(self, country_code: int) -> str:
        """Получение названия страны по коду"""
        country_map = {
            1: "Египет", 4: "Турция", 8: "Греция", 9: "Кипр", 11: "Болгария",
            15: "ОАЭ", 16: "Тунис", 17: "Черногория", 19: "Испания", 20: "Италия",
            22: "Таиланд", 23: "Индия", 24: "Шри-Ланка", 25: "Вьетнам", 26: "Китай",
            27: "Индонезия", 28: "Малайзия", 29: "Сингапур", 30: "Филиппины",
            31: "Маврикий", 32: "Сейшелы", 33: "Танзания", 34: "Кения", 35: "Мальдивы"
        }
        return country_map.get(country_code, f"Страна {country_code}")
    
    async def clear_cities_cache(self) -> int:
        """Очистка кэша направлений по городам"""
        try:
            cache_keys = await self.cache.get_keys_pattern("city_directions_*")
            
            cleared_count = 0
            for key in cache_keys:
                if await self.cache.delete(key):
                    cleared_count += 1
            
            logger.info(f"🗑️ Очищено {cleared_count} ключей кэша направлений по городам")
            return cleared_count
            
        except Exception as e:
            logger.error(f"❌ Ошибка при очистке кэша: {e}")
            return 0
    
    async def get_cities_status(self) -> Dict[str, Any]:
        """Получение статуса системы направлений по городам"""
        try:
            cache_keys = await self.cache.get_keys_pattern("city_directions_*")
            
            cache_info = {}
            for key in cache_keys:
                try:
                    cached_data = await self.cache.get(key)
                    if cached_data:
                        cache_info[key] = {
                            "count": len(cached_data),
                            "countries": list(set([item.get("country_name", "Unknown") for item in cached_data])),
                            "sample_regions": [item.get("name", "Unknown") for item in cached_data[:3]]
                        }
                except:
                    cache_info[key] = {"error": "Cannot read cache"}
            
            return {
                "cache_status": {
                    "cached_variants": len(cache_keys),
                    "cache_details": cache_info
                },
                "endpoints": {
                    "get_all_cities": "/api/v1/tours/directions/cities",
                    "get_cities_by_country": "/api/v1/tours/directions/cities?country_code=1",
                    "get_limited_cities": "/api/v1/tours/directions/cities?limit=10",
                    "clear_cache": "/api/v1/tours/directions/cities/clear-cache"
                },
                "features": {
                    "country_filtering": True,
                    "limit_support": True,
                    "photo_integration": True,
                    "price_calculation": True,
                    "fallback_data": True
                }
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "recommendation": "Check TourVisor API connection"
            }

# Создаем экземпляр сервиса
city_directions_service = CityDirectionsService()