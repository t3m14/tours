# app/services/destinations_service.py (версия с детальной информацией об отелях)

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from app.services.cache_service import cache_service
from app.core.tourvisor_client import tourvisor_client
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class DestinationsService:
    """Сервис для получения направлений через поиск туров"""
    
    def __init__(self):
        self.cache = cache_service
        self.CACHE_KEY = "destinations_search_based"
        self.CACHE_TTL = 86400  # 24 часа
    
    async def get_destinations(self) -> List[Dict[str, Any]]:
        """Получить направления"""
        logger.info("🏖️ Получение направлений через поиск")
        
        # Проверяем кэш
        cached = await self.cache.get(self.CACHE_KEY)
        if cached:
            logger.info(f"📦 Возвращено {len(cached)} направлений из кэша")
            return cached
        
        # Собираем направления
        destinations = await self._collect_destinations_via_search()
        
        # Сохраняем в кэш
        if destinations:
            await self.cache.set(self.CACHE_KEY, destinations, ttl=self.CACHE_TTL)
            logger.info(f"💾 Сохранено {len(destinations)} направлений в кэш")
        
        return destinations
    
    async def _collect_destinations_via_search(self) -> List[Dict[str, Any]]:
        """Собрать направления через поиск туров"""
        destinations = []
        
        # Получаем курорты из API
        countries_regions = await self._get_countries_with_regions()
        
        if not countries_regions:
            logger.warning("⚠️ Не найдено курортов из API")
            return []
        
        # Создаем задачи для параллельного выполнения (первые 15)
        tasks = []
        for country_id, country_name, region_id, region_name in countries_regions[:15]:
            task = asyncio.create_task(
                self._search_destination(country_id, country_name, region_id, region_name)
            )
            tasks.append(task)
        
        # Выполняем все поиски параллельно
        logger.info(f"🔍 Запускаем {len(tasks)} поисков параллельно")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Собираем результаты
        for result in results:
            if isinstance(result, dict) and result:  # Успешный результат
                destinations.append(result)
                photo_type = "реальное" if not "placeholder" in result['image_link'] else "fallback"
                logger.info(f"✅ Добавлено: {result['name']} - {result['min_price']} руб, фото: {photo_type}")
            elif isinstance(result, Exception):
                logger.error(f"❌ Ошибка поиска: {result}")
        
        logger.info(f"🎯 Собрано {len(destinations)} направлений")
        return destinations
    
    async def _get_countries_with_regions(self) -> List[tuple]:
        """Получить список стран с курортами"""
        countries_regions = []
        
        # Популярные страны
        countries = {1: "Египет", 4: "Турция", 22: "Таиланд"}
        
        for country_id, country_name in countries.items():
            try:
                logger.info(f"🌍 Получаем курорты для {country_name}")
                
                # Получаем курорты
                regions_data = await tourvisor_client.get_references("region", regcountry=country_id)
                
                if not regions_data or not isinstance(regions_data, dict):
                    continue
                
                # Извлекаем курорты из новой структуры API
                regions = None
                if "lists" in regions_data and isinstance(regions_data["lists"], dict):
                    if "regions" in regions_data["lists"] and isinstance(regions_data["lists"]["regions"], dict):
                        if "region" in regions_data["lists"]["regions"]:
                            regions = regions_data["lists"]["regions"]["region"]
                
                if not regions and "region" in regions_data:
                    regions = regions_data["region"]
                
                if not regions:
                    continue
                
                if not isinstance(regions, list):
                    regions = [regions]
                
                logger.info(f"📍 {country_name}: найдено {len(regions)} курортов")
                
                # Добавляем курорты в список
                for region in regions[:5]:  # Максимум 5 курортов на страну
                    region_id = region.get("id")
                    region_name = region.get("name")
                    
                    if region_id and region_name:
                        countries_regions.append((country_id, country_name, region_id, region_name))
                
            except Exception as e:
                logger.error(f"❌ Ошибка получения курортов {country_name}: {e}")
                continue
        
        logger.info(f"📍 Итого найдено {len(countries_regions)} курортов для поиска")
        return countries_regions
    
    async def _search_destination(self, country_id: int, country_name: str, region_id: int, region_name: str) -> Optional[Dict[str, Any]]:
        """Поиск направления через search API"""
        try:
            logger.info(f"🔍 Поиск для {region_name} ({country_name})")
            
            # Параметры поиска
            search_params = {
                "departure": 1,  # Москва
                "country": country_id,
                "region": region_id,
                "datefrom": (datetime.now() + timedelta(days=30)).strftime("%d.%m.%Y"),
                "dateto": (datetime.now() + timedelta(days=90)).strftime("%d.%m.%Y"),
                "nightsfrom": 7,
                "nightsto": 10,
                "adults": 2,
                "child": 0,
                "stars": 3
            }
            
            # Запускаем поиск
            request_id = await tourvisor_client.search_tours(search_params)
            if not request_id:
                return None
            
            # Ждем результаты
            hotels_found = 0
            for attempt in range(8):
                await asyncio.sleep(1)
                
                status_result = await tourvisor_client.get_search_status(request_id)
                if not status_result:
                    continue
                
                status_data = self._extract_status(status_result)
                if not status_data:
                    continue
                
                state = status_data.get("state", "")
                hotels_found = int(status_data.get("hotelsfound", 0))
                
                if hotels_found > 0 and state in ["completed", "continue"]:
                    break
            
            if hotels_found == 0:
                return None
            
            # Получаем результаты поиска
            results = await tourvisor_client.get_search_results(request_id, 1, 5)
            if not results:
                return None
            
            # Извлекаем данные
            min_price = self._extract_min_price(results)
            if min_price is None:
                return None
            
            # Получаем фото через детальную информацию об отеле
            image_link = await self._get_hotel_photo_via_details(results, region_name)
            
            # Fallback для фото
            if not image_link:
                colors = {1: "FFD700", 4: "FF6B6B", 22: "4ECDC4"}
                color = colors.get(country_id, "6C7CE7")
                image_link = f"https://via.placeholder.com/400x300/{color}/FFFFFF?text={region_name.replace(' ', '+')}"
            
            return {
                "name": region_name,
                "country_id": country_id,
                "country_name": country_name,
                "image_link": image_link,
                "min_price": min_price
            }
                
        except Exception as e:
            logger.error(f"❌ Ошибка поиска {region_name}: {e}")
            return None
    
    async def _get_hotel_photo_via_details(self, search_results: Dict, region_name: str) -> Optional[str]:
        """Получение фото отеля через детальную информацию об отеле"""
        try:
            logger.info(f"📸 НОВЫЙ ПОДХОД: Ищем фото через детальную информацию для {region_name}")
            
            # Извлекаем отели из результатов поиска
            hotels = self._find_hotels_in_results(search_results)
            if not hotels:
                logger.warning(f"📸 Нет отелей в результатах поиска для {region_name}")
                return None
            
            # Пробуем получить детальную информацию о первых 3 отелях
            for i, hotel in enumerate(hotels[:3]):
                try:
                    hotel_code = hotel.get("hotelcode")
                    hotel_name = hotel.get("hotelname", "Unknown")
                    
                    if not hotel_code:
                        logger.debug(f"📸 Отель {i+1} ({hotel_name}): нет hotel_code")
                        continue
                    
                    logger.info(f"📸 Запрашиваем детали отеля {hotel_name} (код: {hotel_code})")
                    
                    # Получаем детальную информацию об отеле
                    hotel_details = await tourvisor_client.get_hotel_info(hotel_code)
                    
                    if not hotel_details:
                        logger.debug(f"📸 Нет деталей для отеля {hotel_name}")
                        continue
                    
                    logger.info(f"📸 ДЕТАЛИ ОТЕЛЯ: Ответ для {hotel_name}: {type(hotel_details)}")
                    if isinstance(hotel_details, dict):
                        logger.info(f"📸 ДЕТАЛИ ОТЕЛЯ: Ключи: {list(hotel_details.keys())}")
                        logger.info(f"📸 ДЕТАЛИ ОТЕЛЯ: Содержимое (300 символов): {str(hotel_details)[:300]}...")
                    
                    # Ищем фото в детальной информации
                    photo_url = self._extract_photo_from_hotel_details(hotel_details, hotel_name)
                    if photo_url:
                        logger.info(f"📸 ✅ УСПЕХ! Найдено фото в деталях отеля {hotel_name}: {photo_url}")
                        return photo_url
                    
                    # Небольшая задержка между запросами
                    await asyncio.sleep(0.3)
                    
                except Exception as hotel_error:
                    logger.debug(f"📸 Ошибка получения деталей отеля {hotel.get('hotelname', 'Unknown')}: {hotel_error}")
                    continue
            
            logger.warning(f"📸 ❌ Не найдено фото в деталях отелей для {region_name}")
            return None
            
        except Exception as e:
            logger.error(f"📸 ❌ Ошибка получения фото через детали для {region_name}: {e}")
            return None
    
    def _extract_photo_from_hotel_details(self, hotel_details: Dict, hotel_name: str) -> Optional[str]:
        """Извлечение фото из детальной информации об отеле"""
        try:
            if not isinstance(hotel_details, dict):
                return None
            
            # Возможные поля с фото в детальной информации
            photo_fields = [
                "picture", "photo", "image", "hotelpicture", "hotelphoto", "img", "pic",
                "photo_url", "image_url", "main_photo", "main_image", "thumbnail",
                "cover_photo", "hero_image", "primary_image", "gallery", "photos", "images"
            ]
            
            logger.debug(f"📸 ПОИСК ФОТО: Проверяем поля для {hotel_name}")
            
            # Прямой поиск в корне
            for field in photo_fields:
                photo_url = hotel_details.get(field)
                logger.debug(f"📸 Поле '{field}': {photo_url}")
                
                if photo_url and isinstance(photo_url, str) and photo_url.startswith("http"):
                    logger.info(f"📸 ✅ Найдено фото в поле '{field}': {photo_url[:50]}...")
                    return photo_url
            
            # Поиск в подструктурах
            for key, value in hotel_details.items():
                if isinstance(value, dict):
                    logger.debug(f"📸 Проверяем подструктуру '{key}'")
                    for field in photo_fields:
                        photo_url = value.get(field)
                        if photo_url and isinstance(photo_url, str) and photo_url.startswith("http"):
                            logger.info(f"📸 ✅ Найдено фото в {key}.{field}: {photo_url[:50]}...")
                            return photo_url
                
                elif isinstance(value, list) and value:
                    # Проверяем первый элемент списка
                    first_item = value[0]
                    if isinstance(first_item, dict):
                        for field in photo_fields:
                            photo_url = first_item.get(field)
                            if photo_url and isinstance(photo_url, str) and photo_url.startswith("http"):
                                logger.info(f"📸 ✅ Найдено фото в {key}[0].{field}: {photo_url[:50]}...")
                                return photo_url
            
            return None
            
        except Exception as e:
            logger.debug(f"📸 Ошибка извлечения фото: {e}")
            return None
    
    def _extract_status(self, status_result: Dict) -> Optional[Dict]:
        """Извлечение статуса из ответа"""
        try:
            if isinstance(status_result, dict):
                if "data" in status_result and isinstance(status_result["data"], dict):
                    if "status" in status_result["data"]:
                        return status_result["data"]["status"]
                
                if "status" in status_result:
                    return status_result["status"]
                    
                for value in status_result.values():
                    if isinstance(value, dict) and "state" in value:
                        return value
            
            return None
        except:
            return None
    
    def _extract_min_price(self, results: Dict) -> Optional[float]:
        """Извлечение минимальной цены из результатов"""
        try:
            min_price = None
            
            # Ищем отели в результатах
            hotels = self._find_hotels_in_results(results)
            
            for hotel in hotels:
                # Ищем туры в отеле
                tours = self._find_tours_in_hotel(hotel)
                
                for tour in tours:
                    price = tour.get("price")
                    if price:
                        try:
                            price_float = float(price)
                            if min_price is None or price_float < min_price:
                                min_price = price_float
                        except:
                            pass
            
            return min_price
            
        except Exception as e:
            logger.debug(f"❌ Ошибка извлечения цены: {e}")
            return None
    
    def _find_hotels_in_results(self, results: Dict) -> List[Dict]:
        """Поиск отелей в результатах"""
        hotels = []
        
        try:
            if isinstance(results, dict):
                # data.result.hotel
                if "data" in results and isinstance(results["data"], dict):
                    if "result" in results["data"] and isinstance(results["data"]["result"], dict):
                        if "hotel" in results["data"]["result"]:
                            hotel_data = results["data"]["result"]["hotel"]
                            if isinstance(hotel_data, list):
                                hotels.extend(hotel_data)
                            elif hotel_data:
                                hotels.append(hotel_data)
                
                # прямо hotel
                if "hotel" in results:
                    hotel_data = results["hotel"]
                    if isinstance(hotel_data, list):
                        hotels.extend(hotel_data)
                    elif hotel_data:
                        hotels.append(hotel_data)
        except:
            pass
        
        return hotels
    
    def _find_tours_in_hotel(self, hotel: Dict) -> List[Dict]:
        """Поиск туров в отеле"""
        tours = []
        
        try:
            if "tours" in hotel and isinstance(hotel["tours"], dict):
                if "tour" in hotel["tours"]:
                    tour_data = hotel["tours"]["tour"]
                    if isinstance(tour_data, list):
                        tours.extend(tour_data)
                    elif tour_data:
                        tours.append(tour_data)
            
            if "tour" in hotel:
                tour_data = hotel["tour"]
                if isinstance(tour_data, list):
                    tours.extend(tour_data)
                elif tour_data:
                    tours.append(tour_data)
        except:
            pass
        
        return tours
    
    async def clear_cache(self):
        """Очистить кэш"""
        await self.cache.delete(self.CACHE_KEY)
        logger.info("🗑️ Кэш направлений очищен")
    
    async def refresh(self) -> List[Dict[str, Any]]:
        """Принудительное обновление"""
        await self.clear_cache()
        return await self.get_destinations()

# Создаем экземпляр
destinations_service = DestinationsService()