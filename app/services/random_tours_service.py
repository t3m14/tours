import asyncio
import random
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from app.core.tourvisor_client import tourvisor_client
from app.services.cache_service import cache_service
from app.services.tour_service import tour_service
from app.models.tour import RandomTourRequest, HotTourInfo
from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class RandomToursService:
    """Сервис для работы со случайными турами"""
    
    def __init__(self):
        self.cache = cache_service
    
    async def get_random_tours(self, request: RandomTourRequest) -> List[HotTourInfo]:
        """Получение случайных туров через обычный поиск"""
        cache_key = "random_tours_from_search"
        
        logger.info(f"🎯 Запрос случайных туров через поиск, count={request.count}")
        
        # Попытка получить из кэша
        try:
            cached_tours = await self.cache.get(cache_key)
            logger.info(f"💾 Проверка кэша: найдено {len(cached_tours) if cached_tours else 0} туров")
            
            if cached_tours:
                # Преобразуем данные из кэша обратно в объекты
                tours_list = []
                for tour_data in cached_tours[:request.count]:
                    try:
                        tour = HotTourInfo(**tour_data)
                        tours_list.append(tour)
                    except Exception as e:
                        logger.error(f"❌ Ошибка при создании объекта тура из кэша: {e}")
                        continue
                
                logger.info(f"✅ Возвращено {len(tours_list)} туров из кэша")
                return tours_list
        except Exception as e:
            logger.error(f"❌ Ошибка при работе с кэшем: {e}")
        
        # Генерация новых случайных туров через поиск
        logger.info("🔄 Кэш пуст, генерируем новые туры через поиск")
        return await self._generate_random_tours_via_search(request.count)
    
    async def _generate_random_tours_via_search(self, count: int) -> List[HotTourInfo]:
        """Генерация случайных туров через обычный поиск"""
        logger.info(f"🚀 НАЧИНАЕМ ГЕНЕРАЦИЮ {count} ТУРОВ ЧЕРЕЗ ПОИСК")
        
        try:
            random_tours = []
            countries = settings.POPULAR_COUNTRIES.copy()
            cities = settings.DEPARTURE_CITIES.copy()
            
            logger.info(f"📍 Доступные страны: {countries}")
            logger.info(f"🏙️ Доступные города: {cities}")
            
            # Создаем различные поисковые запросы
            search_variants = self._create_search_variants(countries, cities, count)
            logger.info(f"🔍 Создано {len(search_variants)} поисковых вариантов")
            
            for i, search_params in enumerate(search_variants):
                if len(random_tours) >= count:
                    logger.info(f"✅ Достигнуто нужное количество туров ({count})")
                    break
                
                try:
                    logger.info(f"📡 Поиск {i+1}/{len(search_variants)}: {search_params['country']} из города {search_params['departure']}")
                    
                    # Запускаем поиск
                    request_id = await tourvisor_client.search_tours(search_params)
                    logger.info(f"📝 Получен request_id: {request_id}")
                    
                    # Ждем результатов поиска
                    tour_found = await self._wait_and_get_tour_from_search(request_id, search_params)
                    
                    if tour_found:
                        random_tours.append(tour_found)
                        logger.info(f"✅ Добавлен тур {len(random_tours)}: {tour_found.hotelname} в {tour_found.countryname}")
                    else:
                        logger.warning(f"⚠️ Не найдено туров для варианта {i+1}")
                    
                    # Задержка между поисками
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"💥 Ошибка при поиске варианта {i+1}: {e}")
                    continue
            
            logger.info(f"🏁 ГЕНЕРАЦИЯ ЗАВЕРШЕНА. Получено туров: {len(random_tours)}")
            
            if random_tours:
                # Кэшируем результат
                try:
                    await self.cache.set(
                        "random_tours_from_search",
                        [tour.dict() for tour in random_tours],
                        ttl=settings.POPULAR_TOURS_CACHE_TTL
                    )
                    logger.info(f"💾 Туры сохранены в кэш")
                except Exception as cache_error:
                    logger.error(f"❌ Ошибка сохранения в кэш: {cache_error}")
            else:
                logger.warning("⚠️ Не удалось создать ни одного тура через поиск")
            
            return random_tours
            
        except Exception as e:
            logger.error(f"💥 Критическая ошибка при генерации туров: {e}")
            return []
    
    def _create_search_variants(self, countries: List[int], cities: List[int], count: int) -> List[Dict[str, Any]]:
        """Создание вариантов поисковых запросов"""
        variants = []
        
        # Базовые даты
        base_dates = [
            (7, 14),   # через неделю на неделю
            (14, 21),  # через 2 недели на неделю  
            (21, 28),  # через 3 недели на неделю
        ]
        
        # Варианты ночей
        nights_variants = [
            (7, 10),   # стандартный отпуск
            (10, 14),  # длинный отпуск
            (3, 7),    # короткий отпуск
        ]
        
        for i in range(count * 2):  # Создаем больше вариантов чем нужно
            country = random.choice(countries)
            city = random.choice(cities)
            date_variant = random.choice(base_dates)
            nights_variant = random.choice(nights_variants)
            
            # Вычисляем даты
            start_offset, end_offset = date_variant
            start_date = datetime.now() + timedelta(days=start_offset)
            end_date = datetime.now() + timedelta(days=end_offset)
            
            variant = {
                "departure": city,
                "country": country,
                "datefrom": start_date.strftime("%d.%m.%Y"),
                "dateto": end_date.strftime("%d.%m.%Y"),
                "nightsfrom": nights_variant[0],
                "nightsto": nights_variant[1],
                "adults": random.choice([2, 2, 2, 4]),  # чаще 2 взрослых
                "child": random.choice([0, 0, 0, 1, 2]),  # чаще без детей
                "stars": random.choice([3, 4, 5]),  # только хорошие отели
            }
            
            variants.append(variant)
        
        return variants
    
    async def _wait_and_get_tour_from_search(self, request_id: str, search_params: Dict[str, Any]) -> Optional[HotTourInfo]:
        """Ожидание результатов поиска и получение одного случайного тура"""
        try:
            # Ждем завершения поиска (максимум 10 секунд)
            for attempt in range(10):
                await asyncio.sleep(1)
                
                status_result = await tourvisor_client.get_search_status(request_id)
                status_data = status_result.get("data", {}).get("status", {})
                state = status_data.get("state", "searching")
                
                logger.debug(f"🔄 Попытка {attempt+1}: статус = {state}")
                
                if state == "finished":
                    break
            else:
                logger.warning(f"⏰ Таймаут ожидания поиска {request_id}")
                return None
            
            # Получаем результаты
            results = await tourvisor_client.get_search_results(request_id, 1, 10)
            data = results.get("data", {})
            result_data = data.get("result", {})
            hotel_list = result_data.get("hotel", [])
            
            if not isinstance(hotel_list, list):
                hotel_list = [hotel_list] if hotel_list else []
            
            if not hotel_list:
                logger.debug(f"📭 Нет отелей в результатах поиска")
                return None
            
            # Выбираем случайный отель
            random_hotel = random.choice(hotel_list)
            tours_data = random_hotel.get("tours", {}).get("tour", [])
            
            if not isinstance(tours_data, list):
                tours_data = [tours_data] if tours_data else []
            
            if not tours_data:
                logger.debug(f"📭 Нет туров в отеле")
                return None
            
            # Выбираем случайный тур
            random_tour_data = random.choice(tours_data)
            
            # Преобразуем в формат HotTourInfo
            hot_tour_data = self._convert_search_result_to_hot_tour(
                random_hotel, random_tour_data, search_params
            )
            
            return HotTourInfo(**hot_tour_data)
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении тура из поиска: {e}")
            return None
    
    def _convert_search_result_to_hot_tour(self, hotel_data: Dict, tour_data: Dict, search_params: Dict) -> Dict[str, Any]:
        """Конвертация результата поиска в формат HotTourInfo"""
        
        # Получаем название города и страны
        country_name = tour_service._get_country_name(search_params["country"])
        city_name = tour_service._get_city_name(search_params["departure"])
        
        return {
            "countrycode": str(search_params["country"]),
            "countryname": country_name,
            "departurecode": str(search_params["departure"]),
            "departurename": city_name,
            "departurenamefrom": tour_service._get_city_name_from(search_params["departure"]),
            "operatorcode": tour_data.get("operatorcode", ""),
            "operatorname": tour_data.get("operatorname", ""),
            "hotelcode": hotel_data.get("hotelcode", ""),
            "hotelname": hotel_data.get("hotelname", ""),
            "hotelstars": hotel_data.get("hotelstars", 3),
            "hotelregioncode": hotel_data.get("regioncode", ""),
            "hotelregionname": hotel_data.get("regionname", ""),
            "hotelpicture": hotel_data.get("picturelink", ""),
            "fulldesclink": hotel_data.get("fulldesclink", ""),
            "flydate": tour_data.get("flydate", ""),
            "nights": tour_data.get("nights", 7),
            "meal": tour_data.get("mealrussian", tour_data.get("meal", "")),
            "price": float(tour_data.get("price", 0)),
            "priceold": None,  # В обычном поиске нет старой цены
            "currency": tour_data.get("currency", "RUB")
        }

# Создаем экземпляр сервиса случайных туров
random_tours_service = RandomToursService()