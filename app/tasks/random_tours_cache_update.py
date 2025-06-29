# app/tasks/random_tours_cache_update.py - ОБНОВЛЕННАЯ ВЕРСИЯ С HOTELTYPES

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import traceback
import random

from app.services.random_tours_service import random_tours_service
from app.services.cache_service import cache_service
from app.models.tour import RandomTourRequest
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class RandomToursCacheUpdateService:
    """Сервис для автоматического обновления кэша случайных туров с правильной фильтрацией по типам отелей"""
    
    def __init__(self):
        # Настройки из переменных окружения
        import os
        self.update_interval = int(os.getenv("RANDOM_TOURS_UPDATE_INTERVAL_HOURS", "12")) * 3600  # 12 часов по умолчанию
        self.tours_per_type = int(os.getenv("RANDOM_TOURS_PER_TYPE", "8"))  # 8 туров на тип отеля
        self.generation_strategies = os.getenv("RANDOM_TOURS_STRATEGIES", "search,hot_tours,mock").split(",")
        self.countries_to_update = os.getenv("RANDOM_TOURS_COUNTRIES", "1,2,4,9,8").split(",")  # Топ страны
        
        # ОБНОВЛЕННЫЕ типы отелей с правильным маппингом на API TourVisor
        self.hotel_types_mapping = {
            "любой": {
                "display_name": "любой", 
                "api_param": None,  # Без фильтрации
                "cache_key": "любой"
            },
            "активный": {
                "display_name": "активный отдых",
                "api_param": "active",  # TourVisor API: active
                "cache_key": "активный"
            },
            "релакс": {
                "display_name": "релакс отели",
                "api_param": "relax",  # TourVisor API: relax
                "cache_key": "релакс"
            },
            "семейный": {
                "display_name": "семейные отели",
                "api_param": "family",  # TourVisor API: family
                "cache_key": "семейный"
            },
            "оздоровительный": {
                "display_name": "оздоровительные отели",
                "api_param": "health",  # TourVisor API: health
                "cache_key": "оздоровительный"
            },
            "городской": {
                "display_name": "городские отели",
                "api_param": "city",  # TourVisor API: city
                "cache_key": "городской"
            },
            "пляжный": {
                "display_name": "пляжные отели",
                "api_param": "beach",  # TourVisor API: beach
                "cache_key": "пляжный"
            },
            "делюкс": {
                "display_name": "делюкс отели",
                "api_param": "deluxe",  # TourVisor API: deluxe
                "cache_key": "делюкс"
            }
        }
        
        # Состояние
        self.is_running = False
        self.last_update = None
        self.update_stats = {}
        self.current_hotel_type = None
        
        logger.info(f"🎲 Инициализация обновления случайных туров: интервал {self.update_interval//3600}ч, "
                   f"{self.tours_per_type} туров на тип, типы отелей: {list(self.hotel_types_mapping.keys())}")
    
    async def start_scheduler(self):
        """Запуск планировщика автообновления случайных туров"""
        if self.is_running:
            logger.warning("⚠️ Планировщик случайных туров уже запущен")
            return
            
        self.is_running = True
        logger.info(f"🎲 Запуск планировщика обновления случайных туров (интервал: {self.update_interval//3600}ч)")
        
        # Автостарт - запускаем первое обновление
        auto_start = os.getenv("RANDOM_TOURS_AUTO_START", "true").lower() == "true"
        if auto_start:
            logger.info("🚀 Автостарт включен - запуск первого обновления случайных туров")
            try:
                await self._run_update_cycle()
            except Exception as e:
                logger.error(f"❌ Ошибка в автостарте случайных туров: {e}")
        
        while self.is_running:
            try:
                await asyncio.sleep(self.update_interval)
                
                if self.is_running:  # Проверяем снова после ожидания
                    await self._run_update_cycle()
                
            except asyncio.CancelledError:
                logger.info("🛑 Планировщик обновления случайных туров остановлен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в планировщике случайных туров: {e}")
                logger.error(traceback.format_exc())
                # Ждем 1 час перед повтором при ошибке
                await asyncio.sleep(3600)
    
    async def stop_scheduler(self):
        """Остановка планировщика"""
        logger.info("🛑 Остановка планировщика обновления случайных туров")
        self.is_running = False
    
    async def _run_update_cycle(self):
        """Выполнение одного цикла обновления случайных туров"""
        start_time = datetime.now()
        logger.info(f"🎲 НАЧАЛО ЦИКЛА ОБНОВЛЕНИЯ СЛУЧАЙНЫХ ТУРОВ ({start_time.strftime('%Y-%m-%d %H:%M:%S')})")
        
        try:
            # Определяем типы отелей для обновления
            hotel_types = list(self.hotel_types_mapping.keys())
            
            # Статистика обновления
            update_stats = {
                "start_time": start_time,
                "total_hotel_types": len(hotel_types),
                "tours_per_type": self.tours_per_type,
                "processed_types": 0,
                "successful_types": 0,
                "failed_types": 0,
                "total_tours_generated": 0,
                "strategies_used": {},
                "hotel_types_details": {},
                "api_calls_made": 0,
                "real_api_tours": 0,
                "mock_tours": 0
            }
            
            # Обновляем туры для каждого типа отеля
            for hotel_type_key in hotel_types:
                try:
                    hotel_type_info = self.hotel_types_mapping[hotel_type_key]
                    display_name = hotel_type_info["display_name"]
                    
                    logger.info(f"🏨 Обновление туров для типа: {display_name}")
                    self.current_hotel_type = display_name
                    
                    # Генерируем туры для данного типа
                    result = await self._update_tours_for_hotel_type(hotel_type_key, hotel_type_info)
                    
                    update_stats["processed_types"] += 1
                    update_stats["api_calls_made"] += result.get("api_calls_made", 0)
                    
                    if result["success"]:
                        update_stats["successful_types"] += 1
                        update_stats["total_tours_generated"] += result["tours_count"]
                        update_stats["real_api_tours"] += result.get("real_tours", 0)
                        update_stats["mock_tours"] += result.get("mock_tours", 0)
                        
                        # Статистика по стратегиям
                        for strategy, count in result.get("strategies_used", {}).items():
                            update_stats["strategies_used"][strategy] = update_stats["strategies_used"].get(strategy, 0) + count
                    else:
                        update_stats["failed_types"] += 1
                    
                    update_stats["hotel_types_details"][display_name] = result
                    
                    logger.info(f"✅ {display_name}: {result['tours_count']} туров за {result['execution_time_seconds']:.1f}с "
                              f"(реальных: {result.get('real_tours', 0)}, mock: {result.get('mock_tours', 0)})")
                    
                    # Пауза между типами отелей
                    await asyncio.sleep(5)
                    
                except Exception as e:
                    update_stats["processed_types"] += 1
                    update_stats["failed_types"] += 1
                    update_stats["hotel_types_details"][hotel_type_info["display_name"]] = {
                        "success": False,
                        "error": str(e),
                        "tours_count": 0,
                        "execution_time_seconds": 0,
                        "real_tours": 0,
                        "mock_tours": 0
                    }
                    logger.error(f"❌ Ошибка обновления туров для {hotel_type_info['display_name']}: {e}")
            
            # Завершение цикла
            end_time = datetime.now()
            execution_time = end_time - start_time
            
            update_stats["end_time"] = end_time
            update_stats["execution_time_seconds"] = execution_time.total_seconds()
            update_stats["success_rate"] = (update_stats["successful_types"] / len(hotel_types) * 100) if hotel_types else 0
            update_stats["real_tours_percentage"] = (update_stats["real_api_tours"] / update_stats["total_tours_generated"] * 100) if update_stats["total_tours_generated"] > 0 else 0
            
            self.last_update = end_time
            self.update_stats = update_stats
            self.current_hotel_type = None
            
            # Сохраняем статистику в кэш
            await cache_service.set("random_tours_cache_update_stats", update_stats, ttl=48*3600)
            
            logger.info(f"🏁 ЦИКЛ ОБНОВЛЕНИЯ СЛУЧАЙНЫХ ТУРОВ ЗАВЕРШЕН")
            logger.info(f"📊 Итого: {update_stats['successful_types']}/{len(hotel_types)} типов отелей, "
                       f"{update_stats['total_tours_generated']} туров, "
                       f"время: {execution_time.total_seconds():.1f} сек, "
                       f"успешность: {update_stats['success_rate']:.1f}%, "
                       f"реальные туры: {update_stats['real_tours_percentage']:.1f}%")
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в цикле обновления случайных туров: {e}")
            logger.error(traceback.format_exc())
            raise
    
    async def _update_tours_for_hotel_type(self, hotel_type_key: str, hotel_type_info: Dict) -> Dict[str, Any]:
        """Обновление туров для конкретного типа отеля с использованием API фильтрации"""
        start_time = datetime.now()
        
        try:
            display_name = hotel_type_info["display_name"]
            api_param = hotel_type_info["api_param"]
            cache_key_suffix = hotel_type_info["cache_key"]
            
            logger.debug(f"🎲 Генерация {self.tours_per_type} туров для типа: {display_name} (API: {api_param})")
            
            # Очищаем старый кэш для этого типа отеля
            cache_key = f"random_tours_{cache_key_suffix.replace(' ', '_')}"
            await cache_service.delete(cache_key)
            
            # Генерируем туры через улучшенную логику с API фильтрацией
            tours_result, api_calls_made = await self._generate_tours_with_api_filter(
                hotel_type_key, api_param, display_name
            )
            
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            if tours_result and len(tours_result) > 0:
                # Анализируем качество результатов
                strategies_used = {}
                real_tours = 0
                mock_tours = 0
                
                for tour in tours_result:
                    strategy = tour.get("generation_strategy", "unknown")
                    strategies_used[strategy] = strategies_used.get(strategy, 0) + 1
                    
                    if strategy in ["search", "hot_tours"]:
                        real_tours += 1
                    else:
                        mock_tours += 1
                
                # Сохраняем в кэш
                await cache_service.set(cache_key, tours_result, ttl=self.update_interval + 3600)  # TTL = интервал + 1 час
                
                result = {
                    "success": True,
                    "tours_count": len(tours_result),
                    "execution_time_seconds": execution_time,
                    "real_tours": real_tours,
                    "mock_tours": mock_tours,
                    "api_calls_made": api_calls_made,
                    "quality_stats": {
                        "real_tours": real_tours,
                        "mock_tours": mock_tours,
                        "real_tours_percentage": f"{(real_tours/len(tours_result)*100):.1f}%"
                    },
                    "strategies_used": strategies_used,
                    "hotel_type_api_param": api_param
                }
                
                logger.debug(f"✅ Сгенерировано {len(tours_result)} туров для {display_name}: "
                           f"{real_tours} реальных, {mock_tours} mock, API вызовов: {api_calls_made}")
                
                return result
            else:
                return {
                    "success": False,
                    "error": "Не удалось сгенерировать туры",
                    "tours_count": 0,
                    "execution_time_seconds": execution_time,
                    "real_tours": 0,
                    "mock_tours": 0,
                    "api_calls_made": api_calls_made
                }
            
        except Exception as e:
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            logger.error(f"❌ Ошибка генерации туров для {hotel_type_info['display_name']}: {e}")
            
            return {
                "success": False,
                "error": str(e),
                "tours_count": 0,
                "execution_time_seconds": execution_time,
                "real_tours": 0,
                "mock_tours": 0,
                "api_calls_made": 0
            }
    
    async def _generate_tours_with_api_filter(self, hotel_type_key: str, api_param: Optional[str], display_name: str) -> tuple[List[Dict], int]:
        """
        Генерация туров с использованием API фильтрации по типам отелей
        
        Args:
            hotel_type_key: Ключ типа отеля для внутреннего использования
            api_param: Параметр для API TourVisor (hoteltypes)
            display_name: Отображаемое название типа отеля
            
        Returns:
            tuple: (список туров, количество API вызовов)
        """
        try:
            from app.core.tourvisor_client import tourvisor_client
            from datetime import datetime, timedelta
            
            tours_generated = []
            api_calls_made = 0
            
            # Стратегия 1: Попробуем поиск с фильтрацией по типу отеля
            if api_param and "search" in self.generation_strategies:
                logger.debug(f"🔍 Стратегия поиска с фильтром hoteltypes={api_param}")
                
                try:
                    # Случайная страна из списка
                    country_id = random.choice([int(c) for c in self.countries_to_update])
                    
                    # Даты поиска: завтра + неделя
                    tomorrow = datetime.now() + timedelta(days=1)
                    week_later = datetime.now() + timedelta(days=8)
                    
                    # Параметры поиска с фильтром по типу отеля
                    search_params = {
                        "departure": 1,  # Москва
                        "country": country_id,
                        "datefrom": tomorrow.strftime("%d.%m.%Y"),
                        "dateto": week_later.strftime("%d.%m.%Y"),
                        "nightsfrom": 7,
                        "nightsto": 10,
                        "adults": 2,
                        "hoteltypes": api_param,  # КЛЮЧЕВОЙ ПАРАМЕТР - фильтр по типу отеля
                        "format": "json"
                    }
                    
                    # Запускаем поиск
                    request_id = await tourvisor_client.search_tours(search_params)
                    api_calls_made += 1
                    
                    if request_id:
                        logger.debug(f"🚀 Запущен поиск {request_id} для {display_name}")
                        
                        # Ждем результат поиска (ограниченное время)
                        max_wait_time = 30  # 30 секунд максимум
                        start_wait = datetime.now()
                        
                        while (datetime.now() - start_wait).total_seconds() < max_wait_time:
                            try:
                                status_result = await tourvisor_client.get_search_status(request_id)
                                api_calls_made += 1
                                
                                if status_result:
                                    status_data = status_result.get("data", {}).get("status", {})
                                    state = status_data.get("state", "")
                                    hotels_found = status_data.get("hotelsfound", 0)
                                    
                                    if state == "finished" and hotels_found > 0:
                                        # Получаем результаты
                                        search_results = await tourvisor_client.get_search_results(request_id)
                                        api_calls_made += 1
                                        
                                        if search_results:
                                            tours_from_search = await self._extract_tours_from_search_results(
                                                search_results, self.tours_per_type, display_name
                                            )
                                            tours_generated.extend(tours_from_search)
                                            logger.info(f"✅ Поиск {display_name}: получено {len(tours_from_search)} туров через API")
                                        break
                                    elif state == "finished":
                                        logger.warning(f"⚠️ Поиск {display_name} завершен, но отелей не найдено")
                                        break
                                    elif state == "error":
                                        logger.warning(f"❌ Ошибка поиска для {display_name}")
                                        break
                                
                                await asyncio.sleep(2)  # Ждем 2 секунды перед следующей проверкой
                                
                            except Exception as e:
                                logger.debug(f"⚠️ Ошибка проверки статуса для {display_name}: {e}")
                                await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка поиска с фильтром для {display_name}: {e}")
            
            # Стратегия 2: Горящие туры (если не хватает туров)
            if len(tours_generated) < self.tours_per_type and "hot_tours" in self.generation_strategies:
                logger.debug(f"🔥 Стратегия горящих туров для {display_name}")
                
                try:
                    # Попробуем получить горящие туры (без фильтра по типу отеля, так как в горящих турах этого фильтра нет)
                    country_id = random.choice([int(c) for c in self.countries_to_update])
                    
                    hot_tours_params = {
                        "city": 1,  # Москва
                        "items": min(20, self.tours_per_type * 2),  # Запрашиваем больше для фильтрации
                        "countries": str(country_id),
                        "format": "json"
                    }
                    
                    hot_tours_data = await tourvisor_client.get_hot_tours(hot_tours_params)
                    api_calls_made += 1
                    
                    if hot_tours_data and "data" in hot_tours_data:
                        tours_from_hot = await self._extract_tours_from_hot_tours(
                            hot_tours_data, self.tours_per_type - len(tours_generated), display_name
                        )
                        tours_generated.extend(tours_from_hot)
                        logger.info(f"🔥 Горящие туры {display_name}: получено {len(tours_from_hot)} туров")
                
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка получения горящих туров для {display_name}: {e}")
            
            # Стратегия 3: Mock туры (если все еще не хватает)
            if len(tours_generated) < self.tours_per_type and "mock" in self.generation_strategies:
                needed = self.tours_per_type - len(tours_generated)
                logger.debug(f"🎭 Стратегия mock туров для {display_name}: нужно {needed}")
                
                mock_tours = await self._generate_mock_tours(needed, hotel_type_key, display_name)
                tours_generated.extend(mock_tours)
                logger.info(f"🎭 Mock туры {display_name}: сгенерировано {len(mock_tours)} туров")
            
            # Ограничиваем до нужного количества
            tours_generated = tours_generated[:self.tours_per_type]
            
            logger.info(f"📊 Итого для {display_name}: {len(tours_generated)} туров, API вызовов: {api_calls_made}")
            return tours_generated, api_calls_made
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка генерации для {display_name}: {e}")
            return [], api_calls_made
    
    async def _extract_tours_from_search_results(self, search_results: Dict, limit: int, hotel_type: str) -> List[Dict]:
        """Извлечение туров из результатов поиска"""
        try:
            tours = []
            result_data = search_results.get("data", {}).get("result", {})
            hotels = result_data.get("hotel", [])
            
            if not isinstance(hotels, list):
                hotels = [hotels] if hotels else []
            
            for hotel in hotels[:limit]:  # Ограничиваем количество отелей
                hotel_tours = hotel.get("tours", {}).get("tour", [])
                if not isinstance(hotel_tours, list):
                    hotel_tours = [hotel_tours] if hotel_tours else []
                
                # Берем первый тур из отеля
                if hotel_tours:
                    tour = hotel_tours[0]
                    
                    tour_data = {
                        "hotel_name": hotel.get("hotelname", ""),
                        "hotel_stars": hotel.get("hotelstars", 0),
                        "hotel_rating": hotel.get("hotelrating", 0),
                        "country_name": hotel.get("countryname", ""),
                        "region_name": hotel.get("regionname", ""),
                        "price": tour.get("price", 0),
                        "nights": tour.get("nights", 7),
                        "operator_name": tour.get("operatorname", ""),
                        "fly_date": tour.get("flydate", ""),
                        "meal": tour.get("mealrussian", tour.get("meal", "")),
                        "placement": tour.get("placement", ""),
                        "tour_name": tour.get("tourname", ""),
                        "currency": tour.get("currency", "RUB"),
                        "adults": tour.get("adults", 2),
                        "children": tour.get("child", 0),
                        "generation_strategy": "search",
                        "hotel_type": hotel_type,
                        "picture_link": hotel.get("picturelink", ""),
                        "search_source": "api_search_with_filter"
                    }
                    
                    tours.append(tour_data)
                    
                    if len(tours) >= limit:
                        break
            
            return tours
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения туров из поиска для {hotel_type}: {e}")
            return []
    
    async def _extract_tours_from_hot_tours(self, hot_tours_data: Dict, limit: int, hotel_type: str) -> List[Dict]:
        """Извлечение туров из горящих туров"""
        try:
            tours = []
            tours_data = hot_tours_data.get("data", [])
            
            for tour_item in tours_data[:limit]:
                tour_data = {
                    "hotel_name": tour_item.get("hotelname", ""),
                    "hotel_stars": tour_item.get("stars", 0),
                    "hotel_rating": tour_item.get("rating", 0),
                    "country_name": tour_item.get("countryname", ""),
                    "region_name": tour_item.get("regionname", ""),
                    "price": tour_item.get("price", 0),
                    "nights": tour_item.get("nights", 7),
                    "operator_name": tour_item.get("operatorname", ""),
                    "fly_date": tour_item.get("dateto", ""),
                    "meal": tour_item.get("meal", ""),
                    "placement": tour_item.get("placement", ""),
                    "tour_name": tour_item.get("tourname", ""),
                    "currency": "RUB",
                    "adults": 2,
                    "children": 0,
                    "generation_strategy": "hot_tours",
                    "hotel_type": hotel_type,
                    "picture_link": tour_item.get("picture", ""),
                    "search_source": "hot_tours"
                }
                
                tours.append(tour_data)
            
            return tours
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения горящих туров для {hotel_type}: {e}")
            return []
    
    async def _generate_mock_tours(self, count: int, hotel_type_key: str, hotel_type_display: str) -> List[Dict]:
        """Генерация mock туров для типа отеля"""
        try:
            tours = []
            
            # Данные для генерации mock туров в зависимости от типа отеля
            mock_data_by_type = {
                "любой": {
                    "hotels": ["Sunset Resort", "Ocean View Hotel", "Paradise Beach", "Golden Sands"],
                    "price_range": (25000, 80000),
                    "regions": ["Хургада", "Анталья", "Пхукет", "Дубай"]
                },
                "активный": {
                    "hotels": ["Adventure Resort", "Active Sports Hotel", "Mountain View Resort", "Extreme Hotel"],
                    "price_range": (30000, 90000),
                    "regions": ["Анталья", "Красная Поляна", "Буковель", "Альпы"]
                },
                "релакс": {
                    "hotels": ["Spa Resort", "Wellness Hotel", "Zen Garden Resort", "Tranquil Waters"],
                    "price_range": (40000, 120000),
                    "regions": ["Карловы Вары", "Баден-Баден", "Мариенбад", "Термальные источники"]
                },
                "семейный": {
                    "hotels": ["Family Resort", "Kids Club Hotel", "Happy Family Resort", "Children Paradise"],
                    "price_range": (35000, 95000),
                    "regions": ["Анталья", "Крит", "Кипр", "Болгария"]
                },
                "оздоровительный": {
                    "hotels": ["Health Resort", "Medical Spa", "Healing Waters Resort", "Wellness Center"],
                    "price_range": (50000, 150000),
                    "regions": ["Карловы Вары", "Железноводск", "Ессентуки", "Кисловодск"]
                },
                "городской": {
                    "hotels": ["City Hotel", "Metropolitan Resort", "Urban Oasis", "Downtown Hotel"],
                    "price_range": (20000, 70000),
                    "regions": ["Стамбул", "Дубай", "Бангкок", "Сингапур"]
                },
                "пляжный": {
                    "hotels": ["Beach Resort", "Seaside Hotel", "Ocean Paradise", "Tropical Beach"],
                    "price_range": (30000, 100000),
                    "regions": ["Хургада", "Пхукет", "Мальдивы", "Бали"]
                },
                "делюкс": {
                    "hotels": ["Luxury Resort", "Premium Hotel", "Elite Resort", "VIP Paradise"],
                    "price_range": (80000, 250000),
                    "regions": ["Мальдивы", "Сейшелы", "Сент-Барт", "Монако"]
                }
            }
            
            mock_config = mock_data_by_type.get(hotel_type_key, mock_data_by_type["любой"])
            
            for i in range(count):
                # Случайные данные на основе типа отеля
                hotel_name = random.choice(mock_config["hotels"])
                price = random.randint(mock_config["price_range"][0], mock_config["price_range"][1])
                region = random.choice(mock_config["regions"])
                nights = random.choice([7, 10, 14])
                stars = random.choice([3, 4, 5])
                
                tour_data = {
                    "hotel_name": f"{hotel_name} {i+1}",
                    "hotel_stars": stars,
                    "hotel_rating": round(random.uniform(3.0, 5.0), 1),
                    "country_name": "Различные страны",
                    "region_name": region,
                    "price": price,
                    "nights": nights,
                    "operator_name": random.choice(["Sunmar", "Coral Travel", "Pegas", "TUI"]),
                    "fly_date": (datetime.now() + timedelta(days=random.randint(7, 30))).strftime("%d.%m.%Y"),
                    "meal": random.choice(["Завтрак", "Полупансион", "Полный пансион", "Все включено"]),
                    "placement": "DBL",
                    "tour_name": f"Тур в {region}",
                    "currency": "RUB",
                    "adults": 2,
                    "children": 0,
                    "generation_strategy": "mock",
                    "hotel_type": hotel_type_display,
                    "picture_link": f"/static/mockup_images/hotel_{hotel_type_key}_{i+1}.jpg",
                    "search_source": "mock_generation",
                    "mock_type": hotel_type_key
                }
                
                tours.append(tour_data)
            
            return tours
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации mock туров для {hotel_type_display}: {e}")
            return []
    
    # Остальные методы остаются без изменений...
    async def force_update_now(self) -> Dict[str, Any]:
        """Принудительное обновление сейчас (для API)"""
        logger.info("🚀 Принудительное обновление случайных туров")
        
        try:
            await self._run_update_cycle()
            return {
                "success": True,
                "message": "Принудительное обновление случайных туров завершено успешно",
                "stats": self.update_stats
            }
        except Exception as e:
            logger.error(f"❌ Ошибка принудительного обновления случайных туров: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Ошибка при принудительном обновлении случайных туров"
            }
    
    async def get_update_status(self) -> Dict[str, Any]:
        """Получение статуса обновления (для API)"""
        try:
            # Пытаемся получить статистику из кэша
            cached_stats = await cache_service.get("random_tours_cache_update_stats")
            
            if cached_stats:
                # Дополняем актуальной информацией
                status = {
                    "is_running": self.is_running,
                    "last_update": cached_stats.get("end_time"),
                    "next_update": None,
                    "current_hotel_type": self.current_hotel_type,
                    "update_stats": cached_stats,
                    "hotel_types_supported": list(self.hotel_types_mapping.keys()),
                    "api_integration": {
                        "uses_hoteltypes_filter": True,
                        "supported_api_params": [info["api_param"] for info in self.hotel_types_mapping.values() if info["api_param"]]
                    }
                }
                
                # Вычисляем время следующего обновления
                if self.last_update:
                    next_update = self.last_update + timedelta(seconds=self.update_interval)
                    status["next_update"] = next_update
                    status["time_until_next_update_hours"] = max(0, (next_update - datetime.now()).total_seconds() / 3600)
                
                return status
            else:
                return {
                    "is_running": self.is_running,
                    "last_update": self.last_update,
                    "next_update": None,
                    "current_hotel_type": self.current_hotel_type,
                    "update_stats": None,
                    "message": "Еще не было обновлений случайных туров",
                    "hotel_types_supported": list(self.hotel_types_mapping.keys())
                }
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса случайных туров: {e}")
            return {
                "error": str(e),
                "is_running": self.is_running
            }
    
    async def clear_all_cache(self) -> Dict[str, Any]:
        """Очистка всего кэша случайных туров"""
        try:
            logger.info("🗑️ Очистка кэша случайных туров")
            
            hotel_types = list(self.hotel_types_mapping.keys())
            cleared_count = 0
            
            for hotel_type_key in hotel_types:
                cache_key_suffix = self.hotel_types_mapping[hotel_type_key]["cache_key"]
                cache_key = f"random_tours_{cache_key_suffix.replace(' ', '_')}"
                try:
                    await cache_service.delete(cache_key)
                    cleared_count += 1
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось очистить ключ {cache_key}: {e}")
            
            # Также очищаем общий кэш случайных туров
            general_keys = ["random_tours", "random_tours_stats", "random_tours_cache_update_stats"]
            for key in general_keys:
                try:
                    await cache_service.delete(key)
                    cleared_count += 1
                except:
                    pass
            
            return {
                "success": True,
                "message": f"Очищено {cleared_count} ключей кэша случайных туров",
                "cleared_keys": cleared_count,
                "cleared_hotel_types": hotel_types
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки кэша случайных туров: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_cache_health(self) -> Dict[str, Any]:
        """Проверка здоровья кэша случайных туров"""
        try:
            hotel_types = list(self.hotel_types_mapping.keys())
            cached_types = 0
            total_tours = 0
            
            cache_details = {}
            
            for hotel_type_key in hotel_types:
                hotel_type_info = self.hotel_types_mapping[hotel_type_key]
                display_name = hotel_type_info["display_name"]
                cache_key_suffix = hotel_type_info["cache_key"]
                cache_key = f"random_tours_{cache_key_suffix.replace(' ', '_')}"
                
                try:
                    cached_tours = await cache_service.get(cache_key)
                    if cached_tours:
                        cached_types += 1
                        total_tours += len(cached_tours)
                        
                        # Анализ качества
                        real_tours = len([t for t in cached_tours if t.get("generation_strategy") in ["search", "hot_tours"]])
                        
                        cache_details[display_name] = {
                            "cached": True,
                            "tours_count": len(cached_tours),
                            "real_tours": real_tours,
                            "quality": f"{(real_tours/len(cached_tours)*100):.1f}%" if cached_tours else "0%",
                            "api_param": hotel_type_info["api_param"],
                            "cache_key": cache_key
                        }
                    else:
                        cache_details[display_name] = {
                            "cached": False,
                            "tours_count": 0,
                            "api_param": hotel_type_info["api_param"],
                            "cache_key": cache_key
                        }
                except Exception as e:
                    cache_details[display_name] = {
                        "cached": False,
                        "error": str(e),
                        "api_param": hotel_type_info["api_param"]
                    }
            
            # Определяем состояние здоровья
            coverage = (cached_types / len(hotel_types)) * 100
            
            if coverage >= 80:
                health_status = "good"
            elif coverage >= 50:
                health_status = "warning"
            else:
                health_status = "poor"
            
            return {
                "health_status": health_status,
                "coverage_percentage": f"{coverage:.1f}%",
                "cached_hotel_types": cached_types,
                "total_hotel_types": len(hotel_types),
                "total_tours_cached": total_tours,
                "cache_details": cache_details,
                "api_integration": {
                    "hoteltypes_filter_enabled": True,
                    "supported_api_filters": [info["api_param"] for info in self.hotel_types_mapping.values() if info["api_param"]]
                },
                "recommendations": [
                    "Запустите обновление: POST /api/v1/random-tours/cache/force-update" if coverage < 80 else None,
                    "Проверьте планировщик: GET /api/v1/random-tours/cache/status" if not self.is_running else None
                ]
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки здоровья кэша случайных туров: {e}")
            return {
                "health_status": "error",
                "error": str(e)
            }
    
    def get_supported_hotel_types(self) -> Dict[str, Any]:
        """Получение списка поддерживаемых типов отелей"""
        return {
            "hotel_types": {
                key: {
                    "display_name": info["display_name"],
                    "api_param": info["api_param"],
                    "cache_key": info["cache_key"]
                }
                for key, info in self.hotel_types_mapping.items()
            },
            "api_integration": {
                "tourvisor_hoteltypes_field": "hoteltypes",
                "supported_values": [info["api_param"] for info in self.hotel_types_mapping.values() if info["api_param"]],
                "documentation": "https://tourvisor.ru/xml/ - поле hoteltypes в поисковых запросах"
            }
        }

# Создаем единственный экземпляр сервиса
random_tours_cache_update_service = RandomToursCacheUpdateService()

# Функции для интеграции
async def start_random_tours_cache_update_task():
    """Запуск задачи обновления кэша случайных туров в фоне"""
    logger.info("🎲 Запуск фоновой задачи обновления кэша случайных туров")
    await random_tours_cache_update_service.start_scheduler()

async def stop_random_tours_cache_update_task():
    """Остановка задачи обновления кэша случайных туров"""
    await random_tours_cache_update_service.stop_scheduler()