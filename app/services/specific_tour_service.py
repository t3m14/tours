# app/services/specific_tour_service.py

import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from app.core.tourvisor_client import tourvisor_client
from app.services.cache_service import cache_service
from app.models.tour import FoundTourInfo, SpecificTourSearchRequest
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class SpecificTourService:
    """Сервис для поиска конкретных туров по критериям"""
    
    def __init__(self):
        self.cache = cache_service
    
    async def find_specific_tour(self, search_request: SpecificTourSearchRequest) -> Dict[str, Any]:
        """Поиск конкретного тура по заданным критериям - возвращает словарь с hotel_info и tours"""
        try:
            logger.info(f"🔎 Начинаем поиск конкретного тура")
            
            # Выполняем основной поиск
            tour = await self._execute_tour_search(search_request)
            
            if tour:
                logger.info(f"✅ Основной поиск успешен")
                return tour
            
            # Если основной поиск не дал результатов, пробуем fallback
            logger.info(f"🔄 Основной поиск не дал результатов, пробуем fallback")
            tour = await self._execute_fallback_search(search_request)
            
            if tour:
                logger.info(f"✅ Fallback поиск успешен")
                return tour
            else:
                raise ValueError("Тур не найден по заданным критериям")
                
        except Exception as e:
            logger.error(f"❌ Ошибка поиска конкретного тура: {e}")
            raise

    async def find_single_tour(self, search_request: SpecificTourSearchRequest) -> FoundTourInfo:
        """Поиск ОДНОГО лучшего тура - возвращает FoundTourInfo"""
        try:
            logger.info(f"🎯 Поиск одного лучшего тура")
            
            # Получаем отель со всеми турами
            hotel_with_tours = await self.find_specific_tour(search_request)
            
            if not hotel_with_tours or not hotel_with_tours.get('tours'):
                raise ValueError("Туры не найдены")
            
            # Берем лучший тур (первый в отсортированном списке)
            best_tour = hotel_with_tours['tours'][0]
            hotel_info = hotel_with_tours['hotel_info']
            
            logger.info(f"🎯 Создаем FoundTourInfo из отеля: {hotel_info.get('hotel_name', 'Unknown')}")
            
            # Создаем объект FoundTourInfo с обязательными полями
            found_tour_info = FoundTourInfo(
                # Информация об отеле - ОБЯЗАТЕЛЬНЫЕ ПОЛЯ
                hotel_name=hotel_info.get('hotel_name') or '',
                hotel_stars=hotel_info.get('hotel_stars') or 0,
                country_name=hotel_info.get('country_name') or '',
                region_name=hotel_info.get('region_name') or '',
                
                # Информация о туре - ОБЯЗАТЕЛЬНЫЕ ПОЛЯ
                operator_name=best_tour.get('operator_name') or '',
                fly_date=best_tour.get('fly_date') or '',
                nights=best_tour.get('nights') or search_request.nights or 7,
                price=best_tour.get('price') or 0.0,
                meal=best_tour.get('meal') or '',
                room_type=best_tour.get('room_type') or '',
                adults=best_tour.get('adults') or search_request.adults,
                children=best_tour.get('children') or search_request.children,
                currency=best_tour.get('currency') or 'RUB',
                
                # Опциональные поля отеля
                hotel_id=hotel_info.get('hotel_id'),
                hotel_rating=hotel_info.get('hotel_rating'),
                hotel_description=hotel_info.get('hotel_description'),
                hotel_picture=hotel_info.get('hotel_picture'),
                sea_distance=hotel_info.get('sea_distance'),
                
                # Опциональные поля тура
                tour_id=best_tour.get('tour_id'),
                fuel_charge=best_tour.get('fuel_charge'),
                tour_link=best_tour.get('tour_link'),
                
                # Дополнительная информация
                is_regular=best_tour.get('is_regular', False),
                is_promo=best_tour.get('is_promo', False),
                is_on_request=best_tour.get('is_on_request', False),
                search_results_count=hotel_with_tours.get('search_results_count', 1),
                hotels_found=hotel_with_tours.get('hotels_found', 1),
                is_fallback=hotel_with_tours.get('is_fallback', False),
                fallback_strategy=hotel_with_tours.get('fallback_strategy')
            )
            
            logger.info(f"✅ Успешно создан FoundTourInfo для отеля: {found_tour_info.hotel_name}")
            return found_tour_info
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания FoundTourInfo: {e}")
            raise

    async def find_tour_by_hotel_name(self, hotel_name: str, departure: int, country: int, 
                                nights: int = 7, adults: int = 2, children: int = 0) -> FoundTourInfo:
        """Упрощенный поиск тура по названию отеля"""
        logger.info(f"🏨 Поиск тура по отелю '{hotel_name}' в стране {country}")
        
        search_request = SpecificTourSearchRequest(
            departure=departure,
            country=country,
            hotel_name=hotel_name,
            nights=nights,
            adults=adults,
            children=children
        )
        
        return await self.find_single_tour(search_request)

    async def find_tour_by_criteria(self, departure: int, country: int, hotel_stars: int,
                                  meal_type: int, max_price: Optional[int] = None,
                                  nights: int = 7, adults: int = 2) -> FoundTourInfo:
        """Поиск тура по основным критериям - возвращает FoundTourInfo"""
        search_request = SpecificTourSearchRequest(
            departure=departure,
            country=country,
            hotel_stars=hotel_stars,
            meal_type=meal_type,
            max_price=max_price,
            nights=nights,
            adults=adults
        )
        return await self.find_single_tour(search_request)

    def get_search_suggestions(self, search_request: SpecificTourSearchRequest) -> List[str]:
        """Получение предложений по изменению критериев поиска"""
        suggestions = []
        
        if search_request.hotel_stars and search_request.hotel_stars > 3:
            suggestions.append(f"Попробуйте снизить звездность до {search_request.hotel_stars - 1} звезд")
        
        if search_request.max_price and search_request.max_price < 100000:
            suggestions.append(f"Увеличьте максимальную цену до {search_request.max_price + 20000} рублей")
        
        if search_request.meal_type and search_request.meal_type > 2:
            suggestions.append("Попробуйте изменить тип питания на 'Завтрак' или 'Без питания'")
        
        if search_request.nights and search_request.nights > 7:
            suggestions.append(f"Попробуйте сократить количество ночей до {search_request.nights - 1}")
        
        if search_request.rating and search_request.rating > 4.0:
            suggestions.append("Снизьте минимальный рейтинг отеля")
        
        suggestions.append("Попробуйте изменить даты поездки")
        suggestions.append("Рассмотрите другие курорты в этой стране")
        
        return suggestions

    async def _execute_tour_search(self, search_request: SpecificTourSearchRequest) -> Optional[Dict[str, Any]]:
        """Выполнение точного поиска тура"""
        try:
            logger.info(f"🚀 EXECUTE_TOUR_SEARCH: Начинаем поиск")
            
            # Строим параметры для TourVisor API
            search_params = self._build_search_params(search_request)
            
            # Если указано название отеля, найдем его ID
            if search_request.hotel_name and not search_request.hotel_id:
                logger.info(f"🔍 Ищем ID отеля '{search_request.hotel_name}'")
                
                hotel_id = await self._find_hotel_id_by_name(
                    search_request.hotel_name, 
                    search_request.country
                )
                
                if hotel_id:
                    search_params["hotels"] = hotel_id
                    logger.info(f"🏨 ✅ Найден ID отеля: {hotel_id}")
                else:
                    logger.warning(f"🏨 ❌ Отель '{search_request.hotel_name}' НЕ НАЙДЕН!")
                    return None
            
            # Запускаем поиск туров
            logger.info(f"🚀 Запускаем поиск туров в TourVisor...")
            request_id = await tourvisor_client.search_tours(search_params)
            
            # Ждем результатов (максимум 15 секунд)
            logger.info(f"⏳ Ждем результатов поиска...")
            for attempt in range(15):
                await asyncio.sleep(1)
                
                try:
                    status = await tourvisor_client.get_search_status(request_id)
                    status_data = status.get("data", {}).get("status", {})
                    
                    state = status_data.get("state", "searching")
                    hotels_found = int(status_data.get("hotelsfound", 0)) if status_data.get("hotelsfound") else 0
                    
                    logger.info(f"⏳ Попытка {attempt+1}: state={state}, hotels={hotels_found}")
                    
                    # Прерываем если есть результаты или поиск завершен
                    if state == "finished" or (hotels_found > 0 and attempt >= 3):
                        logger.info(f"🎯 Поиск завершен: state={state}, hotels={hotels_found}")
                        break
                        
                except Exception as status_error:
                    logger.warning(f"⚠️ Ошибка получения статуса на попытке {attempt+1}: {status_error}")
                    continue
            
            # Получаем результаты
            logger.info(f"📥 Получаем результаты поиска...")
            results = await tourvisor_client.get_search_results(request_id, 1, 10)
            
            # Извлекаем лучший отель с турами
            hotel_with_tours = await self._extract_hotel_with_all_tours(results, search_request)
            
            if hotel_with_tours:
                hotel_name = hotel_with_tours.get('hotel_info', {}).get('hotel_name', 'Unknown')
                tours_count = len(hotel_with_tours.get('tours', []))
                logger.info(f"✅ Успех! Отель: {hotel_name}, туров: {tours_count}")
                return hotel_with_tours
            else:
                logger.warning(f"❌ Не удалось извлечь отель с турами")
                return None
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в _execute_tour_search: {e}")
            return None

    async def _execute_fallback_search(self, search_request: SpecificTourSearchRequest) -> Optional[Dict[str, Any]]:
        """Выполнение fallback поиска с расширенными параметрами"""
        try:
            logger.info("🔍 Выполняется fallback поиск")
            
            # Создаем копию запроса для fallback
            fallback_request = SpecificTourSearchRequest(**search_request.dict())
            
            # Убираем ограничения для более широкого поиска
            fallback_strategies = [
                {"remove": ["meal_type"], "description": "без ограничений по питанию"},
                {"remove": ["hotel_stars"], "description": "без ограничений по звездности"},
                {"remove": ["nights"], "description": "без ограничений по количеству ночей"},
                {"modify": {"max_price": None}, "description": "без ограничений по цене"},
            ]
            
            for strategy in fallback_strategies:
                # Применяем стратегию
                if "remove" in strategy:
                    for field in strategy["remove"]:
                        setattr(fallback_request, field, None)
                
                if "modify" in strategy:
                    for field, value in strategy["modify"].items():
                        setattr(fallback_request, field, value)
                
                logger.info(f"🔄 Пробуем fallback стратегию: {strategy['description']}")
                
                # Выполняем поиск с измененными параметрами
                result = await self._execute_tour_search(fallback_request)
                
                if result:
                    result["is_fallback"] = True
                    result["fallback_strategy"] = strategy["description"]
                    logger.info(f"✅ Fallback успешен: {strategy['description']}")
                    return result
            
            logger.warning("❌ Все fallback стратегии не дали результатов")
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка fallback поиска: {e}")
            return None
    
    async def _extract_hotel_with_all_tours(self, results: Dict[str, Any], 
                                          search_request: SpecificTourSearchRequest) -> Optional[Dict[str, Any]]:
        """Извлечение отеля со всеми турами из результатов поиска"""
        try:
            data = results.get("data", {})
            result_data = data.get("result", {})
            hotel_list = result_data.get("hotel", [])
            
            if not isinstance(hotel_list, list):
                hotel_list = [hotel_list] if hotel_list else []
            
            if not hotel_list:
                logger.warning("❌ Отели не найдены в результатах поиска")
                return None
            
            logger.info(f"🏨 Найдено отелей: {len(hotel_list)}")
            
            # Выбираем лучший отель по релевантности
            best_hotel = self._select_best_hotel(hotel_list, search_request)
            
            if not best_hotel:
                logger.warning("❌ Не удалось выбрать лучший отель")
                return None
            
            # Собираем все туры для этого отеля
            tours_data = best_hotel.get("tours", {}).get("tour", [])
            
            if not isinstance(tours_data, list):
                tours_data = [tours_data] if tours_data else []
            
            logger.info(f"🎫 Найдено туров для отеля: {len(tours_data)}")
            
            # Получаем информацию об отеле
            hotel_info = self._create_hotel_info(best_hotel)
            
            # Создаем список всех туров
            all_tours = []
            for tour_data in tours_data:
                tour_info = self._create_tour_info(best_hotel, tour_data)
                all_tours.append(tour_info)
            
            # Сортируем туры по цене
            all_tours.sort(key=lambda x: x.get("price", 0))
            
            return {
                "hotel_info": hotel_info,
                "tours": all_tours,
                "tours_count": len(all_tours),
                "search_results_count": len(hotel_list),
                "is_fallback": False,
                "fallback_strategy": None
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения отеля с турами: {e}")
            return None
    
    def _select_best_hotel(self, hotel_list: List[Dict], search_request: SpecificTourSearchRequest) -> Optional[Dict]:
        """Выбор лучшего отеля из списка по релевантности"""
        if not hotel_list:
            return None
        
        # Если указан конкретный отель по ID или имени, ищем его
        if search_request.hotel_id:
            for hotel in hotel_list:
                if str(hotel.get("hotelcode")) == str(search_request.hotel_id):
                    return hotel
        
        if search_request.hotel_name:
            search_name = search_request.hotel_name.lower()
            for hotel in hotel_list:
                hotel_name = hotel.get("hotelname", "").lower()
                if search_name in hotel_name:
                    return hotel
        
        # Иначе сортируем по релевантности и берем первый
        scored_hotels = []
        for hotel in hotel_list:
            score = self._calculate_hotel_score(hotel, search_request)
            scored_hotels.append((score, hotel))
        
        scored_hotels.sort(key=lambda x: x[0], reverse=True)
        return scored_hotels[0][1] if scored_hotels else None
    
    def _calculate_hotel_score(self, hotel: Dict, search_request: SpecificTourSearchRequest) -> float:
        """Расчет релевантности отеля"""
        score = 0.0
        
        # Звездность отеля
        if search_request.hotel_stars:
            hotel_stars = int(hotel.get("hotelstars", 0))
            if hotel_stars == search_request.hotel_stars:
                score += 10
            elif abs(hotel_stars - search_request.hotel_stars) == 1:
                score += 5
        
        # Рейтинг отеля
        hotel_rating = float(hotel.get("hotelrating", 0))
        if hotel_rating > 0:
            score += hotel_rating * 2
        
        # Расстояние до моря (чем меньше, тем лучше)
        sea_distance = int(hotel.get("seadistance", 1000))
        if sea_distance <= 100:
            score += 5
        elif sea_distance <= 300:
            score += 3
        elif sea_distance <= 500:
            score += 1
        
        return score
    
    def _create_hotel_info(self, hotel_data: Dict) -> Dict[str, Any]:
        """Создание базовой информации об отеле"""
        return {
            "hotel_id": self._safe_string(hotel_data.get("hotelcode")),
            "hotel_name": self._safe_string(hotel_data.get("hotelname", "")),
            "hotel_stars": self._safe_int(hotel_data.get("hotelstars")) or 3,
            "hotel_rating": self._safe_float(hotel_data.get("hotelrating")),
            "hotel_description": self._safe_string(hotel_data.get("hoteldescription")),
            "hotel_picture": self._safe_string(hotel_data.get("picturelink")),
            "country_name": self._safe_string(hotel_data.get("countryname", "")),
            "region_name": self._safe_string(hotel_data.get("regionname", "")),
            "sea_distance": self._safe_int(hotel_data.get("seadistance")) or 0,
        }
    
    def _create_tour_info(self, hotel_data: Dict, tour_data: Dict) -> Dict[str, Any]:
        """Создание информации о туре"""
        return {
            "tour_id": self._safe_string(tour_data.get("tourid")),
            "operator_name": self._safe_string(tour_data.get("operatorname", "")),
            "fly_date": self._safe_string(tour_data.get("flydate")),
            "nights": self._safe_int(tour_data.get("nights")) or 7,
            "price": self._safe_int(tour_data.get("price")) or 0,
            "fuel_charge": self._safe_int(tour_data.get("fuelcharge")) or 0,
            "meal": self._safe_string(tour_data.get("meal", "")),
            "room_type": self._safe_string(tour_data.get("room", "")),
            "adults": self._safe_int(tour_data.get("adults")) or 2,
            "children": self._safe_int(tour_data.get("child")) or 0,
            "tour_link": self._safe_string(tour_data.get("tourlink")),
            "currency": self._safe_string(tour_data.get("currency", "RUB")),
            "is_regular": bool(tour_data.get("regular", 0)),
            "is_promo": bool(tour_data.get("promo", 0)),
            "is_on_request": bool(tour_data.get("onrequest", 0)),
        }

    def _build_search_params(self, search_request: SpecificTourSearchRequest) -> Dict[str, Any]:
        """Построение параметров поиска для TourVisor API"""
        
        # Базовые обязательные параметры
        params = {
            "departure": search_request.departure,
            "country": search_request.country,
            "adults": search_request.adults,
            "child": search_request.children,
            "format": "json"
        }
        
        # Даты (если не указаны, берем ближайшие дни)
        if search_request.date_from:
            params["datefrom"] = search_request.date_from
        else:
            start_date = datetime.now() + timedelta(days=3)
            params["datefrom"] = start_date.strftime("%d.%m.%Y")
        
        if search_request.date_to:
            params["dateto"] = search_request.date_to
        else:
            end_date = datetime.now() + timedelta(days=17)
            params["dateto"] = end_date.strftime("%d.%m.%Y")
        
        # Количество ночей
        if search_request.nights:
            params["nightsfrom"] = search_request.nights
            params["nightsto"] = search_request.nights
        else:
            params["nightsfrom"] = 7
            params["nightsto"] = 10
        
        # Опциональные параметры
        if search_request.hotel_stars:
            params["stars"] = search_request.hotel_stars
            params["starsbetter"] = 1
        
        if search_request.meal_type:
            params["meal"] = search_request.meal_type
            params["mealbetter"] = 1
        
        if search_request.region_code:
            params["regions"] = search_request.region_code
        
        if search_request.min_price:
            params["pricefrom"] = search_request.min_price
        
        if search_request.max_price:
            params["priceto"] = search_request.max_price
        
        if search_request.rating:
            # Преобразуем рейтинг в код TourVisor
            if search_request.rating >= 4.5:
                params["rating"] = 5
            elif search_request.rating >= 4.0:
                params["rating"] = 4
            elif search_request.rating >= 3.5:
                params["rating"] = 3
            elif search_request.rating >= 3.0:
                params["rating"] = 2
            else:
                params["rating"] = 0
        
        if search_request.hotel_type:
            params["hoteltypes"] = search_request.hotel_type
        
        # Дополнительные параметры для стабильности
        params["pricetype"] = 0  # Цена за номер
        
        return params

    async def _find_hotel_id_by_name(self, hotel_name: str, country_code: int) -> Optional[str]:
        """Поиск ID отеля по названию"""
        try:
            logger.info(f"🔍 Поиск отеля '{hotel_name}' в стране {country_code}")
            
            # Получаем список отелей для страны
            hotels_data = await tourvisor_client.get_references(
                "hotel",
                hotcountry=country_code
            )
            
            # Извлекаем отели из структуры данных
            hotels = []
            if "lists" in hotels_data and "hotels" in hotels_data["lists"]:
                hotels_nested = hotels_data["lists"]["hotels"].get("hotel", [])
                if isinstance(hotels_nested, list):
                    hotels = hotels_nested
                elif hotels_nested:
                    hotels = [hotels_nested]
            elif "hotel" in hotels_data:
                hotels_direct = hotels_data.get("hotel", [])
                if isinstance(hotels_direct, list):
                    hotels = hotels_direct
                elif hotels_direct:
                    hotels = [hotels_direct]
            
            logger.info(f"📊 Найдено {len(hotels)} отелей в стране {country_code}")
            
            if not hotels:
                logger.warning(f"❌ Нет отелей для страны {country_code}!")
                return None
            
            # Ищем отель по имени
            search_name = hotel_name.lower().strip()
            
            # Сначала точное совпадение
            for hotel in hotels:
                hotel_name_full = hotel.get("name", "").lower().strip()
                if search_name == hotel_name_full:
                    logger.info(f"✅ Точное совпадение: {hotel.get('name')} (ID: {hotel.get('id')})")
                    return hotel.get("id")
            
            # Затем частичное совпадение
            for hotel in hotels:
                hotel_name_full = hotel.get("name", "").lower().strip()
                if search_name in hotel_name_full:
                    logger.info(f"✅ Частичное совпадение: {hotel.get('name')} (ID: {hotel.get('id')})")
                    return hotel.get("id")
            
            # Обратное совпадение
            for hotel in hotels:
                hotel_name_full = hotel.get("name", "").lower().strip()
                if hotel_name_full in search_name:
                    logger.info(f"✅ Обратное совпадение: {hotel.get('name')} (ID: {hotel.get('id')})")
                    return hotel.get("id")
            
            logger.warning(f"❌ Отель '{hotel_name}' не найден среди {len(hotels)} отелей")
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска отеля: {e}")
            return None

    def _safe_string(self, value: Any) -> str:
        """Безопасное преобразование в строку"""
        try:
            if value is None:
                return ""
            elif isinstance(value, (dict, list, tuple)):
                return ""
            else:
                return str(value).strip()
        except (ValueError, TypeError):
            return ""

    def _safe_int(self, value: Any) -> Optional[int]:
        """Безопасное преобразование в int"""
        try:
            return int(value) if value is not None and str(value).strip() else None
        except (ValueError, TypeError):
            return None
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """Безопасное преобразование в float"""
        try:
            return float(value) if value is not None and str(value).strip() else None
        except (ValueError, TypeError):
            return None

# Создаем экземпляр сервиса
specific_tour_service = SpecificTourService()