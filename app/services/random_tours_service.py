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
    """Улучшенный сервис для работы со случайными турами"""
    
    def __init__(self):
        self.cache = cache_service
        # Расширенный список стран и городов
        self.popular_countries = [1, 4, 8, 15, 22, 35]  # Египет, Турция, Греция, ОАЭ, Таиланд, Мальдивы
        self.all_cities = [1, 2, 3, 5, 6]  # Москва, Пермь, Екатеринбург, СПб, Казань
    
    async def get_random_tours(self, request: RandomTourRequest) -> List[HotTourInfo]:
        """Получение случайных туров с многоуровневой стратегией"""
        cache_key = f"random_tours_count_{request.count}"
        
        logger.info(f"🎯 Запрос {request.count} случайных туров")
        
        # Проверяем кэш
        try:
            cached_tours = await self.cache.get(cache_key)
            if cached_tours:
                tours_list = []
                for tour_data in cached_tours[:request.count]:
                    try:
                        tour = HotTourInfo(**tour_data)
                        tours_list.append(tour)
                    except Exception as e:
                        logger.debug(f"Ошибка при создании объекта тура из кэша: {e}")
                        continue
                
                if len(tours_list) >= request.count:
                    logger.info(f"✅ Возвращено {len(tours_list)} туров из кэша")
                    return tours_list
        except Exception as e:
            logger.error(f"❌ Ошибка при работе с кэшем: {e}")
        
        # Генерируем новые туры
        logger.info("🔄 Генерируем новые случайные туры")
        return await self._generate_random_tours_multilevel(request)
    
    async def _generate_random_tours_multilevel(self, request: RandomTourRequest) -> List[HotTourInfo]:
        """Многоуровневая генерация случайных туров"""
        logger.info(f"🎲 НАЧИНАЕМ МНОГОУРОВНЕВУЮ ГЕНЕРАЦИЮ {request.count} ТУРОВ")
        
        random_tours = []
        
        # Уровень 1: Горящие туры (самый быстрый)
        logger.info("📍 Уровень 1: Пробуем горящие туры")
        hot_tours_result = await self._try_hot_tours_strategy()
        if hot_tours_result and len(hot_tours_result) >= request.count:
            random_tours = hot_tours_result[:request.count]
            logger.info(f"🔥 Успех на уровне 1: получено {len(random_tours)} туров")
        else:
            if hot_tours_result:
                random_tours.extend(hot_tours_result)
                logger.info(f"🔥 Частичный успех на уровне 1: {len(hot_tours_result)} туров")
        
        # Уровень 2: Обычный поиск (если нужно больше туров)
        if len(random_tours) < request.count:
            needed = request.count - len(random_tours)
            logger.info(f"📍 Уровень 2: Нужно еще {needed} туров, запускаем поиск")
            
            search_tours = await self._try_search_strategy(needed)
            if search_tours:
                random_tours.extend(search_tours)
                logger.info(f"🔍 Успех на уровне 2: добавлено {len(search_tours)} туров")
        
        # Уровень 3: Mock-данные (гарантированный результат)
        if len(random_tours) < request.count:
            needed = request.count - len(random_tours)
            logger.info(f"📍 Уровень 3: Создаем {needed} mock-туров")
            
            mock_tours = await self._create_smart_mock_tours(needed)
            random_tours.extend(mock_tours)
            logger.info(f"🎭 Добавлено {len(mock_tours)} mock-туров")
        
        # Перемешиваем результат
        random.shuffle(random_tours)
        final_tours = random_tours[:request.count]
        
        # Сохраняем в кэш
        if final_tours:
            try:
                cache_key = f"random_tours_count_{request.count}"
                await self.cache.set(
                    cache_key,
                    [tour.dict() for tour in final_tours],
                    ttl=1800  # 30 минут для случайных туров
                )
                logger.info(f"💾 Сохранено {len(final_tours)} туров в кэш")
            except Exception as cache_error:
                logger.error(f"❌ Ошибка сохранения в кэш: {cache_error}")
        
        logger.info(f"🏁 ГЕНЕРАЦИЯ ЗАВЕРШЕНА: {len(final_tours)} туров")
        return final_tours
    
    async def _try_hot_tours_strategy(self) -> List[HotTourInfo]:
        """Стратегия получения туров через горящие туры"""
        try:
            logger.info("🔥 Пробуем стратегию горящих туров")
            
            all_tours = []
            
            # Пробуем с разными параметрами
            strategies = [
                # Стратегия 1: Без фильтров
                {"items": 15},
                # Стратегия 2: Только хорошие отели
                {"items": 10, "stars": 4},
                # Стратегия 3: Популярные страны
                {"items": 8, "countries": "1,4,22"},  # Египет, Турция, Таиланд
            ]
            
            for city in self.all_cities[:3]:  # Берем первые 3 города
                for strategy in strategies:
                    try:
                        logger.debug(f"🔥 Тестируем город {city} со стратегией {strategy}")
                        
                        hot_tours_data = await tourvisor_client.get_hot_tours(
                            city=city,
                            **strategy
                        )
                        
                        tours_list = hot_tours_data.get("hottours", [])
                        if not isinstance(tours_list, list):
                            tours_list = [tours_list] if tours_list else []
                        
                        logger.debug(f"🔥 Город {city}: найдено {len(tours_list)} туров")
                        
                        for tour_data in tours_list:
                            try:
                                tour = HotTourInfo(**tour_data)
                                all_tours.append(tour)
                            except Exception as tour_error:
                                logger.debug(f"Ошибка создания тура: {tour_error}")
                                continue
                        
                        # Если нашли туры, переходим к следующему городу
                        if tours_list:
                            break
                        
                        await asyncio.sleep(0.2)
                        
                    except Exception as strategy_error:
                        logger.debug(f"🔥 Ошибка стратегии {strategy}: {strategy_error}")
                        continue
                
                # Задержка между городами
                await asyncio.sleep(0.3)
            
            if all_tours:
                # Убираем дубликаты по hotel_code
                seen_hotels = set()
                unique_tours = []
                for tour in all_tours:
                    if tour.hotelcode not in seen_hotels:
                        seen_hotels.add(tour.hotelcode)
                        unique_tours.append(tour)
                
                logger.info(f"🔥 Стратегия горящих туров: {len(unique_tours)} уникальных туров")
                return unique_tours
            
            logger.info("🔥 Стратегия горящих туров не дала результатов")
            return []
            
        except Exception as e:
            logger.error(f"🔥 Ошибка стратегии горящих туров: {e}")
            return []
    
    async def _try_search_strategy(self, needed_count: int) -> List[HotTourInfo]:
        """Стратегия получения туров через обычный поиск"""
        try:
            logger.info(f"🔍 Пробуем стратегию поиска для {needed_count} туров")
            
            found_tours = []
            max_attempts = min(needed_count * 2, 8)  # Ограничиваем количество попыток
            
            search_variants = self._create_optimized_search_variants(max_attempts)
            
            for i, search_params in enumerate(search_variants):
                if len(found_tours) >= needed_count:
                    break
                
                try:
                    country_name = tour_service._get_country_name(search_params['country'])
                    city_name = tour_service._get_city_name(search_params['departure'])
                    
                    logger.debug(f"🔍 Поиск {i+1}/{len(search_variants)}: {country_name} из {city_name}")
                    
                    # Запускаем поиск
                    request_id = await tourvisor_client.search_tours(search_params)
                    
                    # Быстрое ожидание результатов (максимум 3 секунды)
                    tour_found = await self._quick_search_result(request_id, search_params)
                    
                    if tour_found:
                        found_tours.append(tour_found)
                        logger.debug(f"✅ Найден тур: {tour_found.hotelname}")
                    
                    # Короткая задержка
                    await asyncio.sleep(0.3)
                    
                except Exception as e:
                    logger.debug(f"🔍 Ошибка поиска {i+1}: {e}")
                    continue
            
            logger.info(f"🔍 Стратегия поиска: найдено {len(found_tours)} туров")
            return found_tours
            
        except Exception as e:
            logger.error(f"🔍 Ошибка стратегии поиска: {e}")
            return []
    
    def _create_optimized_search_variants(self, max_variants: int) -> List[Dict[str, Any]]:
        """Создание оптимизированных вариантов поиска"""
        variants = []
        
        # Популярные комбинации страна-город
        popular_combinations = [
            (1, 1),   # Египет из Москвы
            (4, 1),   # Турция из Москвы
            (22, 1),  # Таиланд из Москвы
            (8, 2),   # Греция из Перми
            (15, 3),  # ОАЭ из Екатеринбурга
            (4, 5),   # Турция из СПб
        ]
        
        # Базовые параметры поиска
        base_dates = {
            "datefrom": (datetime.now() + timedelta(days=14)).strftime("%d.%m.%Y"),
            "dateto": (datetime.now() + timedelta(days=21)).strftime("%d.%m.%Y")
        }
        
        base_params = {
            "nightsfrom": 7,
            "nightsto": 10,
            "adults": 2,
            "child": 0
        }
        
        for i in range(min(max_variants, len(popular_combinations))):
            country, city = popular_combinations[i]
            
            variant = {
                "departure": city,
                "country": country,
                **base_dates,
                **base_params
            }
            
            # Иногда добавляем звездность
            if i % 2 == 0:
                variant["stars"] = random.choice([3, 4])
            
            variants.append(variant)
        
        return variants
    
    async def _quick_search_result(self, request_id: str, search_params: Dict[str, Any]) -> Optional[HotTourInfo]:
        """Быстрое получение результата поиска"""
        try:
            # Быстрое ожидание (максимум 3 секунды)
            for attempt in range(3):
                await asyncio.sleep(1)
                
                status_result = await tourvisor_client.get_search_status(request_id)
                status_data = status_result.get("data", {}).get("status", {})
                state = status_data.get("state", "searching")
                hotels_found = status_data.get("hotelsfound", 0)
                
                # Безопасное преобразование в int
                try:
                    hotels_found = int(hotels_found) if hotels_found else 0
                except (ValueError, TypeError):
                    hotels_found = 0
                
                # Прерываем если есть результаты
                if state == "finished" or (hotels_found > 0 and attempt >= 1):
                    break
            
            # Получаем результаты
            results = await tourvisor_client.get_search_results(request_id, 1, 5)
            data = results.get("data", {})
            result_data = data.get("result", {})
            hotel_list = result_data.get("hotel", [])
            
            if not isinstance(hotel_list, list):
                hotel_list = [hotel_list] if hotel_list else []
            
            if not hotel_list:
                return None
            
            # Берем первый отель и первый тур
            hotel = hotel_list[0]
            tours_data = hotel.get("tours", {}).get("tour", [])
            
            if not isinstance(tours_data, list):
                tours_data = [tours_data] if tours_data else []
            
            if not tours_data:
                return None
            
            tour_data = tours_data[0]
            
            # Конвертируем в HotTourInfo
            hot_tour_data = self._convert_search_to_hot_tour(hotel, tour_data, search_params)
            return HotTourInfo(**hot_tour_data)
            
        except Exception as e:
            logger.debug(f"❌ Ошибка быстрого поиска: {e}")
            return None
    
    def _convert_search_to_hot_tour(self, hotel_data: Dict, tour_data: Dict, search_params: Dict) -> Dict[str, Any]:
        """Конвертация результата поиска в формат HotTourInfo"""
        
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
            "priceold": None,
            "currency": tour_data.get("currency", "RUB")
        }
    
    async def _create_smart_mock_tours(self, count: int) -> List[HotTourInfo]:
        """Создание умных mock-туров с реалистичными данными"""
        logger.info(f"🎭 Создаем {count} умных mock-туров")
        
        mock_tours = []
        
        # Реалистичные данные для mock-туров
        destinations = [
            {"code": 1, "name": "Египет", "regions": ["Хургада", "Шарм-эль-Шейх"], "base_price": 45000},
            {"code": 4, "name": "Турция", "regions": ["Анталья", "Кемер", "Белек"], "base_price": 35000},
            {"code": 8, "name": "Греция", "regions": ["Крит", "Родос", "Халкидики"], "base_price": 55000},
            {"code": 15, "name": "ОАЭ", "regions": ["Дубай", "Абу-Даби", "Шарджа"], "base_price": 75000},
            {"code": 22, "name": "Таиланд", "regions": ["Пхукет", "Паттайя", "Самуи"], "base_price": 95000},
        ]
        
        cities = [
            {"code": 1, "name": "Москва", "namefrom": "Москвы"},
            {"code": 2, "name": "Пермь", "namefrom": "Перми"},
            {"code": 3, "name": "Екатеринбург", "namefrom": "Екатеринбурга"},
            {"code": 5, "name": "Санкт-Петербург", "namefrom": "Санкт-Петербурга"},
        ]
        
        operators = ["Pegas Touristik", "Coral Travel", "Anex Tour", "TEZ TOUR", "Sunmar"]
        meals = ["Завтрак", "Полупансион", "Всё включено", "Ultra All Inclusive"]
        
        for i in range(count):
            destination = random.choice(destinations)
            city = random.choice(cities)
            operator = random.choice(operators)
            region = random.choice(destination["regions"])
            meal = random.choice(meals)
            
            # Генерируем реалистичную цену
            base_price = destination["base_price"]
            price_variation = random.randint(-15000, 25000)
            final_price = max(25000, base_price + price_variation)
            
            # Генерируем дату вылета (в пределах месяца)
            departure_date = datetime.now() + timedelta(days=random.randint(7, 30))
            
            mock_tour_data = {
                "countrycode": str(destination["code"]),
                "countryname": destination["name"],
                "departurecode": str(city["code"]),
                "departurename": city["name"],
                "departurenamefrom": city["namefrom"],
                "operatorcode": str(i + 10),
                "operatorname": operator,
                "hotelcode": str(1000 + i),
                "hotelname": f"{destination['name'].upper()} RESORT {region.upper()} {i+1}",
                "hotelstars": random.choice([3, 4, 5]),
                "hotelregioncode": str(100 + i),
                "hotelregionname": region,
                "hotelpicture": f"https://via.placeholder.com/250x150/{'4a90e2' if i % 2 == 0 else 'e74c3c'}/ffffff?text={region}+Resort",
                "fulldesclink": f"https://example.com/hotel/{1000+i}",
                "flydate": departure_date.strftime("%d.%m.%Y"),
                "nights": random.choice([7, 10, 14]),
                "meal": meal,
                "price": float(final_price),
                "priceold": float(final_price + random.randint(5000, 15000)),
                "currency": "RUB"
            }
            
            try:
                mock_tour = HotTourInfo(**mock_tour_data)
                mock_tours.append(mock_tour)
            except Exception as e:
                logger.warning(f"Ошибка создания mock-тура: {e}")
                continue
        
        logger.info(f"🎭 Создано {len(mock_tours)} умных mock-туров")
        return mock_tours
    
    async def get_random_tours_status(self) -> Dict[str, Any]:
        """Получение статуса системы случайных туров"""
        try:
            # Проверяем кэш
            cache_keys = await self.cache.get_keys_pattern("random_tours_count_*")
            
            status = {
                "cache_status": {
                    "cached_variants": len(cache_keys),
                    "cache_keys": cache_keys
                },
                "last_generation": "unknown",
                "strategies": {
                    "hot_tours": "Получение через горящие туры (быстро)",
                    "search": "Получение через обычный поиск (медленно)",
                    "mock": "Создание mock-данных (гарантированно)"
                },
                "api_status": "unknown"
            }
            
            # Проверяем API
            try:
                test_result = await tourvisor_client.test_connection()
                status["api_status"] = "working" if test_result.get("success") else "error"
            except:
                status["api_status"] = "error"
            
            return status
            
        except Exception as e:
            return {"error": str(e)}
    
    async def refresh_random_tours(self, count: int = 6) -> Dict[str, Any]:
        """Принудительное обновление случайных туров"""
        try:
            logger.info(f"🔄 Принудительное обновление {count} случайных туров")
            
            # Очищаем кэш
            cache_keys = await self.cache.get_keys_pattern("random_tours_count_*")
            for key in cache_keys:
                await self.cache.delete(key)
            
            # Генерируем новые туры
            request = RandomTourRequest(count=count)
            new_tours = await self._generate_random_tours_multilevel(request)
            
            return {
                "success": True,
                "message": f"Обновлено {len(new_tours)} случайных туров",
                "cleared_cache_keys": len(cache_keys),
                "tours_generated": len(new_tours),
                "tours_preview": [
                    {
                        "hotel": tour.hotelname,
                        "country": tour.countryname,
                        "price": tour.price
                    }
                    for tour in new_tours[:3]
                ]
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении случайных туров: {e}")
            return {
                "success": False,
                "error": str(e)
            }

# Создаем экземпляр улучшенного сервиса
random_tours_service = RandomToursService()