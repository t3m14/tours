# app/tasks/random_tours_cache_update.py - ИСПРАВЛЕННАЯ ВЕРСИЯ С АНГЛИЙСКИМИ НАЗВАНИЯМИ ТИПОВ ОТЕЛЕЙ

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
    """Сервис для автоматического обновления кэша случайных туров с исправленной логикой получения реальных туров"""
    
    def __init__(self):
        # Настройки из переменных окружения
        import os
        self.update_interval = int(os.getenv("RANDOM_TOURS_UPDATE_INTERVAL_HOURS", "12")) * 3600  # 12 часов по умолчанию
        self.tours_per_type = int(os.getenv("RANDOM_TOURS_PER_TYPE", "8"))  # 8 туров на тип отеля
        self.generation_strategies = os.getenv("RANDOM_TOURS_STRATEGIES", "search,hot_tours,mock").split(",")
        self.countries_to_update = os.getenv("RANDOM_TOURS_COUNTRIES", "1,2,4,9,8").split(",")  # Топ страны
        
        # АНГЛИЙСКИЕ типы отелей с маппингом на API TourVisor
        self.hotel_types_mapping = {
            "any": {
                "display_name": "any", 
                "api_param": None,  # Без фильтрации
                "cache_key": "any"
            },
            "active": {
                "display_name": "active",
                "api_param": "active",  # TourVisor API: active
                "cache_key": "active"
            },
            "relax": {
                "display_name": "relax",
                "api_param": "relax",  # TourVisor API: relax
                "cache_key": "relax"
            },
            "family": {
                "display_name": "family",
                "api_param": "family",  # TourVisor API: family
                "cache_key": "family"
            },
            "health": {
                "display_name": "health",
                "api_param": "health",  # TourVisor API: health
                "cache_key": "health"
            },
            "city": {
                "display_name": "city",
                "api_param": "city",  # TourVisor API: city
                "cache_key": "city"
            },
            "beach": {
                "display_name": "beach",
                "api_param": "beach",  # TourVisor API: beach
                "cache_key": "beach"
            },
            "deluxe": {
                "display_name": "deluxe",
                "api_param": "deluxe",  # TourVisor API: deluxe
                "cache_key": "deluxe"
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
            cache_key = f"random_tours_{cache_key_suffix}"
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
        ИСПРАВЛЕННАЯ генерация туров с использованием API фильтрации по типам отелей
        
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
            
            # СТРАТЕГИЯ 1: ПОПРОБУЕМ ПОИСК БЕЗ ФИЛЬТРА СНАЧАЛА (для отладки)
            if "search" in self.generation_strategies:
                logger.debug(f"🔍 Стратегия поиска для {display_name}")
                
                try:
                    # Случайная страна из списка
                    country_id = random.choice([int(c) for c in self.countries_to_update])
                    
                    # Даты поиска: завтра + неделя
                    tomorrow = datetime.now() + timedelta(days=1)
                    week_later = datetime.now() + timedelta(days=8)
                    
                    # ИСПРАВЛЕННЫЕ параметры поиска
                    search_params = {
                        "departure": random.choice([1, 2, 3, 4, 5]),  # Случайный город вылета
                        "country": country_id,
                        "datefrom": tomorrow.strftime("%d.%m.%Y"),
                        "dateto": week_later.strftime("%d.%m.%Y"),
                        "nightsfrom": 7,
                        "nightsto": 10,
                        "adults": 2,
                        "format": "json",  # ИЗМЕНЕНО: JSON вместо XML для лучшей совместимости
                        "onpage": 20       # УМЕНЬШЕНО: меньше результатов для стабильности
                    }
                    
                    # Добавляем фильтр ТОЛЬКО если он существует и мы НЕ тестируем базовый поиск
                    if api_param and hotel_type_key != "any":
                        search_params["hoteltypes"] = api_param
                        logger.debug(f"🎯 Добавлен фильтр hoteltypes={api_param}")
                    
                    logger.info(f"📝 Параметры поиска для {display_name}: {search_params}")
                    
                    # Запускаем поиск
                    request_id = await tourvisor_client.search_tours(search_params)
                    api_calls_made += 1
                    
                    if request_id:
                        logger.info(f"🚀 Запущен поиск {request_id} для {display_name}")
                        
                        # УВЕЛИЧЕННОЕ время ожидания и улучшенная логика
                        max_wait_time = 120  # 2 минуты вместо 60 секунд
                        start_wait = datetime.now()
                        last_hotels_count = 0

                        while (datetime.now() - start_wait).total_seconds() < max_wait_time:
                            try:
                                status_result = await tourvisor_client.get_search_status(request_id)
                                api_calls_made += 1
                                
                                if status_result:
                                    status_data = status_result.get("data", {}).get("status", {})
                                    state = status_data.get("state", "")
                                    hotels_found = int(status_data.get("hotelsfound", 0))
                                    progress = int(status_data.get("progress", 0))
                                    
                                    logger.info(f"📊 Поиск {request_id} для {display_name}: {state}, {progress}%, отелей: {hotels_found}")
                                    
                                    # УЛУЧШЕННАЯ ЛОГИКА ЗАВЕРШЕНИЯ:
                                    if state == "finished":
                                        if hotels_found > 0:
                                            logger.info(f"✅ Поиск {display_name} завершен с {hotels_found} отелями")
                                            break
                                        else:
                                            logger.warning(f"⚠️ Поиск {display_name} завершен, но отелей не найдено")
                                            break
                                            
                                    elif hotels_found >= 3 and progress >= 30:
                                        # СНИЖЕН порог: если есть хотя бы 3 отеля и прогресс >= 30%
                                        logger.info(f"📊 Поиск {display_name}: достаточно результатов ({hotels_found} отелей при {progress}%)")
                                        break
                                        
                                    elif state == "error":
                                        logger.warning(f"❌ Ошибка поиска для {display_name}")
                                        break
                                    
                                    # Если количество отелей не растет 30+ секунд, прерываем
                                    if hotels_found == last_hotels_count and (datetime.now() - start_wait).total_seconds() > 30:
                                        if hotels_found > 0:
                                            logger.info(f"⏰ Поиск {display_name} застопорился на {hotels_found} отелях, завершаем")
                                            break
                                    
                                    last_hotels_count = hotels_found
                                
                                await asyncio.sleep(5)  # УВЕЛИЧЕНА пауза до 5 секунд
                                
                            except Exception as e:
                                logger.warning(f"⚠️ Ошибка проверки статуса для {display_name}: {e}")
                                await asyncio.sleep(5)
                        
                        # Получаем результаты независимо от статуса
                        try:
                            logger.info(f"📥 Получаем результаты поиска {request_id}")
                            search_results = await tourvisor_client.get_search_results(request_id)
                            api_calls_made += 1
                            
                            # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ СТРУКТУРЫ ОТВЕТА
                            logger.info(f"🔍 СТРУКТУРА ОТВЕТА для {display_name}:")
                            logger.info(f"📊 Ключи верхнего уровня: {list(search_results.keys())}")
                            logger.info(f"📄 Первые 1000 символов: {json.dumps(search_results, ensure_ascii=False)[:1000]}")
                            
                            if search_results:
                                tours_from_search = await self._extract_tours_from_search_results(
                                    search_results, self.tours_per_type, display_name
                                )
                                tours_generated.extend(tours_from_search)
                                logger.info(f"✅ Поиск {display_name}: извлечено {len(tours_from_search)} туров через API")
                                
                        except Exception as results_error:
                            logger.error(f"❌ Ошибка получения результатов для {display_name}: {results_error}")
                    
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка поиска для {display_name}: {e}")
                    logger.warning(f"📄 Трейсбек: {traceback.format_exc()}")
            
            # СТРАТЕГИЯ 2: Горящие туры (если не хватает туров)
            if len(tours_generated) < self.tours_per_type and "hot_tours" in self.generation_strategies:
                logger.debug(f"🔥 Стратегия горящих туров для {display_name}")
                
                try:
                    country_id = random.choice([int(c) for c in self.countries_to_update])
                    
                    hot_tours_data = await tourvisor_client.get_hot_tours(
                        city=1,  # Москва
                        items=min(20, self.tours_per_type * 2),
                        countries=str(country_id)
                    )
                    api_calls_made += 1
                    
                    if hot_tours_data and "data" in hot_tours_data:
                        tours_from_hot = await self._extract_tours_from_hot_tours(
                            hot_tours_data, self.tours_per_type - len(tours_generated), display_name
                        )
                        tours_generated.extend(tours_from_hot)
                        logger.info(f"🔥 Горящие туры {display_name}: получено {len(tours_from_hot)} туров")
                
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка получения горящих туров для {display_name}: {e}")
            
            # СТРАТЕГИЯ 3: Mock туры (если все еще не хватает)
            if len(tours_generated) < self.tours_per_type and "mock" in self.generation_strategies:
                needed = self.tours_per_type - len(tours_generated)
                logger.debug(f"🎭 Стратегия mock туров для {display_name}: нужно {needed}")
                
                mock_tours = await self._generate_mock_tours(needed, hotel_type_key, display_name)
                tours_generated.extend(mock_tours)
                logger.info(f"🎭 Mock туры {display_name}: сгенерировано {len(mock_tours)} туров")
            
            # Ограничиваем до нужного количества
            tours_generated = tours_generated[:self.tours_per_type]
            
            logger.info(f"📊 ИТОГО для {display_name}: {len(tours_generated)} туров, API вызовов: {api_calls_made}")
            return tours_generated, api_calls_made
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка генерации для {display_name}: {e}")
            logger.error(f"📄 Трейсбек: {traceback.format_exc()}")
            return [], api_calls_made
    
    async def _extract_tours_from_search_results(self, search_results: Dict, limit: int, hotel_type: str) -> List[Dict]:
        """ИСПРАВЛЕННОЕ извлечение туров из результатов поиска с детальной диагностикой"""
        try:
            tours = []
            
            logger.info(f"🔍 АНАЛИЗ СТРУКТУРЫ РЕЗУЛЬТАТОВ для {hotel_type}")
            logger.debug(f"📊 Полный ответ: {json.dumps(search_results, ensure_ascii=False, indent=2)[:2000]}")
            
            # ИСПРАВЛЕННАЯ ЛОГИКА ПОИСКА ОТЕЛЕЙ
            hotels = []
            
            # Метод 1: Прямой поиск в разных местах структуры
            search_paths = [
                ["data", "result", "hotel"],      # Стандартная структура
                ["data", "hotel"],                # Прямо в data
                ["hotel"],                        # В корне
                ["result", "hotel"],              # Без data
                ["data", "result", "hotels"],     # Множественное число
                ["data", "hotels"],               # Множественное в data
                ["hotels"]                        # Множественное в корне
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
                        # Если дошли до конца пути успешно
                        if current:
                            hotels = current if isinstance(current, list) else [current]
                            logger.info(f"🏨 Найдены отели по пути: {' -> '.join(path)} ({len(hotels)} отелей)")
                            break
                except Exception as path_error:
                    logger.debug(f"⚠️ Ошибка поиска по пути {path}: {path_error}")
                    continue
            
            # Метод 2: Рекурсивный поиск если не нашли
            if not hotels:
                logger.warning(f"⚠️ Отели не найдены стандартными путями, пробуем рекурсивный поиск")
                hotels = self._recursive_find_hotels(search_results)
                if hotels:
                    logger.info(f"🏨 Найдены отели рекурсивным поиском: {len(hotels)} отелей")
            
            if not hotels:
                logger.error(f"❌ Отели НЕ НАЙДЕНЫ в результатах для {hotel_type}")
                logger.error(f"🔍 Доступные ключи в ответе: {self._get_all_keys_recursive(search_results)}")
                return []
            
            logger.info(f"🏨 Найдено {len(hotels)} отелей для обработки")
            
            # Извлекаем туры из отелей
            for i, hotel in enumerate(hotels[:limit]):
                try:
                    if not isinstance(hotel, dict):
                        logger.warning(f"⚠️ Отель {i+1} не является словарем: {type(hotel)}")
                        continue
                    
                    hotel_name = hotel.get("hotelname", hotel.get("name", f"Hotel_{i+1}"))
                    logger.debug(f"🏨 Обрабатываем отель {i+1}: {hotel_name}")
                    
                    # Ищем туры в отеле разными способами
                    hotel_tours = self._extract_tours_from_hotel(hotel)
                    
                    if hotel_tours:
                        logger.debug(f"🎫 Отель {hotel_name}: найдено {len(hotel_tours)} туров")
                        
                        # Берем первый валидный тур
                        for tour in hotel_tours:
                            try:
                                tour_data = self._build_tour_data(hotel, tour, hotel_type)
                                if tour_data:
                                    tours.append(tour_data)
                                    logger.info(f"✅ Извлечен тур: {tour_data['hotel_name']} - {tour_data['price']} руб")
                                    break  # Берем только первый валидный тур из отеля
                            except Exception as tour_build_error:
                                logger.warning(f"⚠️ Ошибка создания тура: {tour_build_error}")
                                continue
                    else:
                        logger.debug(f"⚠️ В отеле {hotel_name} нет туров")
                    
                    if len(tours) >= limit:
                        break
                        
                except Exception as hotel_error:
                    logger.warning(f"⚠️ Ошибка обработки отеля {i+1}: {hotel_error}")
                    continue
            
            logger.info(f"🎯 ИТОГО извлечено {len(tours)} реальных туров для {hotel_type}")
            return tours
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка извлечения туров для {hotel_type}: {e}")
            logger.error(f"📄 Трейсбек: {traceback.format_exc()}")
            return []
    
    def _recursive_find_hotels(self, data, depth=0, max_depth=5):
        """Рекурсивный поиск отелей в структуре данных"""
        if depth > max_depth:
            return []
        
        hotels = []
        
        if isinstance(data, dict):
            # Проверяем, является ли текущий объект отелем
            if self._looks_like_hotel(data):
                return [data]
            
            # Ищем в дочерних элементах
            for key, value in data.items():
                if key.lower() in ['hotel', 'hotels']:
                    if isinstance(value, list):
                        hotels.extend(value)
                    elif value:
                        hotels.append(value)
                else:
                    child_hotels = self._recursive_find_hotels(value, depth + 1, max_depth)
                    hotels.extend(child_hotels)
        
        elif isinstance(data, list):
            for item in data:
                child_hotels = self._recursive_find_hotels(item, depth + 1, max_depth)
                hotels.extend(child_hotels)
        
        return hotels
    
    def _looks_like_hotel(self, data):
        """Проверяет, похож ли объект на отель"""
        if not isinstance(data, dict):
            return False
        
        hotel_indicators = ['hotelname', 'hotelcode', 'hotelstars', 'countryname', 'regionname']
        return any(key in data for key in hotel_indicators)
    
    def _get_all_keys_recursive(self, data, depth=0, max_depth=3):
        """Получает все ключи из структуры данных рекурсивно"""
        if depth > max_depth:
            return set()
        
        keys = set()
        
        if isinstance(data, dict):
            keys.update(data.keys())
            for value in data.values():
                keys.update(self._get_all_keys_recursive(value, depth + 1, max_depth))
        elif isinstance(data, list) and data:
            for item in data[:3]:  # Проверяем только первые 3 элемента
                keys.update(self._get_all_keys_recursive(item, depth + 1, max_depth))
        
        return keys
    
    def _extract_tours_from_hotel(self, hotel):
        """Извлекает туры из данных отеля"""
        hotel_tours = []
        
        # Различные пути к турам
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
                    # Если дошли до конца пути
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
            # Проверяем наличие цены
            price = tour.get("price", 0)
            if not price or (isinstance(price, (str, int, float)) and float(price) <= 0):
                logger.debug(f"⚠️ Тур без валидной цены: {price}")
                return None
            
            # Безопасно извлекаем данные
            def safe_get(obj, key, default="", convert_func=str):
                try:
                    value = obj.get(key, default)
                    return convert_func(value) if value not in [None, "", 0] else convert_func(default)
                except:
                    return convert_func(default)
            
            # Функция для получения названия города по коду
            def get_city_name_by_code(city_code):
                if not city_code:
                    return "Москва"
                
                try:
                    city_code = int(city_code)
                except (ValueError, TypeError):
                    return "Москва"
                city_map = {
                    1: "из Москвы", 2: "из Перми", 3: "из Екатеринбурга", 4: "из Уфы",
                    5: "из Санкт-Петербурга", 6: "из Казани", 7: "из Нижнего Новгорода",
                    8: "из Самары", 9: "из Ростова-на-Дону", 10: "из Краснодара",
                    11: "из Волгограда", 12: "из Воронежа", 13: "из Саратова",
                    14: "из Тольятти", 15: "из Ижевска"
                }
                return city_map.get(city_code, "Москва")
            
            # ПРАВИЛЬНОЕ ПОЛУЧЕНИЕ departure
            # Приоритет: из search_params -> из hotel -> из tour -> маппинг по коду -> fallback
            departure_city = None
            if search_params and search_params.get("departure"):
                departure_city = get_city_name_by_code(search_params["departure"])
            elif hotel.get("departurename"):
                departure_city = safe_get(hotel, "departurename")
            elif tour.get("departurename"):  
                departure_city = safe_get(tour, "departurename")
            elif hotel.get("departurecode"):
                departure_city = get_city_name_by_code(hotel.get("departurecode"))
            elif tour.get("departurecode"):
                departure_city = get_city_name_by_code(tour.get("departurecode"))
            else:
                departure_city = "Москва"  # Fallback

           # Словарь склонений городов
            declensions = {
                "Москва": "из Москвы",
                "Санкт-Петербург": "из Санкт-Петербурга", 
                "Пермь": "из Перми",
                "Саратов": "из Саратова",
                "Екатеринбург": "из Екатеринбурга",
                "Казань": "из Казани",
                "Новосибирск": "из Новосибирска",
                "Нижний Новгород": "из Нижнего Новгорода",
                "Челябинск": "из Челябинска",
                "Самара": "из Самары",
                "Ростов-на-Дону": "из Ростова-на-Дону",
                "Уфа": "из Уфы",
                "Красноярск": "из Красноярска",
                "Воронеж": "из Воронежа",
                "Волгоград": "из Волгограда"
            }
            
            # Приводим город к родительному падежу
            if departure_city in declensions:
                departure_city = declensions[departure_city]
            elif not departure_city.startswith("из "):
                departure_city = f"из {departure_city}"

            
            # ПРАВИЛЬНОЕ ПОЛУЧЕНИЕ seadistance
            # seadistance всегда находится в данных отеля, не тура
            seadistance = (
                safe_get(hotel, "seadistance", 0, int) or 
                safe_get(tour, "seadistance", 0, int) or
                random.choice([50, 100, 150, 200, 300, 500])  # Случайное значение если нет данных
            )
            
            tour_data = {
                "hotel_name": safe_get(hotel, "hotelname"),
                "hotel_stars": safe_get(hotel, "hotelstars", 0, int),
                "hotel_rating": safe_get(hotel, "hotelrating", 0, float),
                "country_name": safe_get(hotel, "countryname"),
                "region_name": safe_get(hotel, "regionname"),
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
                
                # ИСПРАВЛЕННЫЕ ПОЛЯ:
                "departure": departure_city,  # Правильно определенный город
                "seadistance": seadistance,   # Расстояние до моря из отеля
                
                # Дополнительные поля для совместимости
                "departurename": departure_city,  # Дублируем для совместимости  
                "departurecode": str(search_params.get("departure", 1)) if search_params else "1",
                "departurenamefrom": f"из {departure_city}",
                "countrycode": str(safe_get(hotel, "countrycode", search_params.get("country", 1) if search_params else 1)),
                "countryname": safe_get(hotel, "countryname"),
                "operatorcode": safe_get(tour, "operatorcode", ""),
                "hotelcode": safe_get(hotel, "hotelcode", ""),
                "hotelregioncode": safe_get(hotel, "regioncode", ""),
                "hotelregionname": safe_get(hotel, "regionname"),
                "hotelpicture": safe_get(hotel, "picturelink"),
                "fulldesclink": safe_get(hotel, "fulldesclink"),
            }
            
            # Валидация обязательных полей
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
                        "search_source": "hot_tours"
                    }
                    
                    if tour_data["price"] > 0 and tour_data["hotel_name"]:
                        tours.append(tour_data)
                    
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка обработки горящего тура: {e}")
                    continue
            
            return tours
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения горящих туров для {hotel_type}: {e}")
            return []
    
    async def _generate_mock_tours(self, count: int, hotel_type_key: str, hotel_type_display: str) -> List[Dict]:
        """Генерация mock туров для типа отеля"""
        try:
            tours = []
            
            # Данные для генерации mock туров с английскими ключами
            mock_data_by_type = {
                "any": {
                    "hotels": ["Sunset Resort", "Ocean View Hotel", "Paradise Beach", "Golden Sands"],
                    "price_range": (25000, 80000),
                    "regions": ["Хургада", "Анталья", "Пхукет", "Дубай"]
                },
                "active": {
                    "hotels": ["Adventure Resort", "Active Sports Hotel", "Mountain View Resort", "Extreme Hotel"],
                    "price_range": (30000, 90000),
                    "regions": ["Анталья", "Красная Поляна", "Буковель", "Альпы"]
                },
                "relax": {
                    "hotels": ["Spa Resort", "Wellness Hotel", "Zen Garden Resort", "Tranquil Waters"],
                    "price_range": (40000, 120000),
                    "regions": ["Карловы Вары", "Баден-Баден", "Мариенбад", "Термальные источники"]
                },
                "family": {
                    "hotels": ["Family Resort", "Kids Club Hotel", "Happy Family Resort", "Children Paradise"],
                    "price_range": (35000, 95000),
                    "regions": ["Анталья", "Крит", "Кипр", "Болгария"]
                },
                "health": {
                    "hotels": ["Health Resort", "Medical Spa", "Healing Waters Resort", "Wellness Center"],
                    "price_range": (50000, 150000),
                    "regions": ["Карловы Вары", "Железноводск", "Ессентуки", "Кисловодск"]
                },
                "city": {
                    "hotels": ["City Hotel", "Metropolitan Resort", "Urban Oasis", "Downtown Hotel"],
                    "price_range": (20000, 70000),
                    "regions": ["Стамбул", "Дубай", "Бангкок", "Сингапур"]
                },
                "beach": {
                    "hotels": ["Beach Resort", "Seaside Hotel", "Ocean Paradise", "Tropical Beach"],
                    "price_range": (30000, 100000),
                    "regions": ["Хургада", "Пхукет", "Мальдивы", "Бали"]
                },
                "deluxe": {
                    "hotels": ["Luxury Resort", "Premium Hotel", "Elite Resort", "VIP Paradise"],
                    "price_range": (80000, 250000),
                    "regions": ["Мальдивы", "Сейшелы", "Сент-Барт", "Монако"]
                }
            }

            mock_config = mock_data_by_type.get(hotel_type_key, mock_data_by_type["any"])
            
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
    
    # API методы для управления
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
                cache_key = f"random_tours_{cache_key_suffix}"
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
                cache_key = f"random_tours_{cache_key_suffix}"
                
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
    
    async def debug_search_extraction(self, hotel_type_key: str) -> Dict[str, Any]:
        """Диагностический метод для отладки извлечения туров"""
        try:
            from app.core.tourvisor_client import tourvisor_client
            from datetime import datetime, timedelta
            
            logger.info(f"🔍 ДИАГНОСТИКА извлечения туров для {hotel_type_key}")
            
            hotel_type_info = self.hotel_types_mapping[hotel_type_key]
            api_param = hotel_type_info["api_param"]
            
            # Простой поиск
            tomorrow = datetime.now() + timedelta(days=1)
            week_later = datetime.now() + timedelta(days=8)
            
            search_params = {
                "departure": 1,
                "country": 4,  # Турция - должна дать результаты
                "datefrom": tomorrow.strftime("%d.%m.%Y"),
                "dateto": week_later.strftime("%d.%m.%Y"),
                "nightsfrom": 7,
                "nightsto": 10,
                "adults": 2,
                "format": "json",  # JSON для лучшей диагностики
                "onpage": 10
            }
            
            if api_param:
                search_params["hoteltypes"] = api_param
            
            # Запускаем поиск
            request_id = await tourvisor_client.search_tours(search_params)
            logger.info(f"🚀 Диагностический поиск запущен: {request_id}")
            
            # Ждем 15 секунд
            await asyncio.sleep(15)
            
            # Получаем результаты
            search_results = await tourvisor_client.get_search_results(request_id)
            
            # Детальный анализ структуры
            structure_analysis = {
                "request_id": request_id,
                "search_params": search_params,
                "top_level_keys": list(search_results.keys()),
                "has_data": "data" in search_results,
                "data_type": type(search_results.get("data")).__name__ if "data" in search_results else None,
                "all_keys_recursive": list(self._get_all_keys_recursive(search_results))
            }
            
            if "data" in search_results:
                data = search_results["data"]
                if isinstance(data, dict):
                    structure_analysis["data_keys"] = list(data.keys())
                    
                    if "result" in data:
                        result = data["result"]
                        structure_analysis["result_type"] = type(result).__name__
                        if isinstance(result, dict):
                            structure_analysis["result_keys"] = list(result.keys())
                            if "hotel" in result:
                                hotels = result["hotel"]
                                structure_analysis["hotels_count"] = len(hotels) if isinstance(hotels, list) else (1 if hotels else 0)
                                structure_analysis["hotels_type"] = type(hotels).__name__
                                
                                # Анализ первого отеля
                                if hotels:
                                    first_hotel = hotels[0] if isinstance(hotels, list) else hotels
                                    structure_analysis["first_hotel_keys"] = list(first_hotel.keys()) if isinstance(first_hotel, dict) else "not_dict"
                                    structure_analysis["first_hotel_sample"] = str(first_hotel)[:500] if isinstance(first_hotel, dict) else str(first_hotel)
            
            # Пробуем извлечь туры
            extracted_tours = await self._extract_tours_from_search_results(search_results, 5, hotel_type_key)
            
            return {
                "success": True,
                "hotel_type": hotel_type_key,
                "api_param": api_param,
                "structure_analysis": structure_analysis,
                "extracted_tours_count": len(extracted_tours),
                "extracted_tours": extracted_tours[:2] if extracted_tours else [],  # Показываем первые 2 тура
                "raw_results_sample": json.dumps(search_results, ensure_ascii=False, indent=2)[:2000]
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc()
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