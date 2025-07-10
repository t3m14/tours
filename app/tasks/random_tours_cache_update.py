# app/tasks/random_tours_cache_update.py - ОПТИМИЗИРОВАННАЯ ВЕРСИЯ

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import traceback
import random

from app.services.random_tours_service import random_tours_service
from app.services.cache_service import cache_service
from app.models.tour import RandomTourRequest
from app.utils.logger import setup_logger
import os

logger = setup_logger(__name__)

class RandomToursCacheUpdateService:
    """Сервис для автоматического обновления кэша случайных туров"""
    
    def __init__(self):
        self.update_interval = int(os.getenv("RANDOM_TOURS_UPDATE_INTERVAL_HOURS", "12")) * 3600
        self.tours_per_type = int(os.getenv("RANDOM_TOURS_PER_TYPE", "8"))
        self.generation_strategies = os.getenv("RANDOM_TOURS_STRATEGIES", "search,hot_tours,mock").split(",")
        self.countries_to_update = os.getenv("RANDOM_TOURS_COUNTRIES", "1,2,4,9,8").split(",")
        
        # Маппинг типов отелей
        self.hotel_types_mapping = {
            "any": {"display_name": "any", "api_param": None, "cache_key": "any"},
            "active": {"display_name": "active", "api_param": "active", "cache_key": "active"},
            "relax": {"display_name": "relax", "api_param": "relax", "cache_key": "relax"},
            "family": {"display_name": "family", "api_param": "family", "cache_key": "family"},
            "health": {"display_name": "health", "api_param": "health", "cache_key": "health"},
            "city": {"display_name": "city", "api_param": "city", "cache_key": "city"},
            "beach": {"display_name": "beach", "api_param": "beach", "cache_key": "beach"},
            "deluxe": {"display_name": "deluxe", "api_param": "deluxe", "cache_key": "deluxe"}
        }

        self.is_running = False
        self.last_update = None
        self.update_stats = {}
        self.current_hotel_type = None
        
        logger.info(f"🎲 Инициализация обновления случайных туров: интервал {self.update_interval//3600}ч, "
                   f"{self.tours_per_type} туров на тип")
    
    async def start_scheduler(self):
        """Запуск планировщика автообновления случайных туров"""
        if self.is_running:
            logger.warning("⚠️ Планировщик случайных туров уже запущен")
            return
            
        self.is_running = True
        logger.info(f"🎲 Запуск планировщика обновления случайных туров")
        
        # Автостарт
        auto_start = os.getenv("RANDOM_TOURS_AUTO_START", "true").lower() == "true"
        if auto_start:
            logger.info("🚀 Автостарт включен - запуск первого обновления")
            try:
                await self._run_update_cycle()
            except Exception as e:
                logger.error(f"❌ Ошибка в автостарте: {e}")
        
        while self.is_running:
            try:
                await asyncio.sleep(self.update_interval)
                if self.is_running:
                    await self._run_update_cycle()
                
            except asyncio.CancelledError:
                logger.info("🛑 Планировщик остановлен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в планировщике: {e}")
                await asyncio.sleep(3600)
    
    async def stop_scheduler(self):
        """Остановка планировщика"""
        logger.info("🛑 Остановка планировщика")
        self.is_running = False
    
    async def _run_update_cycle(self):
        """Выполнение одного цикла обновления"""
        start_time = datetime.now()
        logger.info(f"🎲 НАЧАЛО ЦИКЛА ОБНОВЛЕНИЯ ({start_time.strftime('%Y-%m-%d %H:%M:%S')})")
        
        try:
            hotel_types = list(self.hotel_types_mapping.keys())
            
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
                    
                    result = await self._update_tours_for_hotel_type(hotel_type_key, hotel_type_info)
                    
                    update_stats["processed_types"] += 1
                    update_stats["api_calls_made"] += result.get("api_calls_made", 0)
                    
                    if result["success"]:
                        update_stats["successful_types"] += 1
                        update_stats["total_tours_generated"] += result["tours_count"]
                        update_stats["real_api_tours"] += result.get("real_tours", 0)
                        update_stats["mock_tours"] += result.get("mock_tours", 0)
                        
                        for strategy, count in result.get("strategies_used", {}).items():
                            update_stats["strategies_used"][strategy] = update_stats["strategies_used"].get(strategy, 0) + count
                    else:
                        update_stats["failed_types"] += 1
                    
                    update_stats["hotel_types_details"][display_name] = result
                    
                    logger.info(f"✅ {display_name}: {result['tours_count']} туров за {result['execution_time_seconds']:.1f}с")
                    
                    await asyncio.sleep(5)
                    
                except Exception as e:
                    update_stats["processed_types"] += 1
                    update_stats["failed_types"] += 1
                    update_stats["hotel_types_details"][hotel_type_info["display_name"]] = {
                        "success": False,
                        "error": str(e),
                        "tours_count": 0,
                        "execution_time_seconds": 0
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
            
            await cache_service.set("random_tours_cache_update_stats", update_stats, ttl=48*3600)
            
            logger.info(f"🏁 ЦИКЛ ЗАВЕРШЕН: {update_stats['successful_types']}/{len(hotel_types)} типов, "
                       f"{update_stats['total_tours_generated']} туров, "
                       f"время: {execution_time.total_seconds():.1f} сек")
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в цикле: {e}")
            logger.error(traceback.format_exc())
            raise
    
    async def _update_tours_for_hotel_type(self, hotel_type_key: str, hotel_type_info: Dict) -> Dict[str, Any]:
        """Обновление туров для конкретного типа отеля"""
        start_time = datetime.now()
        
        try:
            display_name = hotel_type_info["display_name"]
            api_param = hotel_type_info["api_param"]
            cache_key_suffix = hotel_type_info["cache_key"]
            
            logger.debug(f"🎲 Генерация {self.tours_per_type} туров для типа: {display_name}")
            
            # Очищаем старый кэш
            cache_key = f"random_tours_{cache_key_suffix}"
            await cache_service.delete(cache_key)
            
            # Генерируем туры
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
                
                # Добавляем поля hoteldescriptions и tours
                for tour in tours_result:
                    await self._enrich_tour_with_details(tour)
                
                # Сохраняем в кэш
                await cache_service.set(cache_key, tours_result, ttl=self.update_interval + 3600)
                
                result = {
                    "success": True,
                    "tours_count": len(tours_result),
                    "execution_time_seconds": execution_time,
                    "real_tours": real_tours,
                    "mock_tours": mock_tours,
                    "api_calls_made": api_calls_made,
                    "strategies_used": strategies_used,
                    "hotel_type_api_param": api_param
                }
                
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
        """Генерация туров с использованием API фильтрации по типам отелей"""
        try:
            from app.core.tourvisor_client import tourvisor_client
            
            tours_generated = []
            api_calls_made = 0
            
            # СТРАТЕГИЯ 1: Поиск через API
            if "search" in self.generation_strategies:
                logger.debug(f"🔍 Стратегия поиска для {display_name}")
                
                try:
                    country_id = random.choice([int(c) for c in self.countries_to_update])
                    tomorrow = datetime.now() + timedelta(days=1)
                    week_later = datetime.now() + timedelta(days=8)
                    
                    search_params = {
                        "departure": random.choice([1, 2, 3, 4, 5]),
                        "country": country_id,
                        "datefrom": tomorrow.strftime("%d.%m.%Y"),
                        "dateto": week_later.strftime("%d.%m.%Y"),
                        "nightsfrom": 7,
                        "nightsto": 10,
                        "adults": 2,
                        "format": "json",
                        "onpage": 20
                    }
                    
                    if api_param and hotel_type_key != "any":
                        search_params["hoteltypes"] = api_param
                    
                    request_id = await tourvisor_client.search_tours(search_params)
                    api_calls_made += 1
                    
                    if request_id:
                        # Ждем результатов
                        max_wait_time = 60
                        start_wait = datetime.now()

                        while (datetime.now() - start_wait).total_seconds() < max_wait_time:
                            try:
                                status_result = await tourvisor_client.get_search_status(request_id)
                                api_calls_made += 1
                                
                                if status_result:
                                    status_data = status_result.get("data", {}).get("status", {})
                                    state = status_data.get("state", "")
                                    hotels_found = int(status_data.get("hotelsfound", 0))
                                    progress = int(status_data.get("progress", 0))
                                    
                                    if state == "finished" or (hotels_found >= 3 and progress >= 30):
                                        break
                                        
                                    if state == "error":
                                        break
                                
                                await asyncio.sleep(3)
                                
                            except Exception as e:
                                logger.warning(f"⚠️ Ошибка проверки статуса: {e}")
                                await asyncio.sleep(3)
                        
                        # Получаем результаты
                        try:
                            search_results = await tourvisor_client.get_search_results(request_id)
                            api_calls_made += 1
                            
                            if search_results:
                                tours_from_search = await self._extract_tours_from_search_results(
                                    search_results, self.tours_per_type, display_name, search_params
                                )
                                tours_generated.extend(tours_from_search)
                                
                        except Exception as results_error:
                            logger.error(f"❌ Ошибка получения результатов: {results_error}")
                    
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка поиска для {display_name}: {e}")
            
            # СТРАТЕГИЯ 2: Горящие туры
            if len(tours_generated) < self.tours_per_type and "hot_tours" in self.generation_strategies:
                try:
                    country_id = random.choice([int(c) for c in self.countries_to_update])
                    
                    hot_tours_data = await tourvisor_client.get_hot_tours(
                        city=1,
                        items=min(20, self.tours_per_type * 2),
                        countries=str(country_id)
                    )
                    api_calls_made += 1
                    
                    if hot_tours_data and "data" in hot_tours_data:
                        tours_from_hot = await self._extract_tours_from_hot_tours(
                            hot_tours_data, self.tours_per_type - len(tours_generated), display_name
                        )
                        tours_generated.extend(tours_from_hot)
                
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка получения горящих туров: {e}")
            
            # СТРАТЕГИЯ 3: Mock туры
            if len(tours_generated) < self.tours_per_type and "mock" in self.generation_strategies:
                needed = self.tours_per_type - len(tours_generated)
                mock_tours = await self._generate_mock_tours(needed, hotel_type_key, display_name)
                tours_generated.extend(mock_tours)
            
            # Ограничиваем до нужного количества
            tours_generated = tours_generated[:self.tours_per_type]
            
            return tours_generated, api_calls_made
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка генерации для {display_name}: {e}")
            return [], api_calls_made
    
    async def _extract_tours_from_search_results(self, search_results: Dict, limit: int, hotel_type: str, search_params: Dict = None) -> List[Dict]:
        """Извлечение туров из результатов поиска"""
        try:
            tours = []
            
            # Поиск отелей в результатах
            hotels = self._find_hotels_in_results(search_results)
            
            if not hotels:
                logger.warning(f"❌ Отели не найдены в результатах для {hotel_type}")
                return []
            
            # Извлекаем туры из отелей
            for i, hotel in enumerate(hotels[:limit]):
                try:
                    if not isinstance(hotel, dict):
                        continue
                    
                    hotel_tours = self._extract_tours_from_hotel(hotel)
                    
                    if hotel_tours:
                        for tour in hotel_tours:
                            try:
                                tour_data = self._build_tour_data(hotel, tour, hotel_type, search_params)
                                if tour_data:
                                    tours.append(tour_data)
                                    break
                            except Exception as tour_build_error:
                                continue
                    
                    if len(tours) >= limit:
                        break
                        
                except Exception as hotel_error:
                    continue
            
            return tours
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения туров для {hotel_type}: {e}")
            return []
    
    def _find_hotels_in_results(self, search_results: Dict) -> List[Dict]:
        """Поиск отелей в результатах"""
        hotels = []
        
        # Различные пути к отелям
        search_paths = [
            ["data", "result", "hotel"],
            ["data", "hotel"],
            ["hotel"],
            ["result", "hotel"],
            ["data", "result", "hotels"],
            ["data", "hotels"],
            ["hotels"]
        ]
        
        for path in search_paths:
            try:
                current = search_results
                for key in path:
                    if isinstance(current, dict) and key in current:
                        current = current[key]
                    else:
                        break
                else:
                    if current:
                        hotels = current if isinstance(current, list) else [current]
                        break
            except Exception:
                continue
        
        return hotels
    
    def _extract_tours_from_hotel(self, hotel):
        """Извлекает туры из данных отеля"""
        hotel_tours = []
        
        tour_paths = [
            ["tours", "tour"],
            ["tour"],
            ["tours"],
            ["packages"],
            ["offers"]
        ]
        
        for path in tour_paths:
            try:
                current = hotel
                for key in path:
                    if isinstance(current, dict) and key in current:
                        current = current[key]
                    else:
                        break
                else:
                    if current:
                        if isinstance(current, list):
                            hotel_tours.extend(current)
                        else:
                            hotel_tours.append(current)
                        break
            except Exception:
                continue
        
        return hotel_tours
    
    def _build_tour_data(self, hotel, tour, hotel_type, search_params=None):
        """Создает объект тура из данных отеля и тура"""
        try:
            price = tour.get("price", 0)
            if not price or (isinstance(price, (str, int, float)) and float(price) <= 0):
                return None
            
            def safe_get(obj, key, default="", convert_func=str):
                try:
                    value = obj.get(key, default)
                    return convert_func(value) if value not in [None, "", 0] else convert_func(default)
                except:
                    return convert_func(default)
            
            tour_data = {
                "hotel_name": safe_get(hotel, "hotelname"),
                "hotel_stars": safe_get(hotel, "hotelstars", 0, int),
                "hotel_rating": safe_get(hotel, "hotelrating", 0, float),
                "country_name": safe_get(hotel, "countryname"),
                "region_name": safe_get(hotel, "regionname"),
                "departurecode": safe_get(hotel, "departurecode"),
                "countrycode": safe_get(hotel, "countrycode"),
                "price": safe_get(tour, "price", 0, lambda x: int(float(x))),
                "nights": safe_get(tour, "nights", 7, int),
                "operator_name": safe_get(tour, "operatorname"),
                "fly_date": safe_get(tour, "flydate"),
                "meal": safe_get(tour, "mealrussian", safe_get(tour, "meal")),
                "placement": safe_get(tour, "placement"),
                "tour_name": safe_get(tour, "tourname"),
                "currency": safe_get(tour, "currency", "RUB"),
                "adults": safe_get(tour, "adults", 2, int),
                "children": safe_get(tour, "child", 0, int),
                "generation_strategy": "search",
                "hotel_type": hotel_type,
                "picture_link": safe_get(hotel, "picturelink"),
                "search_source": "api_search_with_filter",
                "seadistance": safe_get(hotel, "seadistance", random.choice([50, 100, 150, 200]), int),
                
                # Дополнительные поля для совместимости
                "hotelcode": safe_get(hotel, "hotelcode", ""),
                "fulldesclink": safe_get(hotel, "fulldesclink"),
                "reviewlink": safe_get(hotel, "reviewlink"),
            }
            
            # Валидация
            if not tour_data["hotel_name"] or tour_data["price"] <= 0:
                return None
            
            return tour_data
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка создания тура: {e}")
            return None
    
    async def _extract_tours_from_hot_tours(self, hot_tours_data: Dict, limit: int, hotel_type: str) -> List[Dict]:
        """Извлечение туров из горящих туров"""
        try:
            tours = []
            tours_data = hot_tours_data.get("data", [])
            
            for tour_item in tours_data[:limit]:
                try:
                    tour_data = {
                        "hotel_name": tour_item.get("hotelname", ""),
                        "hotel_stars": int(tour_item.get("stars", 0)),
                        "hotel_rating": float(tour_item.get("rating", 0)),
                        "country_name": tour_item.get("countryname", ""),
                        "region_name": tour_item.get("regionname", ""),
                        "price": int(tour_item.get("price", 0)),
                        "nights": int(tour_item.get("nights", 7)),
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
                        "search_source": "hot_tours",
                        "hotelcode": tour_item.get("hotelcode", ""),
                        "seadistance": random.choice([50, 100, 150, 200, 300])
                    }
                    
                    if tour_data["price"] > 0 and tour_data["hotel_name"]:
                        tours.append(tour_data)
                    
                except Exception as e:
                    continue
            
            return tours
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения горящих туров для {hotel_type}: {e}")
            return []
    
    async def _generate_mock_tours(self, count: int, hotel_type_key: str, hotel_type_display: str) -> List[Dict]:
        """Генерация mock туров для типа отеля"""
        try:
            tours = []
            
            mock_data_by_type = {
                "any": {
                    "hotels": ["Sunset Resort", "Ocean View Hotel", "Paradise Beach", "Golden Sands"],
                    "price_range": (25000, 80000),
                    "regions": ["Хургада", "Анталья", "Пхукет", "Дубай"]
                },
                "active": {
                    "hotels": ["Adventure Resort", "Active Sports Hotel", "Mountain View Resort"],
                    "price_range": (30000, 90000),
                    "regions": ["Анталья", "Красная Поляна", "Буковель"]
                },
                "relax": {
                    "hotels": ["Spa Resort", "Wellness Hotel", "Zen Garden Resort"],
                    "price_range": (40000, 120000),
                    "regions": ["Карловы Вары", "Баден-Баден", "Мариенбад"]
                },
                "family": {
                    "hotels": ["Family Resort", "Kids Club Hotel", "Happy Family Resort"],
                    "price_range": (35000, 95000),
                    "regions": ["Анталья", "Крит", "Кипр"]
                },
                "health": {
                    "hotels": ["Health Resort", "Medical Spa", "Healing Waters Resort"],
                    "price_range": (50000, 150000),
                    "regions": ["Карловы Вары", "Железноводск", "Ессентуки"]
                },
                "city": {
                    "hotels": ["City Hotel", "Metropolitan Resort", "Urban Oasis"],
                    "price_range": (20000, 70000),
                    "regions": ["Стамбул", "Дубай", "Бангкок"]
                },
                "beach": {
                    "hotels": ["Beach Resort", "Seaside Hotel", "Ocean Paradise"],
                    "price_range": (30000, 100000),
                    "regions": ["Хургада", "Пхукет", "Мальдивы"]
                },
                "deluxe": {
                    "hotels": ["Luxury Resort", "Premium Hotel", "Elite Resort"],
                    "price_range": (80000, 250000),
                    "regions": ["Мальдивы", "Сейшелы", "Монако"]
                }
            }

            mock_config = mock_data_by_type.get(hotel_type_key, mock_data_by_type["any"])
            
            for i in range(count):
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
                    "hotelcode": f"MOCK_{hotel_type_key.upper()}_{i+1:03d}",
                    "seadistance": random.choice([50, 100, 150, 200, 300]),
                    "mock_type": hotel_type_key
                }
                
                tours.append(tour_data)
            
            return tours
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации mock туров для {hotel_type_display}: {e}")
            return []
    
    async def _enrich_tour_with_details(self, tour: Dict) -> None:
        """Обогащение тура деталями: hoteldescriptions и tours"""
        try:
            from app.core.tourvisor_client import tourvisor_client
            
            # Получаем код отеля
            hotel_code = tour.get("hotelcode")
            if not hotel_code or hotel_code.startswith("MOCK_"):
                # Для mock туров создаем фиктивные данные
                tour["hoteldescriptions"] = f"Описание отеля {tour.get('hotel_name', 'Unknown Hotel')}"
                tour["tours"] = [{
                    "tour_id": f"mock_tour_{random.randint(1000, 9999)}",
                    "price": tour.get("price", 0),
                    "nights": tour.get("nights", 7),
                    "meal": tour.get("meal", "Завтрак"),
                    "placement": tour.get("placement", "DBL")
                }]
                return
            
            try:
                # Получаем детальную информацию об отеле
                hotel_details = await tourvisor_client.get_hotel_info(hotel_code)
                
                if hotel_details and isinstance(hotel_details, dict):
                    # Извлекаем описание отеля
                    description = (
                        hotel_details.get("hoteldescription", "") or
                        hotel_details.get("description", "") or
                        f"Отель {tour.get('hotel_name', 'Unknown Hotel')}"
                    )
                    tour["hoteldescriptions"] = description
                    
                    # Извлекаем информацию о турах
                    tours_info = []
                    
                    # Основная информация о туре из текущих данных
                    tour_info = {
                        "tour_id": tour.get("tour_id", f"tour_{random.randint(1000, 9999)}"),
                        "price": tour.get("price", 0),
                        "nights": tour.get("nights", 7),
                        "meal": tour.get("meal", "Завтрак"),
                        "placement": tour.get("placement", "DBL"),
                        "operator_name": tour.get("operator_name", ""),
                        "fly_date": tour.get("fly_date", ""),
                        "currency": tour.get("currency", "RUB")
                    }
                    tours_info.append(tour_info)
                    
                    tour["tours"] = tours_info
                else:
                    # Fallback данные
                    tour["hoteldescriptions"] = f"Отель {tour.get('hotel_name', 'Unknown Hotel')}"
                    tour["tours"] = [{
                        "tour_id": f"tour_{random.randint(1000, 9999)}",
                        "price": tour.get("price", 0),
                        "nights": tour.get("nights", 7),
                        "meal": tour.get("meal", "Завтрак"),
                        "placement": tour.get("placement", "DBL")
                    }]
                    
            except Exception as api_error:
                logger.debug(f"Не удалось получить детали отеля {hotel_code}: {api_error}")
                # Fallback данные
                tour["hoteldescriptions"] = f"Отель {tour.get('hotel_name', 'Unknown Hotel')}"
                tour["tours"] = [{
                    "tour_id": f"tour_{random.randint(1000, 9999)}",
                    "price": tour.get("price", 0),
                    "nights": tour.get("nights", 7),
                    "meal": tour.get("meal", "Завтрак"),
                    "placement": tour.get("placement", "DBL")
                }]
                
        except Exception as e:
            logger.debug(f"Ошибка обогащения тура деталями: {e}")
            # Минимальные fallback данные
            tour["hoteldescriptions"] = f"Отель {tour.get('hotel_name', 'Unknown Hotel')}"
            tour["tours"] = [{
                "tour_id": f"tour_{random.randint(1000, 9999)}",
                "price": tour.get("price", 0),
                "nights": tour.get("nights", 7)
            }]
    
    # API методы для управления
    async def force_update_now(self) -> Dict[str, Any]:
        """Принудительное обновление сейчас"""
        logger.info("🚀 Принудительное обновление случайных туров")
        
        try:
            await self._run_update_cycle()
            return {
                "success": True,
                "message": "Принудительное обновление завершено успешно",
                "stats": self.update_stats
            }
        except Exception as e:
            logger.error(f"❌ Ошибка принудительного обновления: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Ошибка при принудительном обновлении"
            }
    
    async def get_update_status(self) -> Dict[str, Any]:
        """Получение статуса обновления"""
        try:
            cached_stats = await cache_service.get("random_tours_cache_update_stats")
            
            if cached_stats:
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
                    "message": "Еще не было обновлений",
                    "hotel_types_supported": list(self.hotel_types_mapping.keys())
                }
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса: {e}")
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
                cache_key = f"random_tours_{cache_key_suffix}"
                try:
                    await cache_service.delete(cache_key)
                    cleared_count += 1
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось очистить ключ {cache_key}: {e}")
            
            # Очищаем общий кэш
            general_keys = ["random_tours", "random_tours_stats", "random_tours_cache_update_stats"]
            for key in general_keys:
                try:
                    await cache_service.delete(key)
                    cleared_count += 1
                except:
                    pass
            
            return {
                "success": True,
                "message": f"Очищено {cleared_count} ключей кэша",
                "cleared_keys": cleared_count,
                "cleared_hotel_types": hotel_types
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка очистки кэша: {e}")
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
                cache_key = f"random_tours_{cache_key_suffix}"
                
                try:
                    cached_tours = await cache_service.get(cache_key)
                    if cached_tours:
                        cached_types += 1
                        total_tours += len(cached_tours)
                        
                        real_tours = len([t for t in cached_tours if t.get("generation_strategy") in ["search", "hot_tours"]])
                        
                        cache_details[display_name] = {
                            "cached": True,
                            "tours_count": len(cached_tours),
                            "real_tours": real_tours,
                            "quality": f"{(real_tours/len(cached_tours)*100):.1f}%" if cached_tours else "0%",
                            "api_param": hotel_type_info["api_param"],
                            "cache_key": cache_key,
                            "has_descriptions": any(t.get("hoteldescriptions") for t in cached_tours),
                            "has_tours_data": any(t.get("tours") for t in cached_tours)
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
                    "supported_api_filters": [info["api_param"] for info in self.hotel_types_mapping.values() if info["api_param"]],
                    "enhanced_with_descriptions": True,
                    "enhanced_with_tours_data": True
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки здоровья кэша: {e}")
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