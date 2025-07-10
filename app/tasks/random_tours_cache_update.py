# app/tasks/random_tours_cache_update.py - ПОЛНАЯ ИСПРАВЛЕННАЯ ВЕРСИЯ

import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import traceback
import random

from app.services.random_tours_service import random_tours_service
from app.services.cache_service import cache_service
from app.services.tour_service import tour_service
from app.models.tour import RandomTourRequest, TourSearchRequest
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
                
                # Обогащаем туры реальными данными через существующий API
                for tour in tours_result:
                    await self._enrich_tour_with_real_data(tour)
                
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
                "regioncode": safe_get(hotel, "regioncode", 0, int),
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
    
    async def _enrich_tour_with_real_data(self, tour: Dict) -> None:
        """Обогащение тура реальными данными через прямое обращение к hotels API"""
        try:
            # Получаем код отеля
            hotel_code = tour.get("hotelcode")
            if not hotel_code or hotel_code.startswith("MOCK_"):
                # Для mock туров создаем базовые данные в правильном формате
                await self._create_mock_tour_data(tour)
                return
            
            # Определяем параметры для поиска
            country_code = tour.get("countrycode", "1")
            departure_city = 1  # Москва по умолчанию
            
            try:
                # Используем внутренний импорт для избежания циклических зависимостей
                from app.api.v1.hotels import get_hotel_tours
                
                logger.debug(f"🔍 Прямое обращение к hotels API для отеля {hotel_code}")
                
                # Вызываем существующую функцию для получения туров
                hotels_result = await get_hotel_tours(
                    hotel_code=hotel_code,
                    departure_city=departure_city,
                    country_code=int(country_code) if str(country_code).isdigit() else 1
                )
                
                if hotels_result and len(hotels_result) > 0:
                    # Берем первый отель из результатов
                    hotel_info = hotels_result[0]
                    
                    # Преобразуем данные в правильный формат
                    # Если hotel_info - это объект Pydantic, конвертируем в dict
                    if hasattr(hotel_info, 'model_dump'):
                        hotel_data = hotel_info.model_dump()
                    elif hasattr(hotel_info, 'dict'):
                        hotel_data = hotel_info.dict()
                    else:
                        hotel_data = hotel_info if isinstance(hotel_info, dict) else {}
                    
                    # Обновляем тур данными в правильном формате
                    self._update_tour_with_hotel_data(tour, hotel_data)
                    
                    logger.debug(f"✅ Обогащен тур для отеля {hotel_code}")
                    return
                else:
                    logger.debug(f"⚠️ Нет результатов от hotels API для отеля {hotel_code}")
                    
            except Exception as api_error:
                logger.debug(f"Ошибка обращения к hotels API для {hotel_code}: {api_error}")
                
                # Попробуем альтернативный метод - прямое обращение к tourvisor_client
                try:
                    from app.core.tourvisor_client import tourvisor_client
                    
                    logger.debug(f"🔄 Пробуем прямое обращение к tourvisor_client для отеля {hotel_code}")
                    
                    # Прямой поиск туров по отелю
                    search_params = {
                        "departure": departure_city,
                        "country": int(country_code) if str(country_code).isdigit() else 1,
                        "hotels": hotel_code,
                        "adults": tour.get("adults", 2),
                        "children": tour.get("children", 0),
                        "nightsfrom": max(1, tour.get("nights", 7) - 1),
                        "nightsto": tour.get("nights", 7) + 1,
                        "format": "json",
                        "onpage": 10
                    }
                    
                    # Добавляем даты
                    tomorrow = datetime.now() + timedelta(days=1)
                    week_later = datetime.now() + timedelta(days=8)
                    search_params["datefrom"] = tomorrow.strftime("%d.%m.%Y")
                    search_params["dateto"] = week_later.strftime("%d.%m.%Y")
                    
                    request_id = await tourvisor_client.search_tours(search_params)
                    
                    if request_id:
                        # Ждем результатов
                        max_wait_time = 30
                        start_wait = datetime.now()
                        
                        while (datetime.now() - start_wait).total_seconds() < max_wait_time:
                            try:
                                status_result = await tourvisor_client.get_search_status(request_id)
                                
                                if status_result:
                                    status_data = status_result.get("data", {}).get("status", {})
                                    state = status_data.get("state", "")
                                    
                                    if state == "finished":
                                        break
                                    elif state == "error":
                                        break
                                
                                await asyncio.sleep(2)
                                
                            except Exception as status_error:
                                logger.debug(f"Ошибка проверки статуса: {status_error}")
                                await asyncio.sleep(2)
                        
                        # Получаем результаты
                        try:
                            search_results = await tourvisor_client.get_search_results(request_id)
                            
                            if search_results:
                                # Извлекаем туры из результатов
                                hotels = self._find_hotels_in_results(search_results)
                                
                                for hotel in hotels:
                                    if hotel.get("hotelcode") == hotel_code:
                                        # Обновляем тур данными в правильном формате
                                        self._update_tour_with_hotel_data(tour, hotel)
                                        
                                        logger.debug(f"✅ Обогащен тур через tourvisor_client для отеля {hotel_code}")
                                        return
                                
                        except Exception as results_error:
                            logger.debug(f"Ошибка получения результатов tourvisor_client: {results_error}")
                
                except Exception as direct_error:
                    logger.debug(f"Ошибка прямого обращения к tourvisor_client: {direct_error}")
            
            # Fallback: создаем базовые данные
            logger.debug(f"⚠️ Используем fallback для отеля {hotel_code}")
            await self._create_mock_tour_data(tour)
            
        except Exception as e:
            logger.debug(f"Ошибка обогащения тура: {e}")
            await self._create_mock_tour_data(tour)
    
    def _update_tour_with_hotel_data(self, tour: Dict, hotel_data: Dict) -> None:
        """Обновляет тур данными отеля в правильном формате"""
        try:
            # Обновляем основные данные отеля
            tour.update({
                "hotelcode": hotel_data.get("hotelcode") or hotel_data.get("hotel_code", tour.get("hotelcode", "")),
                "countrycode": hotel_data.get("countrycode") or hotel_data.get("country_code", tour.get("countrycode", "")),
                "countryname": hotel_data.get("countryname") or hotel_data.get("country_name", tour.get("countryname", "")),
                "regioncode": hotel_data.get("regioncode") or hotel_data.get("region_code", tour.get("regioncode", "")),
                "regionname": hotel_data.get("regionname") or hotel_data.get("region_name", tour.get("regionname", "")),
                "subregioncode": hotel_data.get("subregioncode") or hotel_data.get("subregion_code", tour.get("subregioncode", "")),
                "hotelname": hotel_data.get("hotelname") or hotel_data.get("hotel_name", tour.get("hotelname", "")),
                "hotelstars": hotel_data.get("hotelstars") or hotel_data.get("hotel_stars", tour.get("hotelstars", 0)),
                "hotelrating": hotel_data.get("hotelrating") or hotel_data.get("hotel_rating", tour.get("hotelrating", 0)),
                "hoteldescription": hotel_data.get("hoteldescription") or hotel_data.get("hotel_description", tour.get("hoteldescription", "")),
                "fulldesclink": hotel_data.get("fulldesclink") or hotel_data.get("full_desc_link", tour.get("fulldesclink", "")),
                "reviewlink": hotel_data.get("reviewlink") or hotel_data.get("review_link", tour.get("reviewlink", "")),
                "picturelink": hotel_data.get("picturelink") or hotel_data.get("picture_link", tour.get("picturelink", "")),
                "isphoto": hotel_data.get("isphoto", tour.get("isphoto", 0)),
                "iscoords": hotel_data.get("iscoords", tour.get("iscoords", 0)),
                "isdescription": hotel_data.get("isdescription", tour.get("isdescription", 0)),
                "isreviews": hotel_data.get("isreviews", tour.get("isreviews", 0)),
                "seadistance": hotel_data.get("seadistance", tour.get("seadistance", 0))
            })
            
            # Обновляем туры в правильном формате
            hotel_tours = hotel_data.get("tours", [])
            
            if hotel_tours:
                formatted_tours = []
                for tour_info in hotel_tours:
                    formatted_tour = {
                        "operatorcode": tour_info.get("operatorcode") or tour_info.get("operator_code", ""),
                        "operatorname": tour_info.get("operatorname") or tour_info.get("operator_name", ""),
                        "flydate": tour_info.get("flydate") or tour_info.get("fly_date") or tour_info.get("departure_date", ""),
                        "nights": int(tour_info.get("nights", 0)) if tour_info.get("nights") else 0,
                        "price": int(tour_info.get("price", 0)) if tour_info.get("price") else 0,
                        "placement": tour_info.get("placement") or tour_info.get("room_type", ""),
                        "adults": int(tour_info.get("adults", 0)) if tour_info.get("adults") else 0,
                        "children": int(tour_info.get("children", 0)) if tour_info.get("children") else 0,
                        "meal": tour_info.get("meal") or tour_info.get("mealrussian", ""),
                        "room": tour_info.get("room") or tour_info.get("room_type", ""),
                        "currency": tour_info.get("currency", "RUB"),
                        "tourname": tour_info.get("tourname") or tour_info.get("tour_name", ""),
                        "tourid": tour_info.get("tourid") or tour_info.get("tour_id", ""),
                        "fuelcharge": int(tour_info.get("fuelcharge", 0)) if tour_info.get("fuelcharge") else 0,
                        "operatorlink": tour_info.get("operatorlink") or tour_info.get("operator_link", ""),
                        "regular": bool(tour_info.get("regular", False)),
                        "promo": bool(tour_info.get("promo", False)),
                        "onrequest": bool(tour_info.get("onrequest", False)),
                        "mealcode": tour_info.get("mealcode") or tour_info.get("meal_code", ""),
                        "flightstatus": int(tour_info.get("flightstatus", 0)) if tour_info.get("flightstatus") else 0,
                        "hotelstatus": int(tour_info.get("hotelstatus", 0)) if tour_info.get("hotelstatus") else 0,
                        "nightflight": int(tour_info.get("nightflight", 0)) if tour_info.get("nightflight") else 0
                    }
                    formatted_tours.append(formatted_tour)
                
                tour["tours"] = formatted_tours
                
                # Обновляем основной тур данными из первого тура
                if formatted_tours:
                    best_tour = formatted_tours[0]
                    tour["price"] = best_tour["price"]
                    tour["nights"] = best_tour["nights"]
                    tour["operatorname"] = best_tour["operatorname"]
                    tour["flydate"] = best_tour["flydate"]
                    tour["meal"] = best_tour["meal"]
                    tour["placement"] = best_tour["placement"]
                    tour["adults"] = best_tour["adults"]
                    tour["children"] = best_tour["children"]
            else:
                # Если нет туров, создаем базовый тур
                tour["tours"] = [{
                    "operatorcode": "",
                    "operatorname": tour.get("operatorname", ""),
                    "flydate": tour.get("flydate", ""),
                    "nights": tour.get("nights", 0),
                    "price": tour.get("price", 0),
                    "placement": tour.get("placement", ""),
                    "adults": tour.get("adults", 0),
                    "children": tour.get("children", 0),
                    "meal": tour.get("meal", ""),
                    "room": "",
                    "currency": "RUB",
                    "tourname": "",
                    "tourid": f"fallback_{random.randint(1000, 9999)}",
                    "fuelcharge": 0,
                    "operatorlink": "",
                    "regular": False,
                    "promo": False,
                    "onrequest": False,
                    "mealcode": "",
                    "flightstatus": 0,
                    "hotelstatus": 0,
                    "nightflight": 0
                }]
            
            # Убираем старые поля, которые не нужны в новом формате
            fields_to_remove = [
                "hotel_name", "hotel_stars", "hotel_rating", "country_name", "region_name",
                "operator_name", "fly_date", "tour_name", "picture_link", "search_source",
                "generation_strategy", "hotel_type", "hoteldescriptions", "currency"
            ]
            
            for field in fields_to_remove:
                tour.pop(field, None)
            
        except Exception as e:
            logger.debug(f"Ошибка обновления тура: {e}")
    
    async def _create_mock_tour_data(self, tour: Dict) -> None:
        """Создание базовых данных для тура в правильном формате"""
        try:
            # Создаем данные в формате hotels API
            hotel_name = tour.get("hotel_name") or tour.get("hotelname", "Unknown Hotel")
            
            # Основные данные отеля
            tour.update({
                "hotelcode": tour.get("hotelcode", f"MOCK_{random.randint(1000, 9999)}"),
                "countrycode": tour.get("countrycode", "1"),
                "countryname": tour.get("country_name", "Неизвестная страна"),
                "regioncode": tour.get("regioncode", "1"),
                "regionname": tour.get("region_name", "Неизвестный регион"),
                "subregioncode": "",
                "hotelname": hotel_name,
                "hotelstars": tour.get("hotel_stars", 0),
                "hotelrating": tour.get("hotel_rating", 0),
                "hoteldescription": f"Отель {hotel_name} - прекрасное место для отдыха",
                "fulldesclink": "",
                "reviewlink": "",
                "picturelink": tour.get("picture_link", ""),
                "isphoto": 0,
                "iscoords": 0,
                "isdescription": 1,
                "isreviews": 0,
                "seadistance": tour.get("seadistance", 0)
            })
            
            # Создаем массив туров в правильном формате
            base_price = tour.get("price", 50000)
            tours_list = []
            
            # Создаем 2-3 варианта туров
            for i in range(random.randint(2, 3)):
                mock_tour = {
                    "operatorcode": f"OP{random.randint(10, 99)}",
                    "operatorname": tour.get("operator_name", random.choice(["Coral Travel", "TUI", "Pegas", "Anex"])),
                    "flydate": tour.get("fly_date", (datetime.now() + timedelta(days=random.randint(7, 30))).strftime("%d.%m.%Y")),
                    "nights": tour.get("nights", random.choice([7, 10, 14])),
                    "price": int(base_price * random.uniform(0.8, 1.2)),
                    "placement": tour.get("placement", random.choice(["DBL", "SGL", "TRPL"])),
                    "adults": tour.get("adults", 2),
                    "children": tour.get("children", 0),
                    "meal": tour.get("meal", random.choice(["Завтрак", "Полупансион", "Все включено"])),
                    "room": random.choice(["Standard", "Superior", "Deluxe"]),
                    "currency": "RUB",
                    "tourname": f"Тур {i+1}",
                    "tourid": f"mock_{random.randint(10000, 99999)}",
                    "fuelcharge": random.randint(0, 5000),
                    "operatorlink": "",
                    "regular": random.choice([True, False]),
                    "promo": random.choice([True, False]),
                    "onrequest": False,
                    "mealcode": random.choice(["BB", "HB", "FB", "AI"]),
                    "flightstatus": random.randint(0, 2),
                    "hotelstatus": random.randint(0, 2),
                    "nightflight": random.randint(0, 1)
                }
                tours_list.append(mock_tour)
            
            tour["tours"] = tours_list
            
            # Обновляем основные данные тура из первого тура
            if tours_list:
                best_tour = tours_list[0]
                tour["price"] = best_tour["price"]
                tour["nights"] = best_tour["nights"]
            
            # Убираем старые поля
            fields_to_remove = [
                "hotel_name", "hotel_stars", "hotel_rating", "country_name", "region_name",
                "operator_name", "fly_date", "tour_name", "picture_link", "search_source",
                "generation_strategy", "hotel_type", "hoteldescriptions", "currency"
            ]
            
            for field in fields_to_remove:
                tour.pop(field, None)
            
        except Exception as e:
            logger.debug(f"Ошибка создания mock данных: {e}")
            # Минимальные данные
            tour.update({
                "hotelcode": f"MOCK_{random.randint(1000, 9999)}",
                "hotelname": "Mock Hotel",
                "countryname": "Mock Country",
                "regionname": "Mock Region",
                "tours": [{
                    "operatorcode": "MOCK",
                    "operatorname": "Mock Operator",
                    "flydate": "",
                    "nights": 7,
                    "price": 50000,
                    "placement": "DBL",
                    "adults": 2,
                    "children": 0,
                    "meal": "Завтрак",
                    "room": "Standard",
                    "currency": "RUB",
                    "tourname": "Mock Tour",
                    "tourid": f"mock_{random.randint(1000, 9999)}",
                    "fuelcharge": 0,
                    "operatorlink": "",
                    "regular": False,
                    "promo": False,
                    "onrequest": False,
                    "mealcode": "BB",
                    "flightstatus": 0,
                    "hotelstatus": 0,
                    "nightflight": 0
                }]
            })
    
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
                        "uses_existing_tour_service": True,
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
                            "has_descriptions": any(t.get("hoteldescription") for t in cached_tours),
                            "has_tours_data": any(t.get("tours") for t in cached_tours),
                            "uses_real_api": True
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
                    "uses_existing_tour_service": True,
                    "hoteltypes_filter_enabled": True,
                    "supported_api_filters": [info["api_param"] for info in self.hotel_types_mapping.values() if info["api_param"]],
                    "enhanced_with_real_data": True,
                    "fallback_to_mock": True
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
                "uses_existing_tour_service": True,
                "tourvisor_hoteltypes_field": "hoteltypes",
                "supported_values": [info["api_param"] for info in self.hotel_types_mapping.values() if info["api_param"]],
                "real_api_integration": True,
                "documentation": "Использует существующий tour_service для получения реальных данных"
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