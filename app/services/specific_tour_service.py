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
            
            # ИСПРАВЛЕНИЕ: Правильное извлечение данных из словарей
            # Создаем объект FoundTourInfo с обязательными полями
            found_tour_info = FoundTourInfo(
                # Информация об отеле - ОБЯЗАТЕЛЬНЫЕ ПОЛЯ (из hotel_info словаря)
                hotel_name=hotel_info.get('hotel_name') or 'Неизвестный отель',
                hotel_stars=hotel_info.get('hotel_stars') or 0,
                country_name=hotel_info.get('country_name') or '',
                region_name=hotel_info.get('region_name') or '',
                
                # Информация о туре - ОБЯЗАТЕЛЬНЫЕ ПОЛЯ (из best_tour словаря)
                operator_name=best_tour.get('operator_name') or 'Неизвестный оператор',
                fly_date=best_tour.get('fly_date') or '',
                nights=best_tour.get('nights') or search_request.nights or 7,
                price=float(best_tour.get('price', 0)) or 0.0,
                meal=best_tour.get('meal') or '',
                room_type=best_tour.get('room_type') or '',
                adults=best_tour.get('adults') or search_request.adults,
                children=best_tour.get('children') or search_request.children,
                currency=best_tour.get('currency') or 'RUB',
                
                # Опциональные поля отеля
                hotel_id=hotel_info.get('hotel_id'),
                hotel_rating=hotel_info.get('hotel_rating'),
                hotel_description=hotel_info.get('description') or hotel_info.get('hotel_description'),
                hotel_picture=hotel_info.get('picture_link') or hotel_info.get('hotel_picture') or hotel_info.get('main_photo'),
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
            logger.error(f"🔍 Отладка: hotel_info keys = {list(hotel_info.keys()) if 'hotel_info' in locals() else 'hotel_info не создан'}")
            logger.error(f"🔍 Отладка: best_tour keys = {list(best_tour.keys()) if 'best_tour' in locals() else 'best_tour не создан'}")
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

    # Замените метод _execute_tour_search в app/services/specific_tour_service.py

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
            
            # Если указан ID отеля напрямую
            elif search_request.hotel_id:
                search_params["hotels"] = search_request.hotel_id
                logger.info(f"🏨 Используем указанный ID отеля: {search_request.hotel_id}")
            
            # Выполняем поиск через TourVisor
            logger.info(f"🔍 Запускаем поиск с параметрами: {search_params}")
            request_id = await tourvisor_client.search_tours(search_params)
            
            if not request_id:
                logger.error(f"❌ Не получен request_id от TourVisor")
                return None
            
            logger.info(f"📋 Получен request_id: {request_id}")
            
            # Ждем завершения поиска (используем существующую логику)
            logger.info(f"⏳ Ждем завершения поиска...")
            max_wait_time = 45  # Увеличиваем до 45 секунд
            start_wait = datetime.now()
            
            final_results = None
            
            while (datetime.now() - start_wait).total_seconds() < max_wait_time:
                try:
                    status_result = await tourvisor_client.get_search_status(request_id)
                    
                    if status_result:
                        status_data = status_result.get("data", {}).get("status", {})
                        state = status_data.get("state", "")
                        hotels_found = status_data.get("hotelsfound", 0)
                        
                        # Безопасное преобразование в int
                        try:
                            hotels_found = int(hotels_found) if hotels_found else 0
                        except (ValueError, TypeError):
                            hotels_found = 0
                        
                        logger.info(f"⏳ Статус: {state}, отелей найдено: {hotels_found}")
                        
                        if state == "finished":
                            if hotels_found > 0:
                                # Получаем результаты
                                final_results = await tourvisor_client.get_search_results(request_id)
                                logger.info(f"✅ Получены результаты поиска")
                                break
                            else:
                                logger.warning(f"⚠️ Поиск завершен, но отелей не найдено")
                                break
                        elif state == "error":
                            logger.error(f"❌ Ошибка поиска в TourVisor")
                            break
                        elif hotels_found > 50:  # Теперь это безопасно
                            logger.info(f"🎯 Найдено достаточно отелей ({hotels_found}), получаем результаты")
                            try:
                                final_results = await tourvisor_client.get_search_results(request_id)
                                if final_results and final_results.get("data", {}).get("result"):
                                    logger.info(f"✅ Получены промежуточные результаты с {hotels_found} отелями")
                                    break
                                else:
                                    logger.warning(f"⚠️ Результаты пока пустые, продолжаем ждать...")
                            except Exception as e:
                                logger.warning(f"⚠️ Ошибка получения промежуточных результатов: {e}")
                                # Продолжаем ждать
                    
                    await asyncio.sleep(3)  # Увеличиваем интервал до 3 секунд
                    
                except Exception as status_error:
                    logger.warning(f"⚠️ Ошибка получения статуса: {status_error}")
                    await asyncio.sleep(2)
                    continue
            
            if not final_results:
                logger.error(f"❌ Не получены результаты поиска в отведенное время")
                return None
            
            # Обрабатываем результаты
            logger.info(f"🔄 Обрабатываем результаты поиска")
            return await self._process_search_results(final_results, search_request)
            
        except Exception as e:
            logger.error(f"❌ EXECUTE_TOUR_SEARCH: Ошибка выполнения поиска: {e}")
            return None
    async def _process_search_results(self, search_results: Dict[str, Any], search_request: SpecificTourSearchRequest) -> Optional[Dict[str, Any]]:
        """Обработка результатов поиска с обогащением информации об отеле"""
        try:
            logger.info(f"🔄 Начинаем обработку результатов поиска")
            
            # Извлекаем отели из результатов
            hotels_data = self._extract_hotels_from_results(search_results)
            
            if not hotels_data:
                logger.warning(f"❌ Отели не найдены в результатах поиска")
                return None
            
            logger.info(f"📊 Найдено {len(hotels_data)} отелей")
            
            # Выбираем лучший отель (по рейтингу и другим критериям)
            best_hotel = self._select_best_hotel(hotels_data, search_request)
            
            if not best_hotel:
                logger.warning(f"❌ Не удалось выбрать лучший отель")
                return None
            
            # ВАЖНО: Обогащаем информацию об отеле дополнительными данными
            logger.info(f"🏗️ Обогащаем информацию об отеле: {best_hotel.get('hotelname', 'Unknown')}")
            hotel_info = await self._build_hotel_info(best_hotel)
            
            # Извлекаем и обрабатываем туры
            tours_data = self._extract_tours_from_hotel(best_hotel)
            
            if not tours_data:
                logger.warning(f"❌ Туры не найдены для отеля {hotel_info.get('hotel_name', 'Unknown')}")
                return None
            
            # Сортируем туры по цене
            sorted_tours = sorted(tours_data, key=lambda t: t.get('price', float('inf')))
            
            # Создаем список туров
            tours_list = []
            for tour_data in sorted_tours:
                tour_info = self._create_tour_info(best_hotel, tour_data)
                tours_list.append(tour_info)
            
            logger.info(f"✅ Обработано {len(tours_list)} туров для отеля {hotel_info.get('hotel_name', 'Unknown')}")
            
            # Возвращаем полную информацию
            return {
                "hotel_info": hotel_info,  # ОБОГАЩЕННАЯ информация об отеле
                "tours": tours_list,
                "tours_count": len(tours_list),
                "search_results_count": len(hotels_data),
                "is_fallback": False,
                "fallback_strategy": None,
                "available_dates": self._extract_available_dates(tours_list),
                "meal_types": self._extract_meal_types(tours_list),
                "operators": self._extract_operators(tours_list),
                "price_range": self._calculate_price_range(tours_list)
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки результатов поиска: {e}")
            return None

    def _extract_available_dates(self, tours_list: List[Dict[str, Any]]) -> List[str]:
        """Извлечение доступных дат вылета"""
        try:
            dates = set()
            for tour in tours_list:
                fly_date = tour.get('fly_date')
                if fly_date:
                    dates.add(fly_date)
            return sorted(list(dates))
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения дат: {e}")
            return []

    def _extract_meal_types(self, tours_list: List[Dict[str, Any]]) -> List[str]:
        """Извлечение типов питания"""
        try:
            meals = set()
            for tour in tours_list:
                meal = tour.get('meal')
                if meal:
                    meals.add(meal)
            return sorted(list(meals))
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения типов питания: {e}")
            return []

    def _extract_operators(self, tours_list: List[Dict[str, Any]]) -> List[str]:
        """Извлечение туроператоров"""
        try:
            operators = set()
            for tour in tours_list:
                operator = tour.get('operator_name')
                if operator:
                    operators.add(operator)
            return sorted(list(operators))
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения операторов: {e}")
            return []

    def _calculate_price_range(self, tours_list: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
        """Расчет диапазона цен"""
        try:
            if not tours_list:
                return None
            
            prices = [tour.get('price', 0) for tour in tours_list if tour.get('price', 0) > 0]
            
            if not prices:
                return None
            
            return {
                "min_price": min(prices),
                "max_price": max(prices),
                "avg_price": sum(prices) / len(prices)
            }
        except Exception as e:
            logger.error(f"❌ Ошибка расчета диапазона цен: {e}")
            return None
    # Замените метод _execute_fallback_search в app/services/specific_tour_service.py

    async def _execute_fallback_search(self, search_request: SpecificTourSearchRequest) -> Optional[Dict[str, Any]]:
        """Резервный поиск с более мягкими критериями"""
        try:
            logger.info(f"🔄 FALLBACK_SEARCH: Начинаем резервный поиск")
            
            fallback_strategies = [
                "remove_hotel_filter",
                "increase_price_range", 
                "relax_dates",
                "lower_star_requirements",
                "change_meal_type",
                "expand_region"
            ]
            
            for strategy in fallback_strategies:
                logger.info(f"🔄 Пробуем стратегию: {strategy}")
                
                # Модифицируем параметры поиска
                fallback_params = self._modify_search_params_for_fallback(search_request, strategy)
                
                if not fallback_params:
                    continue
                    
                try:
                    # Выполняем поиск с модифицированными параметрами
                    search_result = await tourvisor_client.search_tours(fallback_params)
                    
                    if not search_result or not search_result.get('request_id'):
                        continue
                    
                    request_id = search_result['request_id']
                    logger.info(f"📋 Fallback request_id: {request_id}")
                    
                    # Ждем завершения поиска
                    final_results = await tourvisor_client.wait_for_search_completion(request_id)
                    
                    if final_results:
                        # Обрабатываем результаты с обогащением
                        processed_results = await self._process_search_results(final_results, search_request)
                        
                        if processed_results and processed_results.get('tours'):
                            logger.info(f"✅ Fallback успешен со стратегией: {strategy}")
                            
                            # Добавляем информацию о fallback
                            processed_results['is_fallback'] = True
                            processed_results['fallback_strategy'] = strategy
                            
                            return processed_results
                            
                except Exception as strategy_error:
                    logger.warning(f"⚠️ Ошибка стратегии {strategy}: {strategy_error}")
                    continue
            
            logger.warning(f"❌ Все fallback стратегии исчерпаны")
            return None
            
        except Exception as e:
            logger.error(f"❌ FALLBACK_SEARCH: Ошибка резервного поиска: {e}")
            return None
      
    def _modify_search_params_for_fallback(self, search_request: SpecificTourSearchRequest, strategy: str) -> Optional[Dict[str, Any]]:
        """Модификация параметров поиска для fallback стратегий"""
        try:
            logger.info(f"🔧 Модифицируем параметры для стратегии: {strategy}")
            
            # Базовые параметры
            params = {
                "departure": search_request.departure,
                "country": search_request.country,
                "adults": search_request.adults,
                "child": search_request.children,
                "format": "json"
            }
            
            # Даты (расширяем диапазон)
            if strategy == "relax_dates":
                start_date = datetime.now() + timedelta(days=1)
                end_date = datetime.now() + timedelta(days=45)
                params["datefrom"] = start_date.strftime("%d.%m.%Y")
                params["dateto"] = end_date.strftime("%d.%m.%Y")
                params["nightsfrom"] = max(1, (search_request.nights or 7) - 3)
                params["nightsto"] = min(30, (search_request.nights or 7) + 3)
            else:
                # Стандартные даты
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
                
                if search_request.nights:
                    params["nightsfrom"] = search_request.nights
                    params["nightsto"] = search_request.nights
            
            # Применяем стратегии модификации
            if strategy == "remove_hotel_filter":
                # Убираем фильтр по отелю, оставляем только основные критерии
                if search_request.hotel_stars:
                    params["stars"] = search_request.hotel_stars
                    params["starsbetter"] = 1
                
            elif strategy == "increase_price_range":
                # Увеличиваем максимальную цену в 1.5 раза
                if search_request.max_price:
                    params["priceto"] = int(search_request.max_price * 1.5)
                if search_request.min_price:
                    params["pricefrom"] = max(10000, int(search_request.min_price * 0.7))
                
            elif strategy == "lower_star_requirements":
                # Понижаем требования к звездности
                if search_request.hotel_stars and search_request.hotel_stars > 3:
                    params["stars"] = search_request.hotel_stars - 1
                    params["starsbetter"] = 1
                elif search_request.hotel_stars:
                    params["stars"] = max(1, search_request.hotel_stars - 1)
                    
            elif strategy == "change_meal_type":
                # Убираем фильтр по типу питания или делаем его менее строгим
                if search_request.meal_type and search_request.meal_type > 1:
                    params["meal"] = search_request.meal_type - 1
                    
            elif strategy == "expand_region":
                # Убираем фильтр по региону, ищем по всей стране
                pass  # Просто не добавляем regions
                
            else:
                # Базовый fallback - копируем все как есть, но убираем hotel_name
                if search_request.hotel_stars:
                    params["stars"] = search_request.hotel_stars
                    params["starsbetter"] = 1
                if search_request.meal_type:
                    params["meal"] = search_request.meal_type
                if search_request.region_code:
                    params["regions"] = search_request.region_code
                if search_request.max_price:
                    params["priceto"] = search_request.max_price
                if search_request.min_price:
                    params["pricefrom"] = search_request.min_price
            
            # Общие дополнительные параметры (если не переопределены стратегией)
            if "stars" not in params and search_request.hotel_stars:
                params["stars"] = search_request.hotel_stars
                params["starsbetter"] = 1
                
            if "meal" not in params and search_request.meal_type:
                params["meal"] = search_request.meal_type
                
            if "regions" not in params and search_request.region_code:
                params["regions"] = search_request.region_code
                
            if "priceto" not in params and search_request.max_price:
                params["priceto"] = search_request.max_price
                
            if "pricefrom" not in params and search_request.min_price:
                params["pricefrom"] = search_request.min_price
            
            logger.info(f"🔧 Параметры для {strategy}: {params}")
            return params
            
        except Exception as e:
            logger.error(f"❌ Ошибка модификации параметров для {strategy}: {e}")
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
    
    async def _build_hotel_info(self, hotel_data: Dict) -> Dict[str, Any]:
        """Построение полной информации об отеле с дополнительными данными
        
        Обрабатывает все поля согласно документации TourVisor XML API:
        - hotelcode – код отеля
        - price – цена в рублях (минимальная по этому отелю)
        - countrycode – код страны
        - countryname – название страны (на русском)
        - regioncode – код курорта для данного отеля
        - regionname – название курорта (на русском)
        - subregioncode – код вложенного курорта (района) для данного отеля, если есть
        - hotelname – название отеля
        - hotelstars – категория отеля (2,3,4 или 5)
        - hotelrating – рейтинг отеля от 1 до 5 (дробный), если нет = 0
        - hoteldescription – краткое описание отеля (если его нет, то пусто)
        - fulldesclink – ссылка на полное описание отеля
        - reviewlink – ссылка на отзывы по отелю
        - picturelink – ссылка на картинку отеля (ширина 130px)
        - isphoto – есть ли фотографии в описании отеля (1 / 0)
        - iscoords – есть ли координаты в описании отеля (1 / 0)
        - isdescription – есть ли детальное описание отеля (1 / 0)
        - isreviews – есть ли отзывы по отелю (1 / 0)
        - seadistance – расстояние до моря (в метрах)
        """
        try:
            logger.info(f"🏗️ Строим полную информацию об отеле: {hotel_data.get('hotelname', 'Unknown')}")
            
            # Создаем базовую информацию из полей TourVisor API
            hotel_info = self._create_base_hotel_info(hotel_data)
            hotel_id = hotel_info.get('hotel_id')
            
            # Если есть ID отеля, получаем детальную информацию
            if hotel_id:
                try:
                    logger.info(f"🔍 Запрашиваем детальную информацию об отеле {hotel_id}")
                    
                    # Получаем детальную информацию об отеле через TourVisor API
                    hotel_details = await tourvisor_client.get_hotel_info(
                        hotel_id, 
                        include_reviews=True, 
                        big_images=True
                    )
                    
                    if hotel_details:
                        logger.info(f"✅ Получена детальная информация об отеле {hotel_id}")
                        logger.debug(f"📋 Ключи в hotel_details: {list(hotel_details.keys()) if isinstance(hotel_details, dict) else 'not dict'}")
                        
                        # Обогащаем информацию деталями
                        hotel_info.update(self._enrich_hotel_info_with_details(hotel_info, hotel_details))
                    else:
                        logger.warning(f"⚠️ Детальная информация об отеле {hotel_id} недоступна")
                        
                except Exception as detail_error:
                    logger.warning(f"⚠️ Ошибка получения деталей отеля {hotel_id}: {detail_error}")
            else:
                logger.warning(f"⚠️ Нет ID отеля для получения деталей")
            
            logger.info(f"✅ Построена информация об отеле: {hotel_info.get('hotel_name', 'Unknown')}")
            return hotel_info
            
        except Exception as e:
            logger.error(f"❌ Ошибка построения информации об отеле: {e}")
            # Возвращаем базовую информацию в случае ошибки
            return self._create_base_hotel_info(hotel_data)

    def _create_base_hotel_info(self, hotel_data: Dict) -> Dict[str, Any]:
        """Создание базовой информации об отеле из данных TourVisor API"""
        try:
            # ИСПРАВЛЕНИЕ: Создаем ключи, которые ожидаются в других частях кода
            hotel_info = {
                # Основные поля отеля - ПРАВИЛЬНЫЕ КЛЮЧИ
                'hotel_id': hotel_data.get('hotelcode'),  # код отеля
                'hotel_name': hotel_data.get('hotelname', ''),  # название отеля
                'hotel_stars': self._safe_int(hotel_data.get('hotelstars', 0)),  # категория отеля (2,3,4 или 5)
                'hotel_rating': self._safe_float(hotel_data.get('hotelrating', 0.0)),  # рейтинг отеля от 1 до 5
                'min_price': self._safe_float(hotel_data.get('price', 0.0)),  # цена в рублях (минимальная)
                
                # ДОБАВЛЯЕМ КЛЮЧИ ДЛЯ СОВМЕСТИМОСТИ:
                'hotel_description': hotel_data.get('hoteldescription', ''),  # краткое описание отеля
                'hotel_picture': hotel_data.get('picturelink', ''),  # ссылка на картинку
                'hotel_review_link': hotel_data.get('reviewlink', ''),  # ссылка на отзывы
                
                # Информация о местоположении
                'country_code': hotel_data.get('countrycode'),  # код страны
                'country_name': hotel_data.get('countryname', ''),  # название страны
                'region_code': hotel_data.get('regioncode'),  # код курорта
                'region_name': hotel_data.get('regionname', ''),  # название курорта
                'subregion_code': hotel_data.get('subregioncode', 0),  # код вложенного курорта (района)
                
                # Описание и контент (дублируем для разных ключей)
                'description': hotel_data.get('hoteldescription', ''),  # краткое описание отеля
                'full_description_link': hotel_data.get('fulldesclink', ''),  # ссылка на полное описание
                'reviews_link': hotel_data.get('reviewlink', ''),  # ссылка на отзывы
                'picture_link': hotel_data.get('picturelink', ''),  # ссылка на картинку (130px)
                
                # Флаги наличия данных (1/0 из API)
                'has_photos': bool(self._safe_int(hotel_data.get('isphoto', 0))),  # есть ли фотографии
                'has_coordinates': bool(self._safe_int(hotel_data.get('iscoords', 0))),  # есть ли координаты
                'has_description': bool(self._safe_int(hotel_data.get('isdescription', 0))),  # есть ли детальное описание
                'has_reviews': bool(self._safe_int(hotel_data.get('isreviews', 0))),  # есть ли отзывы
                
                # Дополнительная информация
                'sea_distance': self._safe_int(hotel_data.get('seadistance', 0)),  # расстояние до моря в метрах
                
                # Обработанные данные для удобства использования
                'sea_distance_text': self._format_sea_distance(hotel_data.get('seadistance', 0)),
                'rating_text': self._format_rating(hotel_data.get('hotelrating', 0)),
                'stars_text': self._format_stars(hotel_data.get('hotelstars', 0)),
                
                # Туры (будут заполнены отдельно)
                'tours': hotel_data.get('tours', [])
            }
            
            # Дополнительные поля, которые могут быть заполнены из детальной информации
            try:
                hotel_info.update({
                    'main_photo': hotel_info['picture_link'],  # основное фото
                    'photos': [],  # список всех фотографий
                    'facilities': None,  # удобства отеля
                    'coordinates': None,  # координаты отеля
                    'detailed_description': '',  # детальное описание
                    'reviews': [],  # отзывы
                    'room_types': [],  # типы номеров
                    'meal_types': [],  # типы питания
                })
            except:
                hotel_info.update({
                    'main_photo': hotel_info['picture_link'],  # основное фото
                    'photos': [],  # список всех фотографий
                    'facilities': None,  # удобства отеля
                    'coordinates': None,  # координаты отеля
                    'detailed_description': '',  # детальное описание
                    'reviews': [],  # отзывы
                    'room_types': [],  # типы номеров
                    'meal_types': [],  # типы питания
                })
            return hotel_info
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания базовой информации об отеле: {e}")
            # Возвращаем минимальную структуру С ПРАВИЛЬНЫМИ КЛЮЧАМИ
            return {
                'hotel_id': hotel_data.get('hotelcode'),
                'hotel_name': hotel_data.get('hotelname', 'Неизвестный отель'),
                'hotel_stars': 0,
                'hotel_rating': 0.0,
                'min_price': 0.0,
                'country_name': hotel_data.get('countryname', ''),
                'region_name': hotel_data.get('regionname', ''),
                
                # ДОБАВЛЯЕМ ОБЯЗАТЕЛЬНЫЕ КЛЮЧИ ДЛЯ СОВМЕСТИМОСТИ:
                'hotel_description': hotel_data.get('hoteldescription', ''),
                'hotel_picture': hotel_data.get('picturelink', ''),
                'hotel_review_link': hotel_data.get('reviewlink', ''),
                'description': hotel_data.get('hoteldescription', ''),
                'sea_distance': 0,
                'tours': hotel_data.get('tours', [])
            }

    def _enrich_hotel_info_with_details(self, hotel_info: Dict, hotel_details: Dict) -> Dict[str, Any]:
        """Обогащение информации об отеле детальными данными из TourVisor API"""
        enriched_data = {}
        
        try:
            if not isinstance(hotel_details, dict):
                logger.warning("⚠️ hotel_details не является словарем")
                return enriched_data
            
            logger.info(f"🔧 Обогащаем отель деталями. Доступные ключи: {list(hotel_details.keys())}")
            
            # ✅ 1. ОСНОВНАЯ ИНФОРМАЦИЯ
            if hotel_details.get("description"):
                enriched_data['detailed_description'] = hotel_details['description']
                enriched_data['hotel_description'] = hotel_details['description']
            
            # ✅ 2. КОНТАКТНАЯ ИНФОРМАЦИЯ
            if hotel_details.get("phone"):
                enriched_data['phone'] = self._safe_string(hotel_details['phone'])
            
            if hotel_details.get("site"):
                enriched_data['website'] = self._safe_string(hotel_details['site'])
            
            # ✅ 3. ТЕХНИЧЕСКАЯ ИНФОРМАЦИЯ
            if hotel_details.get("build"):
                enriched_data['build_year'] = self._safe_int(hotel_details['build'])
            
            if hotel_details.get("repair"):
                enriched_data['renovation_year'] = self._safe_int(hotel_details['repair'])
            
            if hotel_details.get("square"):
                enriched_data['hotel_area'] = self._safe_string(hotel_details['square'])
            
            # ✅ 4. МЕСТОПОЛОЖЕНИЕ И КООРДИНАТЫ
            if hotel_details.get("placement"):
                enriched_data['short_description'] = self._safe_string(hotel_details['placement'])
            
            # Координаты
            lat = self._safe_float(hotel_details.get("coord1"))
            lng = self._safe_float(hotel_details.get("coord2"))
            if lat and lng:
                enriched_data['coordinates'] = {"lat": lat, "lng": lng}
            
            # ✅ 5. ИЗОБРАЖЕНИЯ
            images_data = self._build_images_info(hotel_details)
            if images_data[0]:  # Если есть изображения
                enriched_data['images'] = images_data[0]
                enriched_data['images_count'] = images_data[1]
                enriched_data['main_image'] = images_data[2]
                
                # Обновляем основное фото, если оно лучше
                if images_data[2] and not hotel_info.get('hotel_picture'):
                    enriched_data['hotel_picture'] = images_data[2]
            
            # ✅ 6. FACILITIES - ПРАВИЛЬНОЕ СОЗДАНИЕ
            facilities_data = self._build_facilities_info(hotel_details)
            if facilities_data:
                enriched_data['facilities'] = facilities_data
            
            # ✅ 7. ОТЗЫВЫ
            if hotel_details.get("reviews") and isinstance(hotel_details["reviews"], list):
                enriched_data['reviews'] = self._build_reviews_info(hotel_details)
            
            # ✅ 8. ОБНОВЛЯЕМ ФЛАГИ НАЛИЧИЯ ДАННЫХ
            if enriched_data.get('images'):
                enriched_data['has_photos'] = True
                enriched_data['is_photo'] = True
            
            if enriched_data.get('coordinates'):
                enriched_data['has_coordinates'] = True
                enriched_data['is_coords'] = True
            
            if enriched_data.get('detailed_description'):
                enriched_data['has_description'] = True
                enriched_data['is_description'] = True
            
            if enriched_data.get('reviews'):
                enriched_data['has_reviews'] = True
                enriched_data['is_reviews'] = True
            
            logger.info(f"✅ Обогащение завершено. Добавлено полей: {len(enriched_data)}")
            logger.debug(f"🔧 Добавленные поля: {list(enriched_data.keys())}")
            
            return enriched_data
            
        except Exception as e:
            logger.error(f"❌ Ошибка обогащения данных отеля: {e}")
            return enriched_data


    def _format_sea_distance(self, distance_meters: int) -> str:
        """Форматирование расстояния до моря"""
        try:
            distance = self._safe_int(distance_meters)
            if distance == 0:
                return "Расстояние не указано"
            elif distance < 50:
                return "На берегу моря"
            elif distance < 100:
                return f"{distance}м до моря"
            elif distance < 1000:
                return f"{distance}м до моря"
            else:
                km = distance / 1000
                return f"{km:.1f}км до моря"
        except:
            return "Расстояние не указано"


    def _format_rating(self, rating: float) -> str:
        """Форматирование рейтинга отеля"""
        try:
            rating_val = self._safe_float(rating)
            if rating_val == 0:
                return "Рейтинг не указан"
            else:
                return f"{rating_val:.1f}/5.0"
        except:
            return "Рейтинг не указан"


    def _format_stars(self, stars: int) -> str:
        """Форматирование звездности отеля"""
        try:
            stars_val = self._safe_int(stars)
            if stars_val == 0:
                return "Категория не указана"
            else:
                return f"{stars_val}★"
        except:
            return "Категория не указана"


    def _safe_int(self, value, default: int = 0) -> int:
        """Безопасное преобразование в int"""
        try:
            if value is None:
                return default
            return int(value)
        except (ValueError, TypeError):
            return default


    def _safe_float(self, value, default: float = 0.0) -> float:
        """Безопасное преобразование в float"""
        try:
            if value is None:
                return default
            return float(value)
        except (ValueError, TypeError):
            return default

    
    def _build_facilities_info(self, hotel_details: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Построение информации об удобствах отеля - возвращает dict для HotelFacilities"""
        try:
            facilities = {
                "territory": "",
                "in_room": "",
                "room_types": [],
                "services": [],
                "services_free": [],
                "services_paid": [],
                "animation": "",
                "child_services": "",
                "beach_description": "",
                "meal_types": [],
                "meal_description": ""
            }
            
            # Заполняем данными из hotel_details
            if hotel_details.get("territory"):
                facilities["territory"] = self._safe_string(hotel_details["territory"])
            
            if hotel_details.get("inroom"):
                facilities["in_room"] = self._safe_string(hotel_details["inroom"])
            
            # Типы номеров
            if hotel_details.get("roomtypes"):
                room_types = hotel_details["roomtypes"]
                if isinstance(room_types, list):
                    facilities["room_types"] = [self._safe_string(rt) for rt in room_types]
                elif isinstance(room_types, str):
                    facilities["room_types"] = [self._safe_string(room_types)]
            
            # Услуги
            facilities["services"] = self._parse_services_list(hotel_details.get("services"))
            facilities["services_free"] = self._parse_services_list(hotel_details.get("servicefree"))
            facilities["services_paid"] = self._parse_services_list(hotel_details.get("servicepay"))
            
            # Остальные поля
            if hotel_details.get("animation"):
                facilities["animation"] = self._safe_string(hotel_details["animation"])
            
            if hotel_details.get("child"):
                facilities["child_services"] = self._safe_string(hotel_details["child"])
            
            if hotel_details.get("beach"):
                facilities["beach_description"] = self._safe_string(hotel_details["beach"])
            
            # Питание
            facilities["meal_types"] = self._parse_services_list(hotel_details.get("meallist"))
            if hotel_details.get("mealtypes"):
                facilities["meal_description"] = self._safe_string(hotel_details["mealtypes"])
            
            # ✅ ВСЕГДА возвращаем dict (который Pydantic преобразует в HotelFacilities)
            return facilities
            
        except Exception as e:
            logger.error(f"❌ Ошибка построения информации об удобствах: {e}")
            # ✅ При ошибке возвращаем базовый dict:
            return {
                "territory": "",
                "in_room": "",
                "room_types": [],
                "services": [],
                "services_free": [],
                "services_paid": [],
                "animation": "",
                "child_services": "",
                "beach_description": "",
                "meal_types": [],
                "meal_description": ""
            }
    def _parse_services_list(self, services_data: Any) -> List[str]:
        """Парсинг списка услуг"""
        try:
            if not services_data:
                return []
            
            if isinstance(services_data, list):
                return [self._safe_string(service) for service in services_data if service]
            elif isinstance(services_data, str):
                # Пробуем разделить по запятым или переносам строк
                services = services_data.replace('\n', ',').split(',')
                return [self._safe_string(service.strip()) for service in services if service.strip()]
            else:
                return [self._safe_string(services_data)]
                
        except Exception as e:
            logger.debug(f"Ошибка парсинга списка услуг: {e}")
            return []

    def _build_images_info(self, hotel_details: Dict[str, Any]) -> tuple:
        """Построение информации об изображениях отеля"""
        try:
            images = []
            main_image = ""
            
            # Проверяем поле images
            if "images" in hotel_details:
                images_data = hotel_details["images"]
                
                if isinstance(images_data, list):
                    for img in images_data:
                        if isinstance(img, dict):
                            image_info = {
                                "url": self._safe_string(img.get("image") or img.get("url") or img.get("link")),
                                "description": self._safe_string(img.get("description", "")),
                                "type": self._safe_string(img.get("type", "hotel"))
                            }
                            if image_info["url"]:
                                images.append(image_info)
                        elif isinstance(img, str) and img.strip():
                            images.append({
                                "url": self._safe_string(img),
                                "description": "",
                                "type": "hotel"
                            })
                elif isinstance(images_data, str) and images_data.strip():
                    images.append({
                        "url": self._safe_string(images_data),
                        "description": "",
                        "type": "hotel"
                    })
            
            # Проверяем отдельные поля с изображениями
            image_fields = ["hotelpicturebig", "hotelpicturemedium", "hotelpicturesmall", "picture", "image"]
            for field in image_fields:
                if hotel_details.get(field):
                    image_url = self._safe_string(hotel_details[field])
                    if image_url and not any(img["url"] == image_url for img in images):
                        images.append({
                            "url": image_url,
                            "description": f"Фото отеля ({field})",
                            "type": "hotel"
                        })
            
            # Устанавливаем главное изображение
            if images:
                main_image = images[0]["url"]
            
            images_count = len(images)
            
            logger.debug(f"📸 Найдено {images_count} изображений отеля")
            return images, images_count, main_image
            
        except Exception as e:
            logger.error(f"❌ Ошибка построения информации об изображениях: {e}")
            return [], 0, ""

    def _build_reviews_info(self, hotel_details: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Построение информации об отзывах"""
        try:
            reviews = []
            
            if "reviews" in hotel_details:
                reviews_data = hotel_details["reviews"]
                
                if isinstance(reviews_data, list):
                    for review in reviews_data[:5]:  # Берем только первые 5 отзывов
                        if isinstance(review, dict):
                            review_info = {
                                "author": self._safe_string(review.get("author", "Аноним")),
                                "date": self._safe_string(review.get("date", "")),
                                "rating": self._safe_float(review.get("rating")),
                                "title": self._safe_string(review.get("title", "")),
                                "text": self._safe_string(review.get("text", "")),
                                "pros": self._safe_string(review.get("pros", "")),
                                "cons": self._safe_string(review.get("cons", ""))
                            }
                            reviews.append(review_info)
            
            logger.debug(f"📝 Найдено {len(reviews)} отзывов")
            return reviews
            
        except Exception as e:
            logger.error(f"❌ Ошибка построения информации об отзывах: {e}")
            return []

    def _set_hotel_flags(self, hotel_info: Dict[str, Any]) -> Dict[str, Any]:
        """Установка флагов наличия различных типов данных"""
        try:
            # Проверяем наличие фотографий
            has_photos = bool(hotel_info.get("images") or hotel_info.get("hotel_picture") or hotel_info.get("main_image"))
            hotel_info["has_photos"] = has_photos
            hotel_info["is_photo"] = has_photos  # для совместимости
            
            # Проверяем наличие координат
            location = hotel_info.get("location", {})
            has_coordinates = bool(location and location.get("latitude") and location.get("longitude"))
            hotel_info["has_coordinates"] = has_coordinates
            hotel_info["is_coords"] = has_coordinates  # для совместимости
            
            # Проверяем наличие описания
            has_description = bool(hotel_info.get("description") or hotel_info.get("hotel_description"))
            hotel_info["has_description"] = has_description
            hotel_info["is_description"] = has_description  # для совместимости
            
            # Проверяем наличие отзывов
            has_reviews = bool(hotel_info.get("reviews"))
            hotel_info["has_reviews"] = has_reviews
            hotel_info["is_reviews"] = has_reviews  # для совместимости
            
            return hotel_info
            
        except Exception as e:
            logger.error(f"❌ Ошибка установки флагов: {e}")
            return hotel_info

    def _create_tour_info(self, hotel_data: Dict, tour_data: Dict) -> Dict[str, Any]:
        """Создание информации о туре"""
        try:
            # ИСПРАВЛЕНИЕ: Создаем правильные ключи для туров
            tour_info = {
                "tour_id": self._safe_string(tour_data.get("tourid")),
                "operator_name": self._safe_string(tour_data.get("operatorname", "")),
                "fly_date": self._safe_string(tour_data.get("flydate")),
                "nights": self._safe_int(tour_data.get("nights")) or 7,
                
                # ИСПРАВЛЕНИЕ: Правильное преобразование цены
                "price": self._safe_float(tour_data.get("price")) or 0.0,  # Используем float вместо int
                "fuel_charge": self._safe_float(tour_data.get("fuelcharge")) or 0.0,
                
                "meal": self._safe_string(tour_data.get("meal", "")),
                "room_type": self._safe_string(tour_data.get("room", "")),
                
                # ИСПРАВЛЕНИЕ: Правильные типы данных
                "adults": self._safe_int(tour_data.get("adults")) or 2,
                "children": self._safe_int(tour_data.get("child")) or 0,
                
                "tour_link": self._safe_string(tour_data.get("tourlink")),
                "currency": self._safe_string(tour_data.get("currency", "RUB")),
                
                # ИСПРАВЛЕНИЕ: Правильная обработка булевых значений
                "is_regular": bool(self._safe_int(tour_data.get("regular", 0))),
                "is_promo": bool(self._safe_int(tour_data.get("promo", 0))),
                "is_on_request": bool(self._safe_int(tour_data.get("onrequest", 0))),
                
                # Дополнительные поля для совместимости
                "flight_status": self._safe_int(tour_data.get("flightstatus", 1)),
                "hotel_status": self._safe_int(tour_data.get("hotelstatus", 1)),
                
                # Дополнительная информация о туре
                "tour_name": self._safe_string(tour_data.get("tourname", "")),
                "placement": self._safe_string(tour_data.get("placement", "")),
                "meal_russian": self._safe_string(tour_data.get("mealrussian", "")),
                
                # Дополнительные поля из TourVisor API
                "night_flight": self._safe_int(tour_data.get("nightflight", 0)),
                "price_ue": self._safe_float(tour_data.get("priceue", 0.0)),
            }
            
            return tour_info
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания информации о туре: {e}")
            # Возвращаем минимальную структуру
            return {
                "tour_id": tour_data.get("tourid"),
                "operator_name": tour_data.get("operatorname", "Неизвестный оператор"),
                "fly_date": tour_data.get("flydate", ""),
                "nights": 7,
                "price": 0.0,
                "fuel_charge": 0.0,
                "meal": "",
                "room_type": "",
                "adults": 2,
                "children": 0,
                "currency": "RUB",
                "is_regular": False,
                "is_promo": False,
                "is_on_request": False,
                "flight_status": 1,
                "hotel_status": 1
            }


    # ТАКЖЕ НУЖНО ИСПРАВИТЬ _safe_float МЕТОД
    def _safe_float(self, value, default: float = 0.0) -> float:
        """Безопасное преобразование в float"""
        try:
            if value is None or value == "":
                return default
            
            # Если это строка, убираем лишние символы
            if isinstance(value, str):
                # Убираем пробелы и запятые (для цен)
                cleaned = value.strip().replace(',', '').replace(' ', '')
                if not cleaned:
                    return default
                return float(cleaned)
            
            return float(value)
        except (ValueError, TypeError):
            return default


    def _safe_int(self, value, default: int = 0) -> int:
        """Безопасное преобразование в int"""
        try:
            if value is None or value == "":
                return default
            
            # Если это строка, убираем лишние символы
            if isinstance(value, str):
                cleaned = value.strip().replace(',', '').replace(' ', '')
                if not cleaned:
                    return default
                return int(float(cleaned))  # Через float для обработки "123.0"
            
            return int(value)
        except (ValueError, TypeError):
            return default


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
    # Добавьте эти методы в класс SpecificTourService в app/services/specific_tour_service.py

    def _extract_hotels_from_results(self, search_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Извлечение отелей из результатов поиска"""
        try:
            logger.debug(f"🔍 Извлекаем отели из результатов поиска")
            
            data = search_results.get("data", {})
            result_data = data.get("result", {})
            hotels = result_data.get("hotel", [])
            
            # Нормализуем в список
            if not isinstance(hotels, list):
                hotels = [hotels] if hotels else []
            
            logger.info(f"📊 Извлечено {len(hotels)} отелей из результатов")
            return hotels
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения отелей: {e}")
            return []

    def _select_best_hotel(self, hotels_data: List[Dict[str, Any]], search_request: SpecificTourSearchRequest) -> Optional[Dict[str, Any]]:
        """Выбор лучшего отеля из списка"""
        try:
            if not hotels_data:
                return None
            
            logger.info(f"🏆 Выбираем лучший отель из {len(hotels_data)} вариантов")
            
            # Фильтруем отели с турами
            hotels_with_tours = []
            for hotel in hotels_data:
                tours_data = hotel.get("tours", {})
                if tours_data:
                    tours = tours_data.get("tour", [])
                    if tours:
                        hotels_with_tours.append(hotel)
            
            if not hotels_with_tours:
                logger.warning(f"❌ Нет отелей с турами")
                return None
            
            logger.info(f"🏨 Найдено {len(hotels_with_tours)} отелей с турами")
            
            # Выбираем отель по критериям качества
            best_hotel = max(hotels_with_tours, key=lambda h: self._calculate_hotel_score(h))
            
            logger.info(f"✅ Выбран лучший отель: {best_hotel.get('hotelname', 'Unknown')}")
            return best_hotel
            
        except Exception as e:
            logger.error(f"❌ Ошибка выбора лучшего отеля: {e}")
            return hotels_data[0] if hotels_data else None

    def _extract_tours_from_hotel(self, hotel_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Извлечение туров из данных отеля"""
        try:
            hotel_name = hotel_data.get("hotelname", "Unknown")
            logger.debug(f"🎫 Извлекаем туры из отеля: {hotel_name}")
            
            tours_data = hotel_data.get("tours", {})
            if not tours_data:
                logger.warning(f"❌ Нет туров в отеле {hotel_name}")
                return []
            
            tours = tours_data.get("tour", [])
            
            # Нормализуем в список
            if not isinstance(tours, list):
                tours = [tours] if tours else []
            
            logger.info(f"🎫 Найдено {len(tours)} туров в отеле {hotel_name}")
            return tours
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения туров: {e}")
            return []

    def _calculate_hotel_score(self, hotel: Dict[str, Any]) -> float:
        """Расчет балла качества отеля"""
        try:
            score = 0.0
            
            # Звездность отеля
            stars = self._safe_int(hotel.get("hotelstars")) or 0
            score += stars * 10
            
            # Рейтинг отеля
            rating = self._safe_float(hotel.get("hotelrating")) or 0
            if rating > 0:
                score += rating * 20
            
            # Расстояние до моря (чем меньше, тем лучше)
            sea_distance = self._safe_int(hotel.get("seadistance")) or 1000
            if sea_distance <= 100:
                score += 15
            elif sea_distance <= 300:
                score += 10
            elif sea_distance <= 500:
                score += 5
            
            # Наличие фото
            if hotel.get("isphoto") == "1":
                score += 5
            
            # Наличие описания
            if hotel.get("isdescription") == "1":
                score += 3
            
            # Наличие отзывов
            if hotel.get("isreviews") == "1":
                score += 2
            
            return score
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета балла отеля: {e}")
            return 0.0

    async def _process_search_results(self, search_results: Dict[str, Any], search_request: SpecificTourSearchRequest) -> Optional[Dict[str, Any]]:
        """Обработка результатов поиска с обогащением информации об отеле"""
        try:
            logger.info(f"🔄 Начинаем обработку результатов поиска")
            
            # Извлекаем отели из результатов
            hotels_data = self._extract_hotels_from_results(search_results)
            
            if not hotels_data:
                logger.warning(f"❌ Отели не найдены в результатах поиска")
                return None
            
            logger.info(f"📊 Найдено {len(hotels_data)} отелей")
            
            # Выбираем лучший отель (по рейтингу и другим критериям)
            best_hotel = self._select_best_hotel(hotels_data, search_request)
            
            if not best_hotel:
                logger.warning(f"❌ Не удалось выбрать лучший отель")
                return None
            
            # ВАЖНО: Обогащаем информацию об отеле дополнительными данными
            logger.info(f"🏗️ Обогащаем информацию об отеле: {best_hotel.get('hotelname', 'Unknown')}")
            hotel_info = await self._build_hotel_info(best_hotel)
            
            # Извлекаем и обрабатываем туры
            tours_data = self._extract_tours_from_hotel(best_hotel)
            
            if not tours_data:
                logger.warning(f"❌ Туры не найдены для отеля {hotel_info.get('hotel_name', 'Unknown')}")
                return None
            
            # Сортируем туры по цене
            sorted_tours = sorted(tours_data, key=lambda t: self._safe_float(t.get('price', 0)) or float('inf'))
            
            # Создаем список туров
            tours_list = []
            for tour_data in sorted_tours:
                tour_info = self._create_tour_info(best_hotel, tour_data)
                tours_list.append(tour_info)
            
            logger.info(f"✅ Обработано {len(tours_list)} туров для отеля {hotel_info.get('hotel_name', 'Unknown')}")
            
            # Возвращаем полную информацию
            return {
                "hotel_info": hotel_info,  # ОБОГАЩЕННАЯ информация об отеле
                "tours": tours_list,
                "tours_count": len(tours_list),
                "search_results_count": len(hotels_data),
                "is_fallback": False,
                "fallback_strategy": None,
                "available_dates": self._extract_available_dates(tours_list),
                "meal_types": self._extract_meal_types(tours_list),
                "operators": self._extract_operators(tours_list),
                "price_range": self._calculate_price_range(tours_list)
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки результатов поиска: {e}")
            return None

    def _extract_available_dates(self, tours_list: List[Dict[str, Any]]) -> List[str]:
        """Извлечение доступных дат вылета"""
        try:
            dates = set()
            for tour in tours_list:
                fly_date = tour.get('fly_date')
                if fly_date:
                    dates.add(fly_date)
            return sorted(list(dates))
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения дат: {e}")
            return []

    def _extract_meal_types(self, tours_list: List[Dict[str, Any]]) -> List[str]:
        """Извлечение типов питания"""
        try:
            meals = set()
            for tour in tours_list:
                meal = tour.get('meal')
                if meal:
                    meals.add(meal)
            return sorted(list(meals))
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения типов питания: {e}")
            return []

    def _extract_operators(self, tours_list: List[Dict[str, Any]]) -> List[str]:
        """Извлечение туроператоров"""
        try:
            operators = set()
            for tour in tours_list:
                operator = tour.get('operator_name')
                if operator:
                    operators.add(operator)
            return sorted(list(operators))
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения операторов: {e}")
            return []

    def _calculate_price_range(self, tours_list: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
        """Расчет диапазона цен"""
        try:
            if not tours_list:
                return None
            
            prices = [tour.get('price', 0) for tour in tours_list if tour.get('price', 0) > 0]
            
            if not prices:
                return None
            
            return {
                "min_price": min(prices),
                "max_price": max(prices),
                "avg_price": sum(prices) / len(prices)
            }
        except Exception as e:
            logger.error(f"❌ Ошибка расчета диапазона цен: {e}")
            return None
# Создаем экземпляр сервиса
specific_tour_service = SpecificTourService()