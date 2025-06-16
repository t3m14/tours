import asyncio
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import random

from app.core.tourvisor_client import tourvisor_client
from app.services.cache_service import cache_service
from app.models.tour import (
    TourSearchRequest, SearchResponse, SearchResult, SearchStatus,
    HotelInfo, TourInfo, RandomTourRequest, DirectionInfo, HotTourInfo,
    TourActualizationRequest, DetailedTourInfo
)
from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class TourService:
    def __init__(self):
        self.cache = cache_service
        
    async def search_tours(self, search_request: TourSearchRequest) -> SearchResponse:
        """Запуск поиска туров"""
        try:
            # Подготовка параметров для TourVisor API
            search_params = search_request.dict(exclude_none=True)
            
            # Автоматическое заполнение дат если не указаны
            if not search_params.get("datefrom"):
                tomorrow = datetime.now() + timedelta(days=1)
                search_params["datefrom"] = tomorrow.strftime("%d.%m.%Y")
            
            if not search_params.get("dateto"):
                week_later = datetime.now() + timedelta(days=8)
                search_params["dateto"] = week_later.strftime("%d.%m.%Y")
            
            request_id = await tourvisor_client.search_tours(search_params)
            
            # Сохраняем параметры поиска в кэш для отслеживания
            await self.cache.set(
                f"search_params:{request_id}",
                search_params,
                ttl=7200  # 2 часа
            )
            
            return SearchResponse(request_id=request_id)
            
        except Exception as e:
            logger.error(f"Ошибка при запуске поиска туров: {e}")
            raise
    
    async def get_search_status(self, request_id: str) -> SearchStatus:
        """Получение статуса поиска"""
        try:
            result = await tourvisor_client.get_search_status(request_id)
            status_data = result.get("data", {}).get("status", {})
            
            return SearchStatus(
                state=status_data.get("state", "searching"),
                hotelsfound=int(status_data.get("hotelsfound", 0)),
                toursfound=int(status_data.get("toursfound", 0)),
                minprice=float(status_data.get("minprice", 0)) if status_data.get("minprice") else None,
                progress=int(status_data.get("progress", 0)),
                timepassed=int(status_data.get("timepassed", 0))
            )
            
        except Exception as e:
            logger.error(f"Ошибка при получении статуса поиска: {e}")
            raise
    
    async def get_search_results(self, request_id: str, page: int = 1, onpage: int = 25) -> SearchResult:
        """Получение результатов поиска"""
        try:
            result = await tourvisor_client.get_search_results(request_id, page, onpage)
            data = result.get("data", {})
            
            # Парсинг статуса
            status_data = data.get("status", {})
            status = SearchStatus(
                state=status_data.get("state", "searching"),
                hotelsfound=int(status_data.get("hotelsfound", 0)),
                toursfound=int(status_data.get("toursfound", 0)),
                minprice=float(status_data.get("minprice", 0)) if status_data.get("minprice") else None,
                progress=int(status_data.get("progress", 0)),
                timepassed=int(status_data.get("timepassed", 0))
            )
            
            # Парсинг результатов
            hotels = []
            result_data = data.get("result", {})
            hotel_list = result_data.get("hotel", [])
            
            if not isinstance(hotel_list, list):
                hotel_list = [hotel_list] if hotel_list else []
            
            for hotel_data in hotel_list:
                tours = []
                tour_list = hotel_data.get("tours", {}).get("tour", [])
                
                if not isinstance(tour_list, list):
                    tour_list = [tour_list] if tour_list else []
                
                for tour_data in tour_list:
                    tour = TourInfo(**tour_data)
                    tours.append(tour)
                
                hotel = HotelInfo(
                    **{k: v for k, v in hotel_data.items() if k != "tours"},
                    tours=tours
                )
                hotels.append(hotel)
            
            return SearchResult(status=status, result=hotels)
            
        except Exception as e:
            logger.error(f"Ошибка при получении результатов поиска: {e}")
            raise
    
    async def continue_search(self, request_id: str) -> Dict[str, Any]:
        """Продолжение поиска для получения больше результатов"""
        try:
            return await tourvisor_client.continue_search(request_id)
        except Exception as e:
            logger.error(f"Ошибка при продолжении поиска: {e}")
            raise
    
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
                    
                    # Ждем результатов поиска с увеличенным временем ожидания
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
            # Увеличиваем время ожидания до 30 секунд и проверяем статус чаще
            max_attempts = 30
            for attempt in range(max_attempts):
                await asyncio.sleep(1)
                
                try:
                    status_result = await tourvisor_client.get_search_status(request_id)
                    status_data = status_result.get("data", {}).get("status", {})
                    state = status_data.get("state", "searching")
                    progress = status_data.get("progress", 0)
                    hotels_found = status_data.get("hotelsfound", 0)
                    
                    logger.debug(f"🔄 Попытка {attempt+1}/{max_attempts}: статус = {state}, прогресс = {progress}%, отелей = {hotels_found}")
                    
                    # Проверяем есть ли уже отели или поиск завершен
                    if state == "finished" or (progress >= 50 and hotels_found > 0):
                        logger.info(f"✅ Поиск готов: состояние={state}, прогресс={progress}%, отелей={hotels_found}")
                        break
                        
                except Exception as status_error:
                    logger.warning(f"⚠️ Ошибка получения статуса {attempt+1}: {status_error}")
                    continue
            else:
                logger.warning(f"⏰ Таймаут ожидания поиска {request_id} после {max_attempts} попыток")
                
                # Попробуем получить результаты даже при таймауте
                try:
                    logger.info("🔄 Попытка получения частичных результатов...")
                    results = await tourvisor_client.get_search_results(request_id, 1, 5)
                    data = results.get("data", {})
                    
                    # Проверяем есть ли хоть что-то
                    status_data = data.get("status", {})
                    hotels_found = status_data.get("hotelsfound", 0)
                    
                    if hotels_found > 0:
                        logger.info(f"✅ Найдены частичные результаты: {hotels_found} отелей")
                    else:
                        logger.warning("❌ Нет результатов даже при таймауте")
                        return None
                        
                except Exception as partial_error:
                    logger.error(f"❌ Ошибка получения частичных результатов: {partial_error}")
                    return None
            
            # Получаем результаты
            try:
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
                
            except Exception as results_error:
                logger.error(f"❌ Ошибка при получении результатов: {results_error}")
                return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении тура из поиска: {e}")
            return None
    
    def _convert_search_result_to_hot_tour(self, hotel_data: Dict, tour_data: Dict, search_params: Dict) -> Dict[str, Any]:
        """Конвертация результата поиска в формат HotTourInfo"""
        
        # Получаем название города и страны
        country_name = self._get_country_name(search_params["country"])
        city_name = self._get_city_name(search_params["departure"])
        
        return {
            "countrycode": str(search_params["country"]),
            "countryname": country_name,
            "departurecode": str(search_params["departure"]),
            "departurename": city_name,
            "departurenamefrom": self._get_city_name_from(search_params["departure"]),
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
    
    def _get_city_name(self, city_code: int) -> str:
        """Получение названия города по коду"""
        city_map = {
            1: "Москва",
            2: "Пермь", 
            3: "Екатеринбург",
            4: "Уфа",
            5: "С.Петербург"
        }
        return city_map.get(city_code, f"Город {city_code}")
    
    def _get_city_name_from(self, city_code: int) -> str:
        """Получение названия города в родительном падеже"""
        city_map = {
            1: "Москвы",
            2: "Перми",
            3: "Екатеринбурга", 
            4: "Уфы",
            5: "Санкт-Петербурга"
        }
        return city_map.get(city_code, f"Города {city_code}")

    async def get_directions_with_prices(self) -> List[DirectionInfo]:
        """Получение списка направлений с минимальными ценами через поиск"""
        cache_key = "directions_with_prices_search"
        
        # Попытка получить из кэша
        cached_directions = await self.cache.get(cache_key)
        if cached_directions:
            return [DirectionInfo(**direction) for direction in cached_directions]
        
        return await self._generate_directions_via_search()
    
    async def _generate_directions_via_search(self) -> List[DirectionInfo]:
        """Генерация направлений с ценами через поиск"""
        cache_key = "directions_with_prices_search"  # ИСПРАВЛЕНО: добавили определение переменной
        
        try:
            directions = []
            
            # Берем популярные страны
            popular_countries = settings.POPULAR_COUNTRIES[:6]  # Первые 6 стран
            
            for country_code in popular_countries:
                try:
                    # Находим название страны
                    country_name = self._get_country_name(country_code)
                    
                    # Запускаем быстрый поиск для получения минимальной цены
                    search_params = {
                        "departure": 1,  # Москва
                        "country": country_code,
                        "datefrom": (datetime.now() + timedelta(days=7)).strftime("%d.%m.%Y"),
                        "dateto": (datetime.now() + timedelta(days=14)).strftime("%d.%m.%Y"),
                        "nightsfrom": 7,
                        "nightsto": 10,
                        "adults": 2,
                        "child": 0
                    }
                    
                    request_id = await tourvisor_client.search_tours(search_params)
                    
                    # Ждем результатов с увеличенным временем
                    min_price = await self._get_min_price_from_search(request_id)
                    
                    direction = DirectionInfo(
                        name=country_name,
                        image_link=f"https://via.placeholder.com/300x200/4a90e2/ffffff?text={country_name}",
                        min_price=min_price
                    )
                    directions.append(direction)
                    
                    logger.info(f"✅ Направление {country_name}: мин. цена {min_price}")
                    
                    # Задержка между запросами
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка при обработке страны {country_code}: {e}")
                    continue
            
            # Кэшируем на 6 часов
            if directions:
                await self.cache.set(
                    cache_key, 
                    [direction.dict() for direction in directions], 
                    ttl=21600
                )
            
            return directions
            
        except Exception as e:
            logger.error(f"❌ Ошибка при генерации направлений: {e}")
            return []
    
    async def _get_min_price_from_search(self, request_id: str) -> float:
        """Получение минимальной цены из поиска"""
        try:
            # Ждем до 15 секунд
            for attempt in range(15):
                await asyncio.sleep(1)
                
                try:
                    status_result = await tourvisor_client.get_search_status(request_id)
                    status_data = status_result.get("data", {}).get("status", {})
                    
                    state = status_data.get("state", "searching")
                    min_price = status_data.get("minprice")
                    progress = status_data.get("progress", 0)
                    
                    # Если есть минимальная цена или достаточный прогресс
                    if min_price or state == "finished" or progress >= 50:
                        if min_price:
                            return float(min_price)
                        
                        # Попробуем получить из результатов
                        results = await tourvisor_client.get_search_results(request_id, 1, 5)
                        price = self._extract_min_price_from_results(results)
                        if price < 500000:  # Разумная цена
                            return price
                        
                except Exception as e:
                    logger.warning(f"Ошибка получения статуса: {e}")
                    continue
            
            # Если не получили цену, возвращаем дефолтную
            return 50000.0
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения минимальной цены: {e}")
            return 50000.0
    
    def _extract_min_price_from_results(self, results: Dict[str, Any]) -> float:
        """Извлечение минимальной цены из результатов поиска"""
        try:
            data = results.get("data", {})
            
            # Проверяем статус
            status = data.get("status", {})
            min_price_from_status = status.get("minprice")
            if min_price_from_status:
                return float(min_price_from_status)
            
            # Ищем в результатах
            result_data = data.get("result", {})
            hotel_list = result_data.get("hotel", [])
            
            if not isinstance(hotel_list, list):
                hotel_list = [hotel_list] if hotel_list else []
            
            prices = []
            for hotel in hotel_list:
                hotel_price = hotel.get("price")
                if hotel_price:
                    prices.append(float(hotel_price))
                
                # Также проверяем цены туров
                tours = hotel.get("tours", {}).get("tour", [])
                if not isinstance(tours, list):
                    tours = [tours] if tours else []
                
                for tour in tours:
                    tour_price = tour.get("price")
                    if tour_price:
                        prices.append(float(tour_price))
            
            return min(prices) if prices else 50000.0
            
        except Exception as e:
            logger.error(f"❌ Ошибка при извлечении цены: {e}")
            return 50000.0  # Дефолтная цена

    async def actualize_tour(self, request: TourActualizationRequest) -> DetailedTourInfo:
        """Актуализация тура"""
        try:
            # Простая актуализация
            basic_info = await tourvisor_client.actualize_tour(
                request.tour_id,
                request.request_check
            )
            
            # Детальная актуализация с рейсами
            detailed_info = await tourvisor_client.get_detailed_actualization(
                request.tour_id
            )
            
            return DetailedTourInfo(
                tour=basic_info.get("tour", {}),
                flights=detailed_info.get("flights", []),
                tourinfo=detailed_info.get("tourinfo", {})
            )
            
        except Exception as e:
            logger.error(f"Ошибка при актуализации тура: {e}")
            raise
    
    async def search_tour_by_id(self, tour_id: str) -> Optional[Dict[str, Any]]:
        """Поиск тура по ID"""
        try:
            return await self.actualize_tour(
                TourActualizationRequest(tour_id=tour_id, request_check=2)
            )
        except Exception as e:
            logger.error(f"Ошибка при поиске тура по ID: {e}")
            return None
    
    async def search_tours_by_hotel_name(self, hotel_name: str, country_code: int) -> List[HotelInfo]:
        """Поиск туров по названию отеля"""
        try:
            # Получаем список отелей страны
            hotels_data = await tourvisor_client.get_references(
                "hotel",
                hotcountry=country_code
            )
            
            hotels = hotels_data.get("hotel", [])
            if not isinstance(hotels, list):
                hotels = [hotels] if hotels else []
            
            # Ищем отель по названию
            matching_hotels = [
                hotel for hotel in hotels
                if hotel_name.lower() in hotel.get("name", "").lower()
            ]
            
            if not matching_hotels:
                return []
            
            # Для найденных отелей запускаем поиск туров
            results = []
            for hotel in matching_hotels[:5]:  # Ограничиваем количество
                hotel_code = hotel.get("id")
                
                # Запускаем поиск туров в этом отеле
                search_request = TourSearchRequest(
                    departure=1,  # Москва по умолчанию
                    country=country_code,
                    hotels=str(hotel_code)
                )
                
                search_response = await self.search_tours(search_request)
                
                # Ждем завершения поиска
                for _ in range(15):  # Максимум 15 попыток
                    await asyncio.sleep(2)
                    status = await self.get_search_status(search_response.request_id)
                    if status.state == "finished" or status.progress >= 50:
                        break
                
                # Получаем результаты
                search_results = await self.get_search_results(search_response.request_id)
                if search_results.result:
                    results.extend(search_results.result)
            
            return results
            
        except Exception as e:
            logger.error(f"Ошибка при поиске туров по названию отеля: {e}")
            return []

# Создаем экземпляр сервиса
tour_service = TourService()