import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import time
from app.core.tourvisor_client import tourvisor_client
from app.services.cache_service import cache_service
from app.models.tour import (
    TourSearchRequest, SearchResponse, SearchResult, SearchStatus,
    HotelInfo, TourInfo, TourActualizationRequest, DetailedTourInfo
)
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class TourService:
    """Основной сервис для работы с турами"""
    
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
    
        
    # app/services/tour_service.py - добавить в начало actualize_tour

    async def actualize_tour(self, request: TourActualizationRequest) -> DetailedTourInfo:
        """Актуализация тура с детальным логированием"""
        try:
            # 🔍 КРИТИЧЕСКИ ВАЖНОЕ ЛОГИРОВАНИЕ
            logger.error(f"🆔 TOUR_ID ЗАПРОС: {request.tour_id}")
            logger.error(f"🆔 REQUEST_CHECK: {request.request_check}")
            logger.error(f"🆔 CURRENCY: {request.currency}")
            
            # Время начала для измерения производительности
            start_time = time.time()
            
            logger.info(f"🔍 Начинаем актуализацию тура {request.tour_id}")
            
            # ТОЛЬКО ОДИН запрос - actdetail.php
            detailed_info = await tourvisor_client.get_detailed_actualization(request.tour_id)
            
            end_time = time.time()
            logger.error(f"⏱️ ВРЕМЯ ВЫПОЛНЕНИЯ: {end_time - start_time:.2f} секунд")
            
            # Проверяем что получили
            if not detailed_info:
                logger.error(f"❌ ПУСТОЙ ОТВЕТ от actdetail.php для tour_id: {request.tour_id}")
                return DetailedTourInfo(tour={}, flights=[], tourinfo={})
            
            # Логируем структуру ответа  
            logger.error(f"📊 КЛЮЧИ В ОТВЕТЕ: {list(detailed_info.keys()) if isinstance(detailed_info, dict) else 'НЕ СЛОВАРЬ'}")
            
            # Извлекаем данные
            tour_data = detailed_info.get("tour", {})
            flights_data = detailed_info.get("flights", [])
            tourinfo_data = detailed_info.get("tourinfo", {})
            
            # Логируем количество рейсов
            logger.error(f"✈️ КОЛИЧЕСТВО ВАРИАНТОВ РЕЙСОВ: {len(flights_data) if isinstance(flights_data, list) else 'НЕ СПИСОК'}")
            
            # Если нет tour данных в actdetail, берем из actualize.php
            if not tour_data:
                logger.warning(f"⚠️ НЕТ tour данных в actdetail.php, делаем fallback запрос")
                basic_info = await tourvisor_client.actualize_tour(
                    request.tour_id,
                    request.request_check
                )
                tour_data = basic_info.get("data", {}).get("tour", {}) if basic_info else {}
                logger.error(f"📋 FALLBACK tour данные получены: {bool(tour_data)}")
            
            # Обрабатываем flights как есть, без изменений
            processed_flights = []
            if flights_data and isinstance(flights_data, list):
                for i, flight_group in enumerate(flights_data):
                    if isinstance(flight_group, dict):
                        # Логируем каждый рейс для отладки
                        logger.error(f"✈️ РЕЙС {i+1}: {flight_group.get('dateforward')} → {flight_group.get('datebackward')}, default: {flight_group.get('isdefault')}")
                        
                        processed_flights.append({
                            "forward": flight_group.get("forward", []),
                            "backward": flight_group.get("backward", []),
                            "dateforward": flight_group.get("dateforward", ""),
                            "datebackward": flight_group.get("datebackward", ""),
                            "price": flight_group.get("price", {}),
                            "fuelcharge": flight_group.get("fuelcharge", {}),
                            "isdefault": flight_group.get("isdefault", False)
                        })
            
            result = DetailedTourInfo(
                tour=tour_data,
                flights=processed_flights,
                tourinfo=tourinfo_data
            )
            
            logger.error(f"✅ ИТОГ: tour_id={request.tour_id}, рейсов={len(processed_flights)}, tour_данных={bool(tour_data)}")
            return result
            
        except Exception as e:
            logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА tour_id {request.tour_id}: {e}")
            logger.error(f"❌ ТИП ОШИБКИ: {type(e)}")
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
                for _ in range(10):  # Максимум 10 попыток
                    await asyncio.sleep(1)
                    status = await self.get_search_status(search_response.request_id)
                    if status.state == "finished":
                        break
                
                # Получаем результаты
                search_results = await self.get_search_results(search_response.request_id)
                if search_results.result:
                    results.extend(search_results.result)
            
            return results
            
        except Exception as e:
            logger.error(f"Ошибка при поиске туров по названию отеля: {e}")
            return []

    def _get_country_name(self, country_code: int) -> str:
        """Получение названия страны по коду (расширенный список)"""
        country_map = {
            1: "Египет",
            4: "Турция", 
            8: "Греция",
            9: "Кипр",
            11: "Болгария",
            15: "ОАЭ",
            16: "Тунис",
            17: "Черногория",
            19: "Испания",
            20: "Италия",
            22: "Таиланд",
            23: "Индия",
            24: "Шри-Ланка",
            25: "Вьетнам",
            26: "Китай",
            27: "Индонезия",
            28: "Малайзия",
            29: "Сингапур",
            30: "Филиппины",
            31: "Маврикий",
            32: "Сейшелы",
            33: "Танзания",
            34: "Кения",
            35: "Мальдивы"
        }
        return country_map.get(country_code, f"Страна {country_code}")
    
    def _get_city_name(self, city_code: int) -> str:
        """Получение названия города по коду (расширенный список)"""
        city_map = {
            1: "Москва",
            2: "Пермь", 
            3: "Екатеринбург",
            4: "Уфа",
            5: "Санкт-Петербург",
            6: "Казань",
            7: "Нижний Новгород",
            8: "Самара",
            9: "Ростов-на-Дону",
            10: "Краснодар",
            11: "Волгоград",
            12: "Воронеж",
            13: "Саратов",
            14: "Тольятти",
            15: "Ижевск"
        }
        return city_map.get(city_code, f"Город {city_code}")
    
    def _get_city_name_from(self, city_code: int) -> str:
        """Получение названия города в родительном падеже (расширенный список)"""
        city_map = {
            1: "Москвы",
            2: "Перми",
            3: "Екатеринбурга", 
            4: "Уфы",
            5: "Санкт-Петербурга",
            6: "Казани",
            7: "Нижнего Новгорода",
            8: "Самары",
            9: "Ростова-на-Дону",
            10: "Краснодара",
            11: "Волгограда",
            12: "Воронежа",
            13: "Саратова",
            14: "Тольятти",
            15: "Ижевска"
        }
        return city_map.get(city_code, f"Города {city_code}")

# Создаем экземпляр основного сервиса
tour_service = TourService()