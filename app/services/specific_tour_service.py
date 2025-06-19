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
        
        # Маппинг типов питания (код -> название)
        self.meal_types = {
            1: "Без питания",
            2: "Завтрак", 
            3: "Полупансион",
            4: "Полный пансион",
            5: "Всё включено",
            6: "Ultra All Inclusive",
            7: "All Inclusive"
        }
    
    async def find_specific_tour(self, search_request: SpecificTourSearchRequest) -> FoundTourInfo:
        """Поиск конкретного тура по критериям"""
        try:
            logger.info(f"🔎 Поиск тура: страна {search_request.country}, вылет {search_request.departure}")
            
            # Генерируем ключ кэша
            cache_key = self._generate_cache_key(search_request)
            
            # Проверяем кэш
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                logger.info("✅ Найден результат в кэше")
                return FoundTourInfo(**cached_result)
            
            # Выполняем поиск
            found_tour = await self._execute_tour_search(search_request)
            
            if not found_tour:
                # Пробуем расширенный поиск
                logger.info("🔍 Основной поиск не дал результатов, пробуем fallback")
                found_tour = await self._execute_fallback_search(search_request)
            
            if found_tour:
                # Кэшируем результат на 30 минут
                await self.cache.set(cache_key, found_tour, ttl=1800)
                logger.info(f"✅ Найден тур: {found_tour['hotel_name']} - {found_tour['price']} руб.")
                return FoundTourInfo(**found_tour)
            else:
                raise ValueError("Тур не найден по заданным критериям")
                
        except Exception as e:
            logger.error(f"❌ Ошибка поиска конкретного тура: {e}")
            raise
    
    async def find_tour_by_hotel_name(self, hotel_name: str, departure: int, country: int, 
                                    nights: int = 7, adults: int = 2, children: int = 0) -> FoundTourInfo:
        """Упрощенный поиск тура по названию отеля"""
        search_request = SpecificTourSearchRequest(
            departure=departure,
            country=country,
            hotel_name=hotel_name,
            nights=nights,
            adults=adults,
            children=children
        )
        return await self.find_specific_tour(search_request)
    
    async def find_tour_by_criteria(self, departure: int, country: int, hotel_stars: int,
                                  meal_type: int, max_price: Optional[int] = None,
                                  nights: int = 7, adults: int = 2) -> FoundTourInfo:
        """Поиск тура по основным критериям"""
        search_request = SpecificTourSearchRequest(
            departure=departure,
            country=country,
            hotel_stars=hotel_stars,
            meal_type=meal_type,
            max_price=max_price,
            nights=nights,
            adults=adults
        )
        return await self.find_specific_tour(search_request)
    
    async def _execute_tour_search(self, search_request: SpecificTourSearchRequest) -> Optional[Dict[str, Any]]:
        """Выполнение точного поиска тура"""
        try:
            # Строим параметры для TourVisor API
            search_params = await self._build_search_params(search_request)
            
            # Если указано название отеля, найдем его ID
            if search_request.hotel_name and not search_request.hotel_id:
                hotel_id = await self._find_hotel_id_by_name(
                    search_request.hotel_name, 
                    search_request.country
                )
                if hotel_id:
                    search_params["hotels"] = hotel_id
                    logger.info(f"🏨 Найден ID отеля '{search_request.hotel_name}': {hotel_id}")
                else:
                    logger.warning(f"🏨 Отель '{search_request.hotel_name}' не найден")
                    return None
            
            # Запускаем поиск
            request_id = await tourvisor_client.search_tours(search_params)
            
            # Ждем результатов (максимум 12 секунд)
            for attempt in range(12):
                await asyncio.sleep(1)
                
                status = await tourvisor_client.get_search_status(request_id)
                status_data = status.get("data", {}).get("status", {})
                
                state = status_data.get("state", "searching")
                hotels_found = int(status_data.get("hotelsfound", 0)) if status_data.get("hotelsfound") else 0
                
                # Прерываем если есть результаты или поиск завершен
                if state == "finished" or (hotels_found > 0 and attempt >= 3):
                    break
            
            # Получаем результаты
            results = await tourvisor_client.get_search_results(request_id, 1, 10)
            
            # Извлекаем лучший тур
            tour = await self._extract_best_tour(results, search_request)
            return tour
            
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения поиска: {e}")
            return None
    
    async def _execute_fallback_search(self, original_request: SpecificTourSearchRequest) -> Optional[Dict[str, Any]]:
        """Fallback поиск с ослабленными критериями"""
        logger.info("🔄 Выполняем fallback поиск")
        
        fallback_strategies = [
            self._strategy_expand_nights,
            self._strategy_remove_stars,
            self._strategy_expand_price,
            self._strategy_remove_hotel_type,
            self._strategy_expand_dates,
        ]
        
        for i, strategy in enumerate(fallback_strategies):
            try:
                logger.info(f"🔄 Fallback стратегия {i+1}")
                
                modified_request = strategy(original_request)
                if modified_request:
                    tour = await self._execute_tour_search(modified_request)
                    if tour:
                        logger.info(f"✅ Fallback стратегия {i+1} успешна")
                        tour["is_fallback"] = True
                        tour["fallback_strategy"] = i + 1
                        return tour
                
            except Exception as e:
                logger.debug(f"Fallback стратегия {i+1} не сработала: {e}")
                continue
        
        return None
    
    def _strategy_expand_nights(self, request: SpecificTourSearchRequest) -> SpecificTourSearchRequest:
        """Стратегия: расширение количества ночей"""
        new_request = request.copy()
        if request.nights:
            # Расширяем диапазон ±3 ночи
            new_request.nights = None  # Убираем точное указание
        return new_request
    
    def _strategy_remove_stars(self, request: SpecificTourSearchRequest) -> SpecificTourSearchRequest:
        """Стратегия: убираем фильтр по звездности"""
        new_request = request.copy()
        new_request.hotel_stars = None
        return new_request
    
    def _strategy_expand_price(self, request: SpecificTourSearchRequest) -> SpecificTourSearchRequest:
        """Стратегия: расширение ценового диапазона"""
        new_request = request.copy()
        if request.max_price:
            new_request.max_price = int(request.max_price * 1.5)
        new_request.min_price = None
        return new_request
    
    def _strategy_remove_hotel_type(self, request: SpecificTourSearchRequest) -> SpecificTourSearchRequest:
        """Стратегия: убираем фильтр по типу отеля"""
        new_request = request.copy()
        new_request.hotel_type = None
        return new_request
    
    def _strategy_expand_dates(self, request: SpecificTourSearchRequest) -> SpecificTourSearchRequest:
        """Стратегия: расширение диапазона дат"""
        new_request = request.copy()
        # Расширяем диапазон на ±7 дней
        try:
            if request.date_from:
                date_from = datetime.strptime(request.date_from, "%d.%m.%Y")
                new_date_from = date_from - timedelta(days=7)
                new_request.date_from = new_date_from.strftime("%d.%m.%Y")
            
            if request.date_to:
                date_to = datetime.strptime(request.date_to, "%d.%m.%Y")
                new_date_to = date_to + timedelta(days=7)
                new_request.date_to = new_date_to.strftime("%d.%m.%Y")
        except:
            pass
        
        return new_request
    
    async def _build_search_params(self, request: SpecificTourSearchRequest) -> Dict[str, Any]:
        """Построение параметров поиска для TourVisor API"""
        params = {
            "departure": request.departure,
            "country": request.country,
            "adults": request.adults,
            "child": request.children,
            "format": "xml",
            "pricetype": 0,  # Цена за номер
        }
        
        # Даты
        if request.date_from:
            params["datefrom"] = request.date_from
        else:
            start_date = datetime.now() + timedelta(days=7)
            params["datefrom"] = start_date.strftime("%d.%m.%Y")
        
        if request.date_to:
            params["dateto"] = request.date_to
        else:
            end_date = datetime.now() + timedelta(days=21)
            params["dateto"] = end_date.strftime("%d.%m.%Y")
        
        # Ночи
        if request.nights:
            params["nightsfrom"] = request.nights
            params["nightsto"] = request.nights
        else:
            params["nightsfrom"] = 7
            params["nightsto"] = 10
        
        # Фильтры отеля
        if request.hotel_id:
            params["hotels"] = request.hotel_id
        
        if request.hotel_stars:
            params["stars"] = request.hotel_stars
            params["starsbetter"] = 1
        
        if request.region_code:
            params["regions"] = str(request.region_code)
        
        if request.rating:
            # Конвертируем рейтинг в формат TourVisor
            if request.rating >= 4.5:
                params["rating"] = 5
            elif request.rating >= 4.0:
                params["rating"] = 4
            elif request.rating >= 3.5:
                params["rating"] = 3
            elif request.rating >= 3.0:
                params["rating"] = 2
        
        if request.hotel_type:
            params["hoteltypes"] = request.hotel_type
        
        # Фильтры питания
        if request.meal_type:
            params["meal"] = request.meal_type
            params["mealbetter"] = 1
        
        # Фильтры цены
        if request.min_price:
            params["pricefrom"] = request.min_price
        if request.max_price:
            params["priceto"] = request.max_price
        
        return params
    
    async def _find_hotel_id_by_name(self, hotel_name: str, country_code: int) -> Optional[str]:
        """Поиск ID отеля по названию"""
        try:
            # Проверяем кэш
            cache_key = f"hotel_search_{hotel_name.lower()}_{country_code}"
            cached_id = await self.cache.get(cache_key)
            if cached_id:
                return cached_id
            
            # Ищем в справочнике отелей
            hotels_data = await tourvisor_client.get_references(
                "hotel",
                hotcountry=country_code
            )
            
            hotels = hotels_data.get("hotel", [])
            if not isinstance(hotels, list):
                hotels = [hotels] if hotels else []
            
            # Ищем отель по названию (нечеткий поиск)
            hotel_name_lower = hotel_name.lower()
            
            best_match = None
            best_score = 0
            
            for hotel in hotels:
                hotel_api_name = hotel.get("name", "").lower()
                
                # Точное совпадение
                if hotel_name_lower == hotel_api_name:
                    hotel_id = hotel.get("id")
                    await self.cache.set(cache_key, hotel_id, ttl=86400)  # Кэш на сутки
                    return hotel_id
                
                # Частичное совпадение
                if hotel_name_lower in hotel_api_name:
                    score = len(hotel_name_lower) / len(hotel_api_name)
                    if score > best_score:
                        best_score = score
                        best_match = hotel.get("id")
                elif hotel_api_name in hotel_name_lower:
                    score = len(hotel_api_name) / len(hotel_name_lower)
                    if score > best_score:
                        best_score = score
                        best_match = hotel.get("id")
            
            if best_match and best_score > 0.3:  # Минимальный порог совпадения
                await self.cache.set(cache_key, best_match, ttl=86400)
                return best_match
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска ID отеля: {e}")
            return None
    
    async def _extract_best_tour(self, results: Dict[str, Any], 
                               search_request: SpecificTourSearchRequest) -> Optional[Dict[str, Any]]:
        """Извлечение лучшего тура из результатов поиска"""
        try:
            data = results.get("data", {})
            result_data = data.get("result", {})
            hotel_list = result_data.get("hotel", [])
            
            if not isinstance(hotel_list, list):
                hotel_list = [hotel_list] if hotel_list else []
            
            if not hotel_list:
                return None
            
            # Собираем все туры
            all_tours = []
            
            for hotel in hotel_list:
                tours_data = hotel.get("tours", {}).get("tour", [])
                
                if not isinstance(tours_data, list):
                    tours_data = [tours_data] if tours_data else []
                
                for tour_data in tours_data:
                    combined_tour = self._create_tour_info(hotel, tour_data)
                    all_tours.append(combined_tour)
            
            if not all_tours:
                return None
            
            # Сортируем туры по релевантности
            sorted_tours = self._sort_tours_by_relevance(all_tours, search_request)
            
            # Возвращаем лучший тур
            best_tour = sorted_tours[0]
            best_tour["search_results_count"] = len(all_tours)
            best_tour["hotels_found"] = len(hotel_list)
            
            return best_tour
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения тура: {e}")
            return None
    
    def _create_tour_info(self, hotel_data: Dict, tour_data: Dict) -> Dict[str, Any]:
        """Создание объединенной информации о туре"""
        return {
            # Информация об отеле
            "hotel_id": hotel_data.get("hotelcode"),
            "hotel_name": hotel_data.get("hotelname", ""),
            "hotel_stars": int(hotel_data.get("hotelstars", 3)),
            "hotel_rating": float(hotel_data.get("hotelrating", 0)) if hotel_data.get("hotelrating") else None,
            "hotel_description": hotel_data.get("hoteldescription"),
            "hotel_picture": hotel_data.get("picturelink"),
            "hotel_review_link": hotel_data.get("reviewlink"),
            "country_name": hotel_data.get("countryname", ""),
            "region_name": hotel_data.get("regionname", ""),
            "sea_distance": int(hotel_data.get("seadistance", 0)) if hotel_data.get("seadistance") else None,
            
            # Информация о туре
            "tour_id": tour_data.get("tourid"),
            "operator_name": tour_data.get("operatorname", ""),
            "fly_date": tour_data.get("flydate", ""),
            "nights": int(tour_data.get("nights", 7)),
            "price": float(tour_data.get("price", 0)),
            "fuel_charge": float(tour_data.get("fuelcharge", 0)) if tour_data.get("fuelcharge") else None,
            "meal": tour_data.get("mealrussian", tour_data.get("meal", "")),
            "room_type": tour_data.get("room", ""),
            "adults": int(tour_data.get("adults", 2)),
            "children": int(tour_data.get("child", 0)),
            "currency": tour_data.get("currency", "RUB"),
            "tour_link": tour_data.get("tourlink"),
            
            # Дополнительная информация
            "is_regular": tour_data.get("regular") == 1,
            "is_promo": tour_data.get("promo") == 1,
            "is_on_request": tour_data.get("onrequest") == 1,
            "flight_status": tour_data.get("flightstatus"),
            "hotel_status": tour_data.get("hotelstatus"),
        }
    
    def _sort_tours_by_relevance(self, tours: List[Dict[str, Any]], 
                                search_request: SpecificTourSearchRequest) -> List[Dict[str, Any]]:
        """Сортировка туров по релевантности"""
        
        def calculate_score(tour: Dict[str, Any]) -> float:
            score = 0.0
            
            # Очки за звездность
            if search_request.hotel_stars and tour.get("hotel_stars"):
                if tour["hotel_stars"] == search_request.hotel_stars:
                    score += 100
                elif tour["hotel_stars"] > search_request.hotel_stars:
                    score += 80
                else:
                    score += max(0, 50 - (search_request.hotel_stars - tour["hotel_stars"]) * 10)
            
            # Очки за количество ночей
            if search_request.nights and tour.get("nights"):
                if tour["nights"] == search_request.nights:
                    score += 80
                else:
                    score += max(0, 40 - abs(tour["nights"] - search_request.nights) * 5)
            
            # Очки за рейтинг отеля
            if tour.get("hotel_rating"):
                score += tour["hotel_rating"] * 10
            
            # Очки за цену (предпочитаем разумные цены)
            if tour.get("price"):
                price = tour["price"]
                if 30000 <= price <= 150000:
                    score += 30
                elif price < 30000:
                    score += 20
                else:
                    score += max(0, 30 - (price - 150000) / 10000)
            
            # Очки за статус
            if not tour.get("is_on_request", False):
                score += 20
            
            # Очки за наличие фото
            if tour.get("hotel_picture"):
                score += 10
            
            # Штраф за регулярные рейсы
            if tour.get("is_regular", False):
                score -= 10
            
            return score
        
        tours_with_scores = [(tour, calculate_score(tour)) for tour in tours]
        tours_with_scores.sort(key=lambda x: x[1], reverse=True)
        
        return [tour for tour, score in tours_with_scores]
    
    def _generate_cache_key(self, search_request: SpecificTourSearchRequest) -> str:
        """Генерация ключа кэша"""
        import hashlib
        import json
        
        # Создаем хэш из параметров запроса
        request_dict = search_request.dict(exclude_none=True)
        sorted_params = json.dumps(request_dict, sort_keys=True, default=str)
        params_hash = hashlib.md5(sorted_params.encode()).hexdigest()
        
        return f"specific_tour:{params_hash}"
    
    def get_search_suggestions(self, search_request: SpecificTourSearchRequest) -> List[str]:
        """Получение предложений для улучшения поиска"""
        suggestions = []
        
        if search_request.hotel_stars:
            suggestions.append(f"Попробуйте отели {search_request.hotel_stars-1}* или без фильтра по звездности")
        
        if search_request.max_price:
            suggested_price = int(search_request.max_price * 1.3)
            suggestions.append(f"Увеличьте максимальную цену до {suggested_price:,} руб.")
        
        if search_request.nights:
            nights = search_request.nights
            suggestions.append(f"Попробуйте {nights-2}-{nights+2} ночей вместо точно {nights}")
        
        if search_request.hotel_name:
            suggestions.append("Попробуйте поиск без указания конкретного отеля")
        
        suggestions.extend([
            "Измените даты поездки на ±7 дней",
            "Выберите другой город вылета",
            "Попробуйте соседние курорты"
        ])
        
        return suggestions[:5]

# Создаем экземпляр сервиса
specific_tour_service = SpecificTourService()