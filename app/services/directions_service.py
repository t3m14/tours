import asyncio
from typing import List
from datetime import datetime

from app.services.cache_service import cache_service
from app.services.photo_service import photo_service
from app.services.price_service import price_service
from app.models.tour import DirectionInfo
from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class DirectionsService:
    """Сервис для работы с направлениями и их фотографиями"""
    
    def __init__(self):
        self.cache = cache_service
        self.photo_service = photo_service
        self.price_service = price_service
    
    async def get_directions_with_prices(self) -> List[DirectionInfo]:
        """Получение списка направлений с минимальными ценами и фотографиями отелей"""
        cache_key = "directions_with_prices_and_photos"
        
        # Попытка получить из кэша
        cached_directions = await self.cache.get(cache_key)
        if cached_directions:
            logger.info(f"📸 Возвращено {len(cached_directions)} направлений из кэша")
            return [DirectionInfo(**item) for item in cached_directions]
        
        logger.info("🔄 Кэш пуст, генерируем направления с фотографиями отелей")
        return await self._generate_directions_with_hotel_photos()

    async def _generate_directions_with_hotel_photos(self) -> List[DirectionInfo]:
        """Генерация направлений с ценами и фотографиями отелей"""
        logger.info(f"🏨 НАЧИНАЕМ ГЕНЕРАЦИЮ НАПРАВЛЕНИЙ С ФОТО ОТЕЛЕЙ")
        
        try:
            directions = []
            
            # Берем популярные страны
            popular_countries = settings.POPULAR_COUNTRIES[:6]  # Первые 6 стран
            
            logger.info(f"📍 Обрабатываем страны: {popular_countries}")
            
            for country_code in popular_countries:
                try:
                    # Находим название страны
                    country_name = self._get_country_name(country_code)
                    logger.info(f"🌍 Обрабатываем {country_name} (код: {country_code})")
                    
                    # Получаем фото отеля и минимальную цену параллельно
                    hotel_photo_task = self.photo_service.get_country_hotel_photo_fast(country_code, country_name)
                    min_price_task = self.price_service.get_country_min_price(country_code, country_name)
                    
                    # Ждем результатов обеих задач
                    hotel_photo, min_price = await asyncio.gather(
                        hotel_photo_task, 
                        min_price_task,
                        return_exceptions=True
                    )
                    
                    # Обрабатываем возможные исключения
                    if isinstance(hotel_photo, Exception):
                        logger.error(f"❌ Ошибка получения фото для {country_name}: {hotel_photo}")
                        hotel_photo = None
                    
                    if isinstance(min_price, Exception):
                        logger.error(f"❌ Ошибка получения цены для {country_name}: {min_price}")
                        min_price = 50000.0
                    
                    # Fallback для фото
                    if not hotel_photo:
                        hotel_photo = self.photo_service.get_fallback_image(country_code, country_name)
                    
                    direction = DirectionInfo(
                        name=country_name,
                        image_link=hotel_photo,
                        min_price=min_price
                    )
                    directions.append(direction)
                    
                    logger.info(f"✅ Направление {country_name}: цена {min_price}, фото: {'✓' if hotel_photo and not hotel_photo.startswith('https://via.placeholder.com') else '✗'}")
                    
                    # Задержка между запросами
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка при обработке страны {country_code}: {e}")
                    # Создаем направление с fallback при ошибке
                    country_name = self._get_country_name(country_code)
                    direction = DirectionInfo(
                        name=country_name,
                        image_link=self.photo_service.get_fallback_image(country_code, country_name),
                        min_price=50000.0
                    )
                    directions.append(direction)
                    continue
            
            logger.info(f"🏁 ГЕНЕРАЦИЯ НАПРАВЛЕНИЙ ЗАВЕРШЕНА. Получено: {len(directions)}")
            
            if directions:
                # Кэшируем результат на 6 часов
                try:
                    await self.cache.set(
                        "directions_with_prices_and_photos", 
                        [direction.dict() for direction in directions], 
                        ttl=21600
                    )
                    logger.info(f"💾 Направления сохранены в кэш")
                except Exception as cache_error:
                    logger.error(f"❌ Ошибка сохранения в кэш: {cache_error}")
            
            return directions
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при генерации направлений: {e}")
            return []

    async def refresh_directions(self) -> List[DirectionInfo]:
        """Принудительное обновление направлений"""
        logger.info("🔄 Принудительное обновление направлений")
        
        # Удаляем кэш
        await self.cache.delete("directions_with_prices_and_photos")
        
        # Генерируем новые направления
        return await self._generate_directions_with_hotel_photos()

    async def get_directions_status(self) -> dict:
        """Получение статуса системы направлений"""
        try:
            # Проверяем кэш
            cached_directions = await self.cache.get("directions_with_prices_and_photos")
            
            return {
                "cache": {
                    "has_data": bool(cached_directions),
                    "directions_count": len(cached_directions) if cached_directions else 0,
                    "cache_key": "directions_with_prices_and_photos"
                },
                "photo_sources": {
                    "hot_tours": "Fastest - from hot tours API",
                    "hotels_reference": "Medium - from hotels directory",
                    "tours_search": "Slower - from search results",
                    "fallback": "Placeholder with country colors"
                },
                "endpoints": {
                    "get_directions": "/api/v1/tours/directions",
                    "refresh_directions": "/api/v1/tours/directions/refresh", 
                    "check_status": "/api/v1/tours/directions/status"
                },
                "features": {
                    "real_hotel_photos": True,
                    "min_prices_from_search": True,
                    "cache_ttl_hours": 6,
                    "parallel_processing": True,
                    "multiple_photo_sources": True
                }
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "recommendation": "use_refresh_endpoint"
            }

    async def fix_cache_issues(self) -> dict:
        """Исправление проблем с кэшированием направлений"""
        try:
            logger.info("🔧 Исправляем проблемы с кэшем направлений")
            
            # 1. Очищаем старые ключи кэша
            old_cache_keys = [
                "directions_with_prices_search",
                "directions_with_prices",
                "directions_with_prices_and_photos"
            ]
            
            cleared_keys = []
            for key in old_cache_keys:
                if await self.cache.delete(key):
                    cleared_keys.append(key)
            
            # 2. Принудительно генерируем новые направления
            logger.info("🔧 Генерируем новые направления...")
            new_directions = await self._generate_directions_with_hotel_photos()
            
            # 3. Проверяем результат
            cache_check = await self.cache.get("directions_with_prices_and_photos")
            
            return {
                "success": True,
                "actions_performed": [
                    f"Очищены ключи кэша: {cleared_keys}",
                    f"Сгенерировано {len(new_directions)} направлений",
                    f"Кэш {'сохранен' if cache_check else 'НЕ сохранен'}"
                ],
                "generated_directions": [
                    {
                        "name": d.name,
                        "has_real_photo": not d.image_link.startswith("https://via.placeholder.com"),
                        "price": d.min_price
                    }
                    for d in new_directions
                ],
                "recommendations": [
                    "Проверьте endpoints /api/v1/tours/directions",
                    "Если проблемы остались, используйте /api/v1/tours/directions/diagnose"
                ]
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка при исправлении кэша: {e}")
            raise

    def _get_country_name(self, country_code: int) -> str:
        """Получение названия страны по коду"""
        country_map = {
            1: "Египет",
            4: "Турция", 
            22: "Таиланд",
            8: "Греция",
            15: "ОАЭ",
            35: "Мальдивы"
        }
        return country_map.get(country_code, f"Страна {country_code}")

# Создаем экземпляр сервиса направлений
directions_service = DirectionsService()