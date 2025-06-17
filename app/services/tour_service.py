import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

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

# Создаем экземпляр основного сервиса
tour_service = TourService()