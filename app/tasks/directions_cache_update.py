# app/tasks/directions_cache_update.py

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any
import traceback

from app.services.directions_service import directions_service
from app.services.cache_service import cache_service
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class DirectionsCacheUpdateService:
    """Сервис для автоматического обновления кэша направлений"""
    
    def __init__(self):
        self.update_interval = 24 * 60 * 60  # 24 часа в секундах
        self.countries_batch_size = 3  # Обновляем по 3 страны параллельно
        self.is_running = False
        self.last_update = None
        self.update_stats = {}
        
    async def start_scheduler(self):
        """Запуск планировщика автообновления"""
        if self.is_running:
            logger.warning("⚠️ Планировщик уже запущен")
            return
            
        self.is_running = True
        logger.info("🕒 Запуск планировщика обновления кэша направлений")
        
        while self.is_running:
            try:
                await self._run_update_cycle()
                
                # Ждем до следующего обновления
                logger.info(f"😴 Ожидание следующего обновления кэша направлений (24 часа)")
                await asyncio.sleep(self.update_interval)
                
            except asyncio.CancelledError:
                logger.info("🛑 Планировщик обновления кэша направлений остановлен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в планировщике обновления кэша: {e}")
                logger.error(traceback.format_exc())
                # Ждем 1 час перед повтором при ошибке
                await asyncio.sleep(3600)
    
    async def stop_scheduler(self):
        """Остановка планировщика"""
        logger.info("🛑 Остановка планировщика обновления кэша направлений")
        self.is_running = False
    
    async def _run_update_cycle(self):
        """Выполнение одного цикла обновления"""
        start_time = datetime.now()
        logger.info(f"🔄 НАЧАЛО ЦИКЛА ОБНОВЛЕНИЯ КЭША НАПРАВЛЕНИЙ ({start_time.strftime('%Y-%m-%d %H:%M:%S')})")
        
        try:
            # Получаем список всех стран
            countries_list = list(directions_service.COUNTRIES_MAPPING.items())
            total_countries = len(countries_list)
            
            logger.info(f"🌍 Будет обновлено {total_countries} стран")
            
            # Статистика обновления
            update_stats = {
                "start_time": start_time,
                "total_countries": total_countries,
                "processed_countries": 0,
                "successful_countries": 0,
                "failed_countries": 0,
                "total_directions": 0,
                "countries_details": {}
            }
            
            # Обновляем страны батчами для снижения нагрузки
            for i in range(0, total_countries, self.countries_batch_size):
                batch = countries_list[i:i + self.countries_batch_size]
                
                logger.info(f"📦 Обработка батча {i//self.countries_batch_size + 1}/{(total_countries + self.countries_batch_size - 1)//self.countries_batch_size}")
                
                # Создаем задачи для параллельного выполнения батча
                batch_tasks = []
                for country_name, country_info in batch:
                    task = asyncio.create_task(
                        self._update_country_directions(country_name, country_info)
                    )
                    batch_tasks.append((country_name, task))
                
                # Ждем завершения батча
                for country_name, task in batch_tasks:
                    try:
                        result = await task
                        update_stats["processed_countries"] += 1
                        
                        if result["success"]:
                            update_stats["successful_countries"] += 1
                            update_stats["total_directions"] += result["directions_count"]
                        else:
                            update_stats["failed_countries"] += 1
                        
                        update_stats["countries_details"][country_name] = result
                        
                        logger.info(f"✅ {country_name}: {result['directions_count']} направлений")
                        
                    except Exception as e:
                        update_stats["processed_countries"] += 1
                        update_stats["failed_countries"] += 1
                        update_stats["countries_details"][country_name] = {
                            "success": False,
                            "error": str(e),
                            "directions_count": 0
                        }
                        logger.error(f"❌ Ошибка обновления {country_name}: {e}")
                
                # Пауза между батчами для снижения нагрузки на API
                if i + self.countries_batch_size < total_countries:
                    logger.info("⏸️ Пауза между батчами (30 сек)")
                    await asyncio.sleep(30)
            
            # Завершение цикла
            end_time = datetime.now()
            execution_time = end_time - start_time
            
            update_stats["end_time"] = end_time
            update_stats["execution_time_seconds"] = execution_time.total_seconds()
            update_stats["success_rate"] = (update_stats["successful_countries"] / total_countries * 100) if total_countries > 0 else 0
            
            self.last_update = end_time
            self.update_stats = update_stats
            
            # Сохраняем статистику в кэш
            await cache_service.set("directions_cache_update_stats", update_stats, ttl=48*3600)  # 48 часов
            
            logger.info(f"🏁 ЦИКЛ ОБНОВЛЕНИЯ ЗАВЕРШЕН")
            logger.info(f"📊 Статистика: {update_stats['successful_countries']}/{total_countries} стран успешно, "
                       f"{update_stats['total_directions']} направлений, "
                       f"время: {execution_time.total_seconds():.1f} сек")
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в цикле обновления: {e}")
            logger.error(traceback.format_exc())
            raise
        
        
    async def _update_country_directions(self, country_name: str, country_info: Dict) -> Dict[str, Any]:
        """
        ИСПРАВЛЕНО: Обновление направлений для одной страны с сохранением старого кеша
        
        Изменения:
        1. НЕ очищаем кеш перед обновлением
        2. Сохраняем старый кеш на случай ошибки
        3. Отдаем предпочтение реальным данным
        """
        country_id = country_info.get("country_id")
        
        if not country_id:
            return {
                "success": False,
                "error": "Нет country_id",
                "directions_count": 0,
                "execution_time_seconds": 0
            }
        
        start_time = datetime.now()
        cache_key = f"directions_with_prices_country_{country_id}"
        
        try:
            logger.info(f"🔄 Обновление направлений для {country_name} (ID: {country_id})")
            
            # КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Сохраняем старый кеш перед обновлением
            old_cache = None
            try:
                old_cache = await cache_service.get(cache_key)
                if old_cache:
                    logger.info(f"💾 Сохранен старый кеш для {country_name}: {len(old_cache)} направлений")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось получить старый кеш для {country_name}: {e}")
            
            # НЕ ОЧИЩАЕМ КЕШ! Пусть get_directions_by_country сам решает
            # await cache_service.delete(cache_key)  # <-- УБИРАЕМ ЭТУ СТРОКУ
            
            # Получаем новые направления
            # directions_service.get_directions_by_country теперь сам проверяет кеш
            # и обновляет только если нужно
            directions = await directions_service.get_directions_by_country(country_name)
            
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            # Анализ качества результатов
            with_prices = len([d for d in directions if d.get("min_price")])
            with_images = len([d for d in directions if d.get("image_link")])
            
            # Проверяем, что получили данные
            if directions:
                result = {
                    "success": True,
                    "directions_count": len(directions),
                    "execution_time_seconds": execution_time,
                    "quality_stats": {
                        "with_prices": with_prices,
                        "with_images": with_images,
                        "price_coverage": f"{(with_prices/len(directions)*100):.1f}%" if directions else "0%",
                        "image_coverage": f"{(with_images/len(directions)*100):.1f}%" if directions else "0%"
                    },
                    "cache_action": "updated" if directions != old_cache else "kept_existing"
                }
                
                logger.info(f"✅ {country_name}: {len(directions)} направлений за {execution_time:.1f}с")
                return result
            else:
                # Если новых данных нет, но есть старый кеш - используем его
                if old_cache:
                    logger.info(f"🔄 Нет новых данных для {country_name}, оставляем старый кеш: {len(old_cache)} направлений")
                    
                    # Восстанавливаем старый кеш с новым TTL
                    await cache_service.set(cache_key, old_cache, ttl=86400 * 30)
                    
                    return {
                        "success": True,
                        "directions_count": len(old_cache),
                        "execution_time_seconds": execution_time,
                        "quality_stats": {
                            "with_prices": len([d for d in old_cache if d.get("min_price")]),
                            "with_images": len([d for d in old_cache if d.get("image_link")]),
                            "price_coverage": f"{(len([d for d in old_cache if d.get('min_price')])/len(old_cache)*100):.1f}%",
                            "image_coverage": f"{(len([d for d in old_cache if d.get('image_link')])/len(old_cache)*100):.1f}%"
                        },
                        "cache_action": "kept_old_cache"
                    }
                else:
                    # Нет ни новых данных, ни старого кеша
                    return {
                        "success": False,
                        "error": "Нет данных и нет старого кеша",
                        "directions_count": 0,
                        "execution_time_seconds": execution_time,
                        "cache_action": "no_data"
                    }
            
        except Exception as e:
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            logger.error(f"❌ Ошибка обновления {country_name}: {e}")
            
            # ВАЖНО: При ошибке восстанавливаем старый кеш
            if old_cache:
                try:
                    await cache_service.set(cache_key, old_cache, ttl=86400 * 30)
                    logger.info(f"🔄 Восстановлен старый кеш для {country_name} после ошибки")
                    
                    return {
                        "success": True,  # Считаем успехом, так как данные есть
                        "directions_count": len(old_cache),
                        "execution_time_seconds": execution_time,
                        "error": str(e),
                        "cache_action": "restored_old_cache_after_error",
                        "quality_stats": {
                            "with_prices": len([d for d in old_cache if d.get("min_price")]),
                            "with_images": len([d for d in old_cache if d.get("image_link")]),
                        }
                    }
                except Exception as restore_error:
                    logger.error(f"❌ Не удалось восстановить старый кеш для {country_name}: {restore_error}")
            
            return {
                "success": False,
                "error": str(e),
                "directions_count": 0,
                "execution_time_seconds": execution_time,
                "cache_action": "failed"
            }

    # ДОПОЛНИТЕЛЬНО: Добавить метод для принудительного обновления конкретной страны
    async def force_update_country(self, country_name: str) -> Dict[str, Any]:
        """
        НОВЫЙ МЕТОД: Принудительное обновление конкретной страны с очисткой кеша
        """
        if country_name not in directions_service.COUNTRIES_MAPPING:
            return {
                "success": False,
                "error": f"Страна {country_name} не найдена"
            }
        
        country_info = directions_service.COUNTRIES_MAPPING[country_name]
        country_id = country_info.get("country_id")
        
        if not country_id:
            return {
                "success": False,
                "error": f"Нет country_id для {country_name}"
            }
        
        logger.info(f"🚀 Принудительное обновление {country_name} с очисткой кеша")
        
        try:
            # Очищаем кеш принудительно
            cache_key = f"directions_with_prices_country_{country_id}"
            await cache_service.delete(cache_key)
            logger.info(f"🗑️ Очищен кеш для {country_name}")
            
            # Обновляем данные
            return await self._update_country_directions(country_name, country_info)
            
        except Exception as e:
            logger.error(f"❌ Ошибка принудительного обновления {country_name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    async def force_update_now(self) -> Dict[str, Any]:
        """Принудительное обновление сейчас (для API)"""
        logger.info("🚀 Принудительное обновление кэша направлений")
        
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
        """Получение статуса обновления (для API)"""
        try:
            # Пытаемся получить статистику из кэша
            cached_stats = await cache_service.get("directions_cache_update_stats")
            
            if cached_stats:
                # Дополняем актуальной информацией
                status = {
                    "is_running": self.is_running,
                    "last_update": cached_stats.get("end_time"),
                    "next_update": None,
                    "update_stats": cached_stats
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
                    "update_stats": None,
                    "message": "Еще не было обновлений"
                }
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса: {e}")
            return {
                "error": str(e),
                "is_running": self.is_running
            }

# Создаем единственный экземпляр сервиса
directions_cache_update_service = DirectionsCacheUpdateService()

# Функция для запуска в фоновом режиме
async def start_directions_cache_update_task():
    """Запуск задачи обновления кэша направлений в фоне"""
    logger.info("🚀 Запуск фоновой задачи обновления кэша направлений")
    await directions_cache_update_service.start_scheduler()

# Функция для остановки
async def stop_directions_cache_update_task():
    """Остановка задачи обновления кэша направлений"""
    await directions_cache_update_service.stop_scheduler()