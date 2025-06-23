# app/services/city_directions_service.py
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.services.cache_service import cache_service
from app.services.photo_service import photo_service
from app.services.price_service import price_service
from app.core.tourvisor_client import tourvisor_client
from app.models.direction import CityDirectionInfo, CountryDirectionsResponse, DirectionsResponse
from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class CityDirectionsService:
    """Сервис для получения направлений по городам (курортам) с фотографиями"""
    
    def __init__(self):
        self.cache = cache_service
        self.photo_service = photo_service
        self.price_service = price_service
        
        # Ключи кэша
        self.CITIES_CACHE_KEY = "city_directions_all"
        self.CACHE_TTL = 86400  # 24 часа
        
    async def get_all_city_directions(
        self, 
        country_id: Optional[int] = None,
        limit_per_country: int = 12
    ) -> DirectionsResponse:
        """
        Получение всех направлений по городам с фильтрацией по стране
        
        Args:
            country_id: ID страны для фильтрации (опционально)
            limit_per_country: Максимум городов на страну
        """
        try:
            logger.info(f"🌍 Получение направлений по городам (страна: {country_id}, лимит: {limit_per_country})")
            
            # Проверяем кэш
            cache_key = f"{self.CITIES_CACHE_KEY}_limit_{limit_per_country}"
            cached_data = await self.cache.get(cache_key)
            
            if cached_data:
                logger.info("📦 Данные получены из кэша")
                all_countries = [CountryDirectionsResponse(**country_data) for country_data in cached_data]
                
                # Применяем фильтрацию по стране если нужно
                if country_id:
                    filtered_countries = [c for c in all_countries if c.country_id == country_id]
                    total_cities = sum(len(c.cities) for c in filtered_countries)
                    
                    return DirectionsResponse(
                        countries=filtered_countries,
                        total_countries=len(filtered_countries),
                        total_cities=total_cities
                    )
                
                total_cities = sum(len(c.cities) for c in all_countries)
                return DirectionsResponse(
                    countries=all_countries,
                    total_countries=len(all_countries),
                    total_cities=total_cities
                )
            
            # Генерируем новые данные
            logger.info("🔄 Генерируем новые данные направлений")
            all_countries = await self._generate_city_directions(limit_per_country)
            
            # Сохраняем в кэш
            if all_countries:
                await self.cache.set(
                    cache_key,
                    [country.model_dump() for country in all_countries],
                    ttl=self.CACHE_TTL
                )
                logger.info(f"💾 Сохранено {len(all_countries)} стран в кэш")
            
            # Применяем фильтрацию если нужно
            if country_id:
                filtered_countries = [c for c in all_countries if c.country_id == country_id]
                total_cities = sum(len(c.cities) for c in filtered_countries)
                
                return DirectionsResponse(
                    countries=filtered_countries,
                    total_countries=len(filtered_countries),
                    total_cities=total_cities
                )
            
            total_cities = sum(len(c.cities) for c in all_countries)
            return DirectionsResponse(
                countries=all_countries,
                total_countries=len(all_countries),
                total_cities=total_cities
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении направлений по городам: {e}")
            raise
    
    async def _generate_city_directions(self, limit_per_country: int) -> List[CountryDirectionsResponse]:
        """Генерация направлений по городам для всех стран"""
        try:
            logger.info("🏗️ Начинаем генерацию направлений по городам")
            
            # Получаем список всех стран
            countries_data = await tourvisor_client.get_references("country")
            countries_list = countries_data.get("country", [])
            
            if not isinstance(countries_list, list):
                countries_list = [countries_list] if countries_list else []
            
            # Фильтруем валидные страны
            valid_countries = []
            for country in countries_list:
                country_id = country.get("id")
                country_name = country.get("name")
                
                if country_id and country_name:
                    try:
                        valid_countries.append({
                            "id": int(country_id),
                            "name": country_name
                        })
                    except (ValueError, TypeError):
                        continue
            
            logger.info(f"🌍 Найдено {len(valid_countries)} валидных стран")
            
            # Приоритизируем популярные страны
            popular_countries = [1, 4, 22, 8, 15, 35, 9, 11]
            
            def country_priority(country):
                return 0 if country["id"] in popular_countries else 1
            
            valid_countries.sort(key=country_priority)
            
            # Генерируем данные по странам
            all_countries = []
            
            for i, country in enumerate(valid_countries):
                try:
                    logger.info(f"🏙️ [{i+1}/{len(valid_countries)}] Обрабатываем {country['name']}")
                    
                    country_directions = await self._generate_country_cities(
                        country["id"], 
                        country["name"], 
                        limit_per_country
                    )
                    
                    if country_directions and country_directions.cities:
                        all_countries.append(country_directions)
                        logger.info(f"✅ {country['name']}: {len(country_directions.cities)} городов")
                    else:
                        logger.warning(f"⚠️ {country['name']}: нет городов")
                    
                    # Задержка между странами
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка при обработке {country['name']}: {e}")
                    continue
            
            logger.info(f"🏁 Генерация завершена: {len(all_countries)} стран")
            return all_countries
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации направлений: {e}")
            return []
    
    async def _generate_country_cities(
        self, 
        country_id: int, 
        country_name: str, 
        limit: int
    ) -> Optional[CountryDirectionsResponse]:
        """Генерация городов для одной страны"""
        try:
            # Получаем курорты для страны
            regions_data = await tourvisor_client.get_references(
                "region",
                regcountry=country_id
            )
            
            regions_list = regions_data.get("region", [])
            if not isinstance(regions_list, list):
                regions_list = [regions_list] if regions_list else []
            
            if not regions_list:
                logger.debug(f"🏙️ Нет курортов для {country_name}")
                return None
            
            logger.info(f"🏙️ {country_name}: найдено {len(regions_list)} курортов")
            
            # Генерируем данные для курортов
            cities = []
            
            # Ограничиваем количество курортов
            limited_regions = regions_list[:limit]
            
            # Обрабатываем курорты параллельно (группами по 3)
            for i in range(0, len(limited_regions), 3):
                batch = limited_regions[i:i+3]
                tasks = []
                
                for region in batch:
                    region_id = region.get("id")
                    region_name = region.get("name")
                    
                    if region_id and region_name:
                        try:
                            region_id = int(region_id)
                            task = self._generate_city_info(
                                region_id, 
                                region_name, 
                                country_id, 
                                country_name
                            )
                            tasks.append(task)
                        except (ValueError, TypeError):
                            continue
                
                # Выполняем батч параллельно
                if tasks:
                    batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    for result in batch_results:
                        if isinstance(result, CityDirectionInfo):
                            cities.append(result)
                        elif isinstance(result, Exception):
                            logger.debug(f"Ошибка в батче: {result}")
                
                # Задержка между батчами
                await asyncio.sleep(0.2)
            
            if cities:
                return CountryDirectionsResponse(
                    country_name=country_name,
                    country_id=country_id,
                    cities=cities,
                    total_cities=len(cities)
                )
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации городов для {country_name}: {e}")
            return None
    
    async def _generate_city_info(
        self, 
        city_id: int, 
        city_name: str, 
        country_id: int, 
        country_name: str
    ) -> Optional[CityDirectionInfo]:
        """Генерация информации для одного города"""
        try:
            # Получаем фото и цену параллельно с таймаутом
            try:
                photo_task = self._get_city_photo_optimized(city_id, city_name, country_id, country_name)
                price_task = self._get_city_price_optimized(city_id, country_id, country_name)
                
                photo, price = await asyncio.wait_for(
                    asyncio.gather(photo_task, price_task, return_exceptions=True),
                    timeout=8.0  # 8 секунд максимум на город
                )
            except asyncio.TimeoutError:
                logger.debug(f"⏰ Таймаут для {city_name}")
                photo = None
                price = 50000.0
            
            # Обрабатываем результаты
            if isinstance(photo, Exception):
                logger.debug(f"❌ Ошибка получения фото для {city_name}: {photo}")
                photo = None
            
            if isinstance(price, Exception):
                logger.debug(f"❌ Ошибка получения цены для {city_name}: {price}")
                price = self.price_service.get_default_prices().get(country_id, 50000.0)
            
            # Fallback для фото
            if not photo:
                photo = self.photo_service.get_fallback_image(country_id, f"{city_name}, {country_name}")
            
            return CityDirectionInfo(
                city_name=city_name,
                city_id=city_id,
                country_name=country_name,
                country_id=country_id,
                image_link=photo,
                min_price=float(price)
            )
            
        except Exception as e:
            logger.debug(f"❌ Ошибка генерации для {city_name}: {e}")
            return None
    
    async def _get_city_photo_optimized(
        self, 
        city_id: int, 
        city_name: str, 
        country_id: int, 
        country_name: str
    ) -> Optional[str]:
        """Оптимизированное получение фото для города"""
        try:
            # 1. Сначала пробуем горящие туры для этого курорта
            for city_departure in [1, 2, 3]:  # Москва, Пермь, Екатеринбург
                try:
                    hot_tours_data = await tourvisor_client.get_hot_tours(
                        city=city_departure,
                        items=5,
                        countries=str(country_id),
                        regions=str(city_id)
                    )
                    
                    tours_list = hot_tours_data.get("hottours", [])
                    if not isinstance(tours_list, list):
                        tours_list = [tours_list] if tours_list else []
                    
                    for tour in tours_list:
                        photo_url = tour.get("hotelpicture")
                        if photo_url and photo_url.strip() and not self.photo_service.is_placeholder_image(photo_url):
                            logger.debug(f"📸 Фото для {city_name} через горящие туры")
                            return photo_url
                    
                    await asyncio.sleep(0.1)
                    
                except Exception:
                    continue
            
            # 2. Если не получилось - через отели курорта
            try:
                hotels_data = await tourvisor_client.get_references(
                    "hotel",
                    hotcountry=country_id,
                    hotregion=city_id
                )
                
                hotels = hotels_data.get("hotel", [])
                if not isinstance(hotels, list):
                    hotels = [hotels] if hotels else []
                
                # Берем первые 2 отеля для быстроты
                for hotel in hotels[:2]:
                    hotel_code = hotel.get("id")
                    if not hotel_code:
                        continue
                    
                    hotel_details = await tourvisor_client.get_hotel_info(str(hotel_code))
                    
                    photo_fields = ['hotelpicturebig', 'hotelpicturemedium', 'hotelpicturesmall']
                    for field in photo_fields:
                        photo_url = hotel_details.get(field)
                        if photo_url and photo_url.strip() and not self.photo_service.is_placeholder_image(photo_url):
                            logger.debug(f"📸 Фото для {city_name} через отели")
                            return photo_url
                    
                    await asyncio.sleep(0.1)
                    
            except Exception:
                pass
            
            return None
            
        except Exception as e:
            logger.debug(f"❌ Ошибка получения фото для {city_name}: {e}")
            return None
    
    async def _get_city_price_optimized(
        self, 
        city_id: int, 
        country_id: int, 
        country_name: str
    ) -> float:
        """Оптимизированное получение цены для города"""
        try:
            # Быстрый поиск с конкретным курортом
            from datetime import datetime, timedelta
            
            search_params = {
                "departure": 1,  # Москва
                "country": country_id,
                "regions": str(city_id),
                "datefrom": (datetime.now() + timedelta(days=14)).strftime("%d.%m.%Y"),
                "dateto": (datetime.now() + timedelta(days=21)).strftime("%d.%m.%Y"),
                "nightsfrom": 7,
                "nightsto": 10,
                "adults": 2,
                "child": 0
            }
            
            request_id = await tourvisor_client.search_tours(search_params)
            
            # Ждем результатов максимум 3 секунды
            for attempt in range(3):
                await asyncio.sleep(1)
                
                status_result = await tourvisor_client.get_search_status(request_id)
                status_data = status_result.get("data", {}).get("status", {})
                
                min_price_from_status = status_data.get("minprice")
                if min_price_from_status and float(min_price_from_status) > 0:
                    return float(min_price_from_status)
            
            # Fallback к дефолтной цене страны
            return self.price_service.get_default_prices().get(country_id, 50000.0)
            
        except Exception as e:
            logger.debug(f"❌ Ошибка получения цены для города {city_id}: {e}")
            return self.price_service.get_default_prices().get(country_id, 50000.0)
    
    async def clear_cache(self) -> bool:
        """Очистка кэша направлений по городам"""
        try:
            keys_to_clear = await self.cache.get_keys_pattern("city_directions_*")
            
            for key in keys_to_clear:
                await self.cache.delete(key)
            
            logger.info(f"🗑️ Очищено {len(keys_to_clear)} ключей кэша городских направлений")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки кэша: {e}")
            return False

# Создаем экземпляр сервиса
city_directions_service = CityDirectionsService()