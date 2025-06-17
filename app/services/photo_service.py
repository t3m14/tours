import asyncio
from typing import Optional
from datetime import datetime, timedelta

from app.core.tourvisor_client import tourvisor_client
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class PhotoService:
    """Сервис для получения фотографий отелей"""
    
    @staticmethod
    def is_placeholder_image(image_url: str) -> bool:
        """Проверка, является ли изображение placeholder'ом"""
        if not image_url:
            return True
        
        placeholder_indicators = [
            "placeholder.com",
            "via.placeholder",
            "placehold",
            "no-image",
            "default",
            "noimage"
        ]
        
        return any(indicator in image_url.lower() for indicator in placeholder_indicators)
    
    @staticmethod
    def get_fallback_image(country_code: int, country_name: str) -> str:
        """Получение запасной фотографии для направления"""
        # Цвета для разных стран
        colors = {
            1: "FFD700",    # Египет - золотой
            4: "FF6B6B",    # Турция - красный  
            22: "4ECDC4",   # Таиланд - бирюзовый
            8: "74B9FF",    # Греция - синий
            15: "A29BFE",   # ОАЭ - фиолетовый
            35: "00CEC9"    # Мальдивы - циан
        }
        
        color = colors.get(country_code, "6C7CE7")
        
        # Создаем красивую placeholder фотографию
        fallback_url = f"https://via.placeholder.com/400x300/{color}/FFFFFF?text={country_name.replace(' ', '+')}"
        
        logger.info(f"🎨 Используем fallback изображение для {country_name}: {fallback_url}")
        return fallback_url
    
    async def get_country_hotel_photo_fast(self, country_code: int, country_name: str) -> Optional[str]:
        """Быстрое получение фото отеля (горящие туры → справочник → поиск)"""
        try:
            logger.info(f"📸 Быстрое получение фото для {country_name}")
            
            # 1. Сначала пробуем горящие туры (самый быстрый способ)
            photo_from_hot_tours = await self._get_photo_via_hot_tours(country_code, country_name)
            if photo_from_hot_tours:
                return photo_from_hot_tours
            
            # 2. Если не получилось, пробуем через справочник отелей
            logger.info(f"📋 Пробуем справочник отелей для {country_name}")
            photo_from_reference = await self._get_photo_from_hotels_reference(country_code, country_name)
            if photo_from_reference:
                return photo_from_reference
            
            # 3. В крайнем случае - через поиск туров
            logger.info(f"🔍 Пробуем поиск туров для {country_name}")
            photo_from_search = await self._get_photo_via_search(country_code, country_name)
            if photo_from_search:
                return photo_from_search
            
            logger.warning(f"⚠️ Не найдено фото отелей для {country_name} всеми способами")
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка быстрого получения фото для {country_name}: {e}")
            return None

    async def _get_photo_via_hot_tours(self, country_code: int, country_name: str) -> Optional[str]:
        """Получение фото отеля через горящие туры (самый быстрый способ)"""
        try:
            logger.info(f"🔥 Получение фото через горящие туры для {country_name}")
            
            # Пробуем получить горящие туры для страны из разных городов
            cities_to_try = [1, 2, 3]  # Москва, Пермь, Екатеринбург
            
            for city in cities_to_try:
                try:
                    hot_tours_data = await tourvisor_client.get_hot_tours(
                        city=city,
                        items=10,  # Увеличиваем количество для большего выбора
                        countries=str(country_code)
                    )
                    
                    tours_list = hot_tours_data.get("hottours", [])
                    if not isinstance(tours_list, list):
                        tours_list = [tours_list] if tours_list else []
                    
                    logger.info(f"🔥 Найдено {len(tours_list)} горящих туров для {country_name} из города {city}")
                    
                    # Ищем тур с фотографией отеля
                    for tour in tours_list:
                        photo_url = tour.get("hotelpicture")
                        if photo_url and photo_url.strip() and not self.is_placeholder_image(photo_url):
                            logger.info(f"🔥✅ Найдено фото через горящие туры для {country_name}: {tour.get('hotelname', 'Unknown')}")
                            return photo_url
                    
                    # Задержка между попытками
                    await asyncio.sleep(0.3)
                    
                except Exception as city_error:
                    logger.debug(f"🔥 Ошибка для города {city}: {city_error}")
                    continue
            
            logger.debug(f"🔥 Нет подходящих фото в горящих турах для {country_name}")
            return None
            
        except Exception as e:
            logger.debug(f"🔥 Ошибка получения фото через горящие туры для {country_name}: {e}")
            return None

    async def _get_photo_from_hotels_reference(self, country_code: int, country_name: str) -> Optional[str]:
        """Получение фотографии отеля через справочник отелей"""
        try:
            logger.info(f"📋 Получение фото через справочник отелей для {country_name}")
            
            # Пробуем разные варианты фильтрации отелей
            filter_variants = [
                {"hotstars": 5},           # Сначала 5* отели
                {"hotstars": 4},           # Потом 4* отели  
                {"hotbeach": 1},           # Пляжные отели
                {"hotdeluxe": 1},          # Люкс отели
                {}                         # Любые отели
            ]
            
            for filters in filter_variants:
                try:
                    hotels_data = await tourvisor_client.get_references(
                        "hotel",
                        hotcountry=country_code,
                        **filters
                    )
                    
                    hotels = hotels_data.get("hotel", [])
                    if not isinstance(hotels, list):
                        hotels = [hotels] if hotels else []
                    
                    logger.info(f"📋 Найдено {len(hotels)} отелей для {country_name} с фильтрами {filters}")
                    
                    # Берем первые 5 отелей для быстрой обработки
                    for hotel in hotels[:5]:
                        try:
                            hotel_code = hotel.get("id")
                            hotel_name = hotel.get("name", "Unknown")
                            
                            if not hotel_code:
                                continue
                            
                            logger.debug(f"📋 Проверяем отель {hotel_name} (код: {hotel_code})")
                            
                            # Получаем детальную информацию об отеле
                            hotel_details = await tourvisor_client.get_hotel_info(str(hotel_code))
                            
                            # Ищем фотографии в разных полях (в порядке предпочтения)
                            photo_fields = [
                                'hotelpicturebig', 'hotelpicturemedium', 'hotelpicturesmall',
                                'picturelink', 'picture', 'image'
                            ]
                            
                            for field in photo_fields:
                                photo_url = hotel_details.get(field)
                                if photo_url and photo_url.strip() and not self.is_placeholder_image(photo_url):
                                    logger.info(f"📋✅ Найдено фото отеля для {country_name}: {hotel_name}")
                                    return photo_url
                            
                            # Также проверяем массив изображений
                            images = hotel_details.get("images", [])
                            if images and isinstance(images, list) and len(images) > 0:
                                first_image = images[0]
                                if isinstance(first_image, dict):
                                    photo_url = first_image.get("image") or first_image.get("url") or first_image.get("link")
                                else:
                                    photo_url = str(first_image)
                                
                                if photo_url and photo_url.strip() and not self.is_placeholder_image(photo_url):
                                    logger.info(f"📋✅ Найдено фото отеля для {country_name}: {hotel_name}")
                                    return photo_url
                            
                            # Задержка между запросами к отелям
                            await asyncio.sleep(0.1)
                            
                        except Exception as hotel_error:
                            logger.debug(f"📋 Ошибка при получении фото отеля {hotel.get('id', 'unknown')}: {hotel_error}")
                            continue
                    
                    # Если нашли отели но нет фото, пробуем следующий фильтр
                    if hotels:
                        await asyncio.sleep(0.2)
                    
                except Exception as filter_error:
                    logger.debug(f"📋 Ошибка с фильтрами {filters}: {filter_error}")
                    continue
            
            logger.warning(f"📋 Не найдено фото отелей для {country_name} через справочник")
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения фото через справочник: {e}")
            return None

    async def _get_photo_via_search(self, country_code: int, country_name: str) -> Optional[str]:
        """Получение фото отеля через поиск туров"""
        try:
            logger.info(f"🔍 Поиск фото отеля через туры для {country_name}")
            
            # Пробуем разные варианты поиска
            search_variants = [
                {  # Стандартный поиск
                    "nightsfrom": 7, "nightsto": 10,
                    "stars": 4, "adults": 2, "child": 0
                },
                {  # Поиск люкс отелей
                    "nightsfrom": 3, "nightsto": 7,
                    "stars": 5, "adults": 2, "child": 0
                },
                {  # Простой поиск без фильтров
                    "nightsfrom": 7, "nightsto": 14,
                    "adults": 2, "child": 0
                }
            ]
            
            for variant in search_variants:
                try:
                    search_params = {
                        "departure": 1,  # Москва
                        "country": country_code,
                        "datefrom": (datetime.now() + timedelta(days=7)).strftime("%d.%m.%Y"),
                        "dateto": (datetime.now() + timedelta(days=14)).strftime("%d.%m.%Y"),
                        **variant
                    }
                    
                    logger.debug(f"🔍 Поиск с параметрами: {variant}")
                    request_id = await tourvisor_client.search_tours(search_params)
                    
                    # Ждем результатов (максимум 5 секунд)
                    for attempt in range(5):
                        await asyncio.sleep(1)
                        
                        status_result = await tourvisor_client.get_search_status(request_id)
                        status_data = status_result.get("data", {}).get("status", {})
                        state = status_data.get("state", "searching")
                        hotels_found = status_data.get("hotelsfound", 0)
                        
                        logger.debug(f"🔍 Попытка {attempt+1}: статус = {state}, отелей = {hotels_found}")
                        
                        if state == "finished" or hotels_found > 0:
                            # Получаем результаты
                            results = await tourvisor_client.get_search_results(request_id, 1, 5)
                            
                            data = results.get("data", {})
                            result_data = data.get("result", {})
                            hotel_list = result_data.get("hotel", [])
                            
                            if not isinstance(hotel_list, list):
                                hotel_list = [hotel_list] if hotel_list else []
                            
                            # Ищем отель с фотографией
                            for hotel in hotel_list:
                                photo_url = hotel.get("picturelink")
                                hotel_name = hotel.get("hotelname", "Unknown")
                                
                                if photo_url and photo_url.strip() and not self.is_placeholder_image(photo_url):
                                    logger.info(f"🔍✅ Найдено фото отеля через поиск для {country_name}: {hotel_name}")
                                    return photo_url
                            
                            break
                    
                    # Задержка между вариантами поиска
                    await asyncio.sleep(0.5)
                    
                except Exception as variant_error:
                    logger.debug(f"🔍 Ошибка с вариантом {variant}: {variant_error}")
                    continue
            
            logger.warning(f"🔍 Не найдено фото отелей для {country_name} через поиск")
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения фото через поиск для {country_name}: {e}")
            return None

# Создаем экземпляр сервиса фотографий
photo_service = PhotoService()