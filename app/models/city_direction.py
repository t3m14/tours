# app/services/city_directions_service.py

import asyncio
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import json

from app.services.cache_service import cache_service
from app.core.tourvisor_client import tourvisor_client
from app.models.tour import TourSearchRequest
from app.services.tour_service import tour_service
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class CityDirectionsService:
    """
    Новый сервис для получения направлений по городам через поиск туров
    
    Логика:
    1. Получаем список регионов (городов) для страны
    2. Для каждого региона запускаем поиск туров
    3. Извлекаем минимальную цену и фото отеля
    4. Возвращаем информацию в требуемом формате
    """
    
    def __init__(self):
        self.cache = cache_service
        
        # Кэш на 24 часа для результатов по городам
        self.CITIES_CACHE_TTL = 86400  # 24 часа
        
        # Маппинг стран из бара сайта (точные ID из TourVisor)
        self.COUNTRIES_MAPPING = {
            "Россия": 47,
            "Турция": 4, 
            "Таиланд": 2,
            "ОАЭ": 9,
            "Египет": 1,
            "Мальдивы": 8,
            "Китай": 13,
            "Шри-Ланка": 12,
            "Абхазия": 46,
            "Куба": 10,
            "Индия": 3,
            "Вьетнам": 16,
            "Камбоджа": 40
        }

    async def get_city_directions(self, country_id: int, limit: Optional[int] = None) -> List[Dict]:
        """
        Получение направлений по городам для указанной страны
        
        Args:
            country_id: ID страны в TourVisor
            limit: Максимальное количество городов для возврата
            
        Returns:
            List[Dict]: Список городов с информацией о ценах и фото
        """
        cache_key = f"city_directions_{country_id}"
        
        # Проверяем кэш
        cached_result = await self.cache.get(cache_key)
        if cached_result:
            logger.info(f"🏙️ Возвращено {len(cached_result)} городов из кэша для страны {country_id}")
            return cached_result[:limit] if limit else cached_result
        
        try:
            # Получаем название страны
            country_name = await self._get_country_name(country_id)
            
            # Получаем список регионов (городов) для страны
            regions = await self._get_country_regions(country_id)
            
            if not regions:
                logger.warning(f"❌ Не найдены регионы для страны {country_id}")
                return []
            
            logger.info(f"🔍 Начинаем сбор данных для {len(regions)} регионов страны {country_name}")
            
            # Обрабатываем регионы параллельно, но с ограничением
            semaphore = asyncio.Semaphore(2)  # Уменьшено до 2 одновременных запросов
            tasks = []
            
            for region in regions[:limit] if limit else regions:
                task = self._process_region(semaphore, country_id, country_name, region)
                tasks.append(task)
            
            # Ждем завершения всех задач
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Фильтруем успешные результаты
            city_directions = []
            for result in results:
                if isinstance(result, dict) and result.get("min_price"):
                    city_directions.append(result)
                elif isinstance(result, Exception):
                    logger.error(f"❌ Ошибка при обработке региона: {result}")
            
            # Сортируем по цене
            city_directions.sort(key=lambda x: x.get("min_price", float('inf')))
            
            # Кэшируем результат
            await self.cache.set(cache_key, city_directions, ttl=self.CITIES_CACHE_TTL)
            
            logger.info(f"✅ Собрано {len(city_directions)} городов для страны {country_name}")
            
            return city_directions
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении направлений по городам: {e}")
            return []

    async def _process_region(self, semaphore: asyncio.Semaphore, country_id: int, 
                            country_name: str, region: Dict) -> Optional[Dict]:
        """
        Обработка одного региона (города)
        
        Args:
            semaphore: Семафор для ограничения одновременных запросов
            country_id: ID страны
            country_name: Название страны
            region: Информация о регионе
            
        Returns:
            Dict: Информация о городе с ценой и фото или None
        """
        async with semaphore:
            try:
                region_id = region.get("id")
                region_name = region.get("name")
                
                if not region_id or not region_name:
                    return None
                
                logger.debug(f"🔍 Обрабатываем регион: {region_name} (ID: {region_id})")
                
                # Создаем запрос на поиск туров в этом регионе
                search_request = TourSearchRequest(
                    departure=1,  # Москва по умолчанию
                    country=country_id,
                    regions=str(region_id),  # Добавляем параметр региона
                    nights=7,  # 7 ночей по умолчанию
                    adults=2
                )
                
                logger.debug(f"🚀 Запускаем поиск туров для региона {region_name}")
                
                # Запускаем поиск
                search_response = await tour_service.search_tours(search_request)
                request_id = search_response.request_id
                
                logger.debug(f"🎯 Получен request_id: {request_id} для региона {region_name}")
                
                # Ждем завершения поиска (увеличиваем время ожидания)
                search_completed = False
                for attempt in range(60):  # Увеличено до 60 секунд
                    await asyncio.sleep(1)
                    status = await tour_service.get_search_status(request_id)
                    
                    logger.debug(f"🔄 Попытка {attempt + 1}/60 для {region_name}: статус = {status.state}")
                    
                    if status.state == "finished":
                        search_completed = True
                        break
                    elif status.state == "error":
                        logger.warning(f"❌ Ошибка поиска для региона {region_name}: {status.error}")
                        return None
                
                if not search_completed:
                    logger.warning(f"⏰ Таймаут поиска для региона {region_name}")
                    return None
                
                logger.debug(f"✅ Поиск завершен для региона {region_name}")
                
                # Получаем минимальную цену из статуса поиска (намного проще!)
                min_price = status.minprice
                
                if not min_price or min_price <= 0:
                    logger.debug(f"❌ Нет валидной минимальной цены для региона {region_name}: {min_price}")
                    return None
                
                logger.debug(f"💰 Минимальная цена из статуса для {region_name}: {min_price}")
                
                # Получаем результаты с более мягкой валидацией
                try:
                    search_results = await tour_service.get_search_results(request_id, page=1, onpage=10)
                except Exception as validation_error:
                    logger.warning(f"⚠️ Ошибка валидации результатов для {region_name}: {validation_error}")
                    # Попробуем получить сырые данные и обработать их вручную
                    try:
                        # Получаем сырые данные напрямую от TourVisor
                        raw_results = await tourvisor_client.get_search_results(request_id, page=1, onpage=10)
                        
                        if not raw_results or not raw_results.get("result"):
                            logger.debug(f"❌ Нет сырых результатов для региона {region_name}")
                            return None
                        
                        # Извлекаем минимальную цену из сырых данных
                        hotels = raw_results.get("result", [])
                        if not hotels:
                            return None
                        
                        min_price = float('inf')
                        image_link = "https://via.placeholder.com/300x200?text=No+Image"
                        
                        for hotel in hotels:
                            # Ищем туры в отеле
                            tours = hotel.get("tours", [])
                            if isinstance(tours, list):
                                for tour in tours:
                                    try:
                                        price = float(tour.get("price", 0))
                                        if price > 0 and price < min_price:
                                            min_price = price
                                    except (ValueError, TypeError):
                                        continue
                            
                            # Ищем фото
                            hotel_picture = hotel.get("picturelink") or hotel.get("hotelpicture")
                            if hotel_picture and isinstance(hotel_picture, str) and hotel_picture.startswith('http'):
                                image_link = hotel_picture
                        
                        if min_price == float('inf'):
                            logger.debug(f"❌ Не найдены валидные цены для региона {region_name}")
                            return None
                        
                        result = {
                            "country_name": country_name,
                            "country_id": country_id,
                            "city_name": region_name,
                            "image_link": image_link,
                            "min_price": int(min_price)
                        }
                        
                        logger.info(f"✅ Регион {region_name} (сырые данные): цена от {min_price} руб., фото: {'есть' if not image_link.startswith('https://via.placeholder.com') else 'нет'}")
                        
                        return result
                        
                    except Exception as raw_error:
                        logger.error(f"❌ Ошибка обработки сырых данных для {region_name}: {raw_error}")
                        return None
                
                if not search_results.result:
                    logger.debug(f"❌ Нет туров для региона {region_name}")
                    return None
                
                logger.debug(f"📊 Найдено {len(search_results.result)} туров для региона {region_name}")
                
                # Находим минимальную цену и фото
                min_price = min(tour.price for tour in search_results.result)
                
                # Ищем фото отеля (берем первое доступное)
                image_link = "https://via.placeholder.com/300x200?text=No+Image"
                for tour in search_results.result:
                    # Проверяем разные поля для фото
                    photo_fields = ['hotel_picture', 'hotel_image', 'image', 'picture', 'picturelink']
                    for field in photo_fields:
                        if hasattr(tour, field):
                            photo_url = getattr(tour, field)
                            if photo_url and isinstance(photo_url, str) and photo_url.startswith('http'):
                                image_link = photo_url
                                logger.debug(f"📸 Найдено фото для {region_name}: {photo_url}")
                                break
                    if image_link != "https://via.placeholder.com/300x200?text=No+Image":
                        break
                
                result = {
                    "country_name": country_name,
                    "country_id": country_id,
                    "city_name": region_name,
                    "image_link": image_link,
                    "min_price": min_price
                }
                
                logger.info(f"✅ Регион {region_name}: цена от {min_price} руб., фото: {'есть' if not image_link.startswith('https://via.placeholder.com') else 'нет'}")
                
                return result
                
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке региона {region.get('name', 'Unknown')}: {e}")
                return None

    async def _get_country_regions(self, country_id: int) -> List[Dict]:
        """Получение списка регионов для страны"""
        try:
            logger.debug(f"🔍 Получаем регионы для страны {country_id}")
            
            # Правильный параметр для фильтрации по стране
            regions_data = await tourvisor_client.get_references("region", regcountry=country_id)
            
            # Проверяем структуру ответа - может быть вложенной
            regions = None
            if isinstance(regions_data, dict):
                # Попробуем найти регионы в разных местах структуры
                if "lists" in regions_data and "regions" in regions_data["lists"]:
                    regions = regions_data["lists"]["regions"].get("region", [])
                elif "region" in regions_data:
                    regions = regions_data["region"]
                else:
                    logger.warning(f"❌ Неожиданная структура ответа API: {list(regions_data.keys())}")
                    return []
            
            if not regions:
                logger.warning(f"❌ Нет данных о регионах в ответе API")
                return []
            
            if not isinstance(regions, list):
                regions = [regions] if regions else []
            
            logger.debug(f"📦 Получено из API: {len(regions)} регионов")
            
            # Фильтруем валидные регионы
            valid_regions = []
            for region in regions:
                region_id = region.get("id")
                region_name = region.get("name")
                
                if region_id and region_name:
                    try:
                        # Проверяем что ID валидный
                        int(region_id)
                        valid_regions.append({
                            "id": int(region_id),
                            "name": region_name.strip()
                        })
                    except (ValueError, TypeError):
                        logger.warning(f"⚠️ Некорректный ID региона: {region_id}")
                        continue
            
            logger.info(f"📍 Найдено {len(valid_regions)} валидных регионов для страны {country_id}")
            
            if len(valid_regions) == 0:
                logger.warning(f"❌ Нет валидных регионов для страны {country_id}. Проверьте API response.")
                # Логируем сырой ответ для отладки
                logger.debug(f"Raw regions data: {regions_data}")
            
            return valid_regions
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении регионов для страны {country_id}: {e}")
            return []

    async def _get_country_name(self, country_id: int) -> str:
        """Получение названия страны по ID"""
        try:
            countries_data = await tourvisor_client.get_references("country")
            
            # Проверяем структуру ответа
            countries = None
            if isinstance(countries_data, dict):
                if "lists" in countries_data and "countries" in countries_data["lists"]:
                    countries = countries_data["lists"]["countries"].get("country", [])
                elif "country" in countries_data:
                    countries = countries_data["country"]
                else:
                    logger.warning(f"❌ Неожиданная структура ответа countries API: {list(countries_data.keys())}")
                    return f"Страна {country_id}"
            
            if not countries:
                return f"Страна {country_id}"
            
            if not isinstance(countries, list):
                countries = [countries] if countries else []
            
            for country in countries:
                if country.get("id"):
                    try:
                        if int(country.get("id")) == country_id:
                            return country.get("name", f"Страна {country_id}")
                    except (ValueError, TypeError):
                        continue
            
            return f"Страна {country_id}"
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении названия страны {country_id}: {e}")
            return f"Страна {country_id}"

    async def clear_cities_cache(self) -> int:
        """Очистка кэша направлений по городам"""
        try:
            # Получаем все ключи кэша для городов
            pattern = "city_directions_*"
            # В зависимости от реализации cache_service, может потребоваться другой метод
            
            # Пример очистки (нужно адаптировать под ваш cache_service)
            cleared_count = 0
            for country_id in range(1, 50):  # Примерный диапазон ID стран
                cache_key = f"city_directions_{country_id}"
                if await self.cache.delete(cache_key):
                    cleared_count += 1
            
            logger.info(f"🧹 Очищено {cleared_count} записей кэша направлений по городам")
            
            return cleared_count
            
        except Exception as e:
            logger.error(f"❌ Ошибка при очистке кэша: {e}")
            return 0

    async def get_cities_status(self) -> Dict:
        """Получение статуса системы направлений по городам"""
        try:
            status = {
                "service_name": "CityDirectionsService",
                "cache_info": {
                    "ttl_hours": self.CITIES_CACHE_TTL // 3600,
                },
                "supported_countries": [],
                "last_updated": datetime.now().isoformat()
            }
            
            # Проверяем какие страны есть в кэше
            cached_countries = []
            for country_id in [47, 4, 2, 9, 1, 8, 13, 12, 46, 10, 3, 16, 40]:  # Страны из бара сайта
                cache_key = f"city_directions_{country_id}"
                cached_data = await self.cache.get(cache_key)
                if cached_data:
                    country_name = await self._get_country_name(country_id)
                    cached_countries.append({
                        "country_id": country_id,
                        "country_name": country_name,
                        "cities_count": len(cached_data),
                        "cached": True
                    })
            
            status["supported_countries"] = cached_countries
            
            return status
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении статуса: {e}")
            return {"error": str(e)}

    def _extract_image_from_raw(self, raw_data: Dict) -> str:
        """
        Извлекает только изображение из сырых данных API
        
        Returns:
            str: Ссылка на изображение или placeholder
        """
        try:
            # Ищем отели по пути data -> result -> hotel
            if "data" in raw_data and isinstance(raw_data["data"], dict):
                data = raw_data["data"]
                if "result" in data and isinstance(data["result"], dict):
                    result = data["result"]
                    if "hotel" in result and isinstance(result["hotel"], list):
                        hotels = result["hotel"]
                        
                        # Ищем фото в первом доступном отеле
                        for hotel in hotels:
                            if isinstance(hotel, dict):
                                photo_fields = ['picturelink', 'hotelpicture', 'picture', 'image']
                                for field in photo_fields:
                                    photo_url = hotel.get(field)
                                    if photo_url and isinstance(photo_url, str) and photo_url.startswith('http'):
                                        logger.debug(f"📸 Найдено фото в сырых данных: {photo_url}")
                                        return photo_url
            
            return "https://via.placeholder.com/300x200?text=No+Image"
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения фото из сырых данных: {e}")
            return "https://via.placeholder.com/300x200?text=No+Image"

    def get_country_id_by_name(self, country_name: str) -> Optional[int]:
        """Получение ID страны по названию из бара сайта"""
        return self.COUNTRIES_MAPPING.get(country_name)
    
    def get_all_supported_countries(self) -> List[Dict]:
        """Получение списка всех поддерживаемых стран"""
        return [
            {"id": country_id, "name": country_name}
            for country_name, country_id in self.COUNTRIES_MAPPING.items()
        ]

    def _extract_price_and_image_from_raw(self, raw_data: Dict) -> Optional[tuple]:
        """
        Извлекает минимальную цену и изображение из сырых данных API
        
        Returns:
            tuple: (min_price, image_link) или None если данных нет
        """
        try:
            # Проверяем разные возможные структуры ответа
            hotels = None
            
            # Список возможных путей к данным отелей
            possible_paths = [
                # Правильный путь согласно анализу структуры
                ["data", "result", "hotel"],
                # Альтернативные пути для совместимости
                ["result"],
                ["data", "result"], 
                ["data", "hotels"],
                ["data", "data", "result"],
                ["data"],
                ["hotels"],
                ["items"],
                ["results"]
            ]
            
            logger.debug(f"🔍 Анализируем структуру данных: {list(raw_data.keys())}")
            
            for path in possible_paths:
                try:
                    current_obj = raw_data
                    path_str = " -> ".join(path)
                    
                    for key in path:
                        if isinstance(current_obj, dict) and key in current_obj:
                            current_obj = current_obj[key]
                        else:
                            break
                    else:
                        # Дошли до конца пути успешно
                        if isinstance(current_obj, list) and current_obj:
                            # Проверяем, что это действительно отели
                            first_item = current_obj[0]
                            if isinstance(first_item, dict) and any(key in first_item for key in ['hotelname', 'hotelcode', 'tours']):
                                hotels = current_obj
                                logger.debug(f"✅ Найдены отели по пути: {path_str}")
                                break
                        elif isinstance(current_obj, dict):
                            # Может быть единственный отель
                            if any(key in current_obj for key in ['hotelname', 'hotelcode', 'tours']):
                                hotels = [current_obj]
                                logger.debug(f"✅ Найден единственный отель по пути: {path_str}")
                                break
                                
                except Exception as e:
                    logger.debug(f"⚠️ Ошибка при проверке пути {path_str}: {e}")
                    continue
            
            if not hotels:
                logger.info("❌ Не удалось найти отели в данных")
                logger.info(f"🔍 Доступные ключи верхнего уровня: {list(raw_data.keys())}")
                
                # Дополнительная диагностика
                if "data" in raw_data:
                    data_obj = raw_data["data"]
                    if isinstance(data_obj, dict):
                        logger.info(f"🔍 Ключи в data: {list(data_obj.keys())}")
                        
                        if "result" in data_obj:
                            result_obj = data_obj["result"]
                            if isinstance(result_obj, dict):
                                logger.info(f"🔍 Ключи в result: {list(result_obj.keys())}")
                            else:
                                logger.info(f"🔍 Тип result: {type(result_obj)}")
                    else:
                        logger.info(f"🔍 Тип data: {type(data_obj)}")
                
                return None
            
            logger.info(f"📦 Обрабатываем {len(hotels)} отелей из сырых данных")
            
            min_price = float('inf')
            image_link = "https://via.placeholder.com/300x200?text=No+Image"
            
            for i, hotel in enumerate(hotels):
                if not isinstance(hotel, dict):
                    continue
                    
                hotel_name = hotel.get('hotelname', f'Hotel_{i+1}')
                logger.info(f"🏨 Отель {i+1}: {hotel_name}")
                
                # Извлекаем фото отеля
                photo_fields = ['picturelink', 'hotelpicture', 'picture', 'image']
                for field in photo_fields:
                    hotel_picture = hotel.get(field)
                    if hotel_picture and isinstance(hotel_picture, str) and hotel_picture.startswith('http'):
                        image_link = hotel_picture
                        logger.info(f"📸 Найдено фото в поле {field}: {hotel_picture}")
                        break
                
                # Извлекаем цены из туров
                tours = hotel.get("tours", [])
                
                logger.info(f"🎯 Поле tours в отеле {hotel_name}: тип={type(tours)}, содержимое={str(tours)[:100]}...")
                
                # Нормализуем туры в список
                if isinstance(tours, dict):
                    tours = [tours]  # Если один тур пришел как объект
                    logger.info(f"   Преобразовано из dict в list с 1 элементом")
                elif not isinstance(tours, list):
                    logger.info(f"⚠️ Неожиданный тип туров: {type(tours)}")
                    continue
                
                logger.info(f"🎯 Найдено {len(tours)} туров в отеле {hotel_name}")
                
                for j, tour in enumerate(tours):
                    if not isinstance(tour, dict):
                        logger.warning(f"⚠️ Тур {j+1} не является словарем: {type(tour)}")
                        continue
                        
                    logger.info(f"   Тур {j+1}: ключи={list(tour.keys())}")
                    
                    try:
                        price = tour.get("price")
                        logger.info(f"   Цена из тура {j+1}: {repr(price)} (тип: {type(price)})")
                        
                        if price is not None:
                            # Пробуем преобразовать в число
                            if isinstance(price, str):
                                # Очищаем строку от лишних символов
                                price_str = ''.join(c for c in price if c.isdigit() or c == '.')
                                if price_str:
                                    price = float(price_str)
                                    logger.info(f"   Преобразована строка в число: {price}")
                                else:
                                    logger.warning(f"   Не удалось очистить строку цены: {repr(price)}")
                                    continue
                            else:
                                price = float(price)
                                logger.info(f"   Преобразовано в число: {price}")
                            
                            if price > 0 and price < min_price:
                                min_price = price
                                logger.info(f"💰 Новая минимальная цена: {price} (отель: {hotel_name})")
                                
                    except (ValueError, TypeError) as e:
                        logger.warning(f"⚠️ Ошибка парсинга цены в туре {j+1}: {e}")
                        continue
            
            if min_price == float('inf'):
                logger.info("❌ Не найдены валидные цены")
                return None
            
            logger.info(f"✅ Итоговая минимальная цена: {min_price}, фото: {image_link}")
            
            return (int(min_price), image_link)
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения данных из сырого ответа: {e}")
            return None

# Создаем экземпляр сервиса
city_directions_service = CityDirectionsService()