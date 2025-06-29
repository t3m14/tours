import os
from typing import Dict, Any

class CacheUpdateConfig:
    """Конфигурация для автообновления кэша направлений"""
    
    # Основные настройки
    UPDATE_INTERVAL_HOURS: int = int(os.getenv("CACHE_UPDATE_INTERVAL_HOURS", "24"))
    BATCH_SIZE: int = int(os.getenv("CACHE_UPDATE_BATCH_SIZE", "3"))
    BATCH_PAUSE_SECONDS: int = int(os.getenv("CACHE_UPDATE_BATCH_PAUSE", "30"))
    
    # Таймауты и производительность
    SEARCH_TIMEOUT_SECONDS: int = int(os.getenv("CACHE_SEARCH_TIMEOUT", "120"))
    SEARCH_DELAY_SECONDS: float = float(os.getenv("CACHE_SEARCH_DELAY", "1.0"))
    CACHE_TTL_HOURS: int = int(os.getenv("CACHE_TTL_HOURS", "2"))
    
    # Качество данных
    REQUIRE_REAL_PRICES: bool = os.getenv("CACHE_REQUIRE_REAL_PRICES", "false").lower() == "true"
    MIN_SUCCESS_RATE: float = float(os.getenv("CACHE_MIN_SUCCESS_RATE", "80.0"))
    
    # Уведомления и мониторинг
    ENABLE_NOTIFICATIONS: bool = os.getenv("CACHE_ENABLE_NOTIFICATIONS", "false").lower() == "true"
    NOTIFICATION_EMAIL: str = os.getenv("CACHE_NOTIFICATION_EMAIL", "")
    NOTIFICATION_WEBHOOK: str = os.getenv("CACHE_NOTIFICATION_WEBHOOK", "")
    
    # Режимы работы
    AUTO_START: bool = os.getenv("CACHE_AUTO_START", "true").lower() == "true"
    RETRY_FAILED_COUNTRIES: bool = os.getenv("CACHE_RETRY_FAILED", "true").lower() == "true"
    
    @classmethod
    def get_all_settings(cls) -> Dict[str, Any]:
        """Получить все настройки"""
        return {
            "update_interval_hours": cls.UPDATE_INTERVAL_HOURS,
            "batch_size": cls.BATCH_SIZE,
            "batch_pause_seconds": cls.BATCH_PAUSE_SECONDS,
            "search_timeout_seconds": cls.SEARCH_TIMEOUT_SECONDS,
            "search_delay_seconds": cls.SEARCH_DELAY_SECONDS,
            "cache_ttl_hours": cls.CACHE_TTL_HOURS,
            "require_real_prices": cls.REQUIRE_REAL_PRICES,
            "min_success_rate": cls.MIN_SUCCESS_RATE,
            "enable_notifications": cls.ENABLE_NOTIFICATIONS,
            "auto_start": cls.AUTO_START,
            "retry_failed_countries": cls.RETRY_FAILED_COUNTRIES
        }

# app/tasks/directions_cache_update.py - ОБНОВЛЕННАЯ ВЕРСИЯ С КОНФИГУРАЦИЕЙ

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any
import traceback

from app.services.directions_service import directions_service
from app.services.cache_service import cache_service
from app.config.cache_update import CacheUpdateConfig
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class DirectionsCacheUpdateService:
    """Сервис для автоматического обновления кэша направлений с настройками"""
    
    def __init__(self):
        # Загружаем конфигурацию
        self.config = CacheUpdateConfig()
        
        # Настройки из конфигурации
        self.update_interval = self.config.UPDATE_INTERVAL_HOURS * 3600  # в секундах
        self.countries_batch_size = self.config.BATCH_SIZE
        self.batch_pause = self.config.BATCH_PAUSE_SECONDS
        
        # Состояние
        self.is_running = False
        self.last_update = None
        self.update_stats = {}
        self.current_batch = None
        self.current_country = None
        
        logger.info(f"🔧 Инициализация с настройками: обновление каждые {self.config.UPDATE_INTERVAL_HOURS}ч, "
                   f"батч {self.config.BATCH_SIZE} стран, пауза {self.config.BATCH_PAUSE_SECONDS}с")
    
    async def start_scheduler(self):
        """Запуск планировщика с учетом конфигурации"""
        if self.is_running:
            logger.warning("⚠️ Планировщик уже запущен")
            return
            
        self.is_running = True
        logger.info(f"🕒 Запуск планировщика обновления кэша направлений (интервал: {self.config.UPDATE_INTERVAL_HOURS}ч)")
        
        # Если включен автостарт, запускаем первое обновление сразу
        if self.config.AUTO_START:
            logger.info("🚀 Автостарт включен - запуск первого обновления")
            try:
                await self._run_update_cycle()
            except Exception as e:
                logger.error(f"❌ Ошибка в автостарте: {e}")
        
        while self.is_running:
            try:
                await asyncio.sleep(self.update_interval)
                
                if self.is_running:  # Проверяем снова после ожидания
                    await self._run_update_cycle()
                
            except asyncio.CancelledError:
                logger.info("🛑 Планировщик обновления кэша направлений остановлен")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в планировщике обновления кэша: {e}")
                logger.error(traceback.format_exc())
                
                # Уведомление об ошибке
                await self._send_error_notification(e)
                
                # Ждем 1 час перед повтором при ошибке
                await asyncio.sleep(3600)
    
    async def _run_update_cycle(self):
        """Выполнение одного цикла обновления с улучшенной логикой"""
        start_time = datetime.now()
        logger.info(f"🔄 НАЧАЛО ЦИКЛА ОБНОВЛЕНИЯ КЭША НАПРАВЛЕНИЙ ({start_time.strftime('%Y-%m-%d %H:%M:%S')})")
        
        try:
            # Получаем список всех стран
            countries_list = list(directions_service.COUNTRIES_MAPPING.items())
            total_countries = len(countries_list)
            
            logger.info(f"🌍 Будет обновлено {total_countries} стран (батчами по {self.countries_batch_size})")
            
            # Статистика обновления
            update_stats = {
                "start_time": start_time,
                "total_countries": total_countries,
                "processed_countries": 0,
                "successful_countries": 0,
                "failed_countries": 0,
                "total_directions": 0,
                "countries_details": {},
                "config": self.config.get_all_settings()
            }
            
            # Обновляем страны батчами
            for i in range(0, total_countries, self.countries_batch_size):
                batch = countries_list[i:i + self.countries_batch_size]
                batch_num = i//self.countries_batch_size + 1
                total_batches = (total_countries + self.countries_batch_size - 1)//self.countries_batch_size
                
                logger.info(f"📦 Обработка батча {batch_num}/{total_batches} ({len(batch)} стран)")
                self.current_batch = batch_num
                
                # Создаем задачи для параллельного выполнения батча
                batch_tasks = []
                for country_name, country_info in batch:
                    task = asyncio.create_task(
                        self._update_country_directions_with_retry(country_name, country_info)
                    )
                    batch_tasks.append((country_name, task))
                
                # Ждем завершения батча
                for country_name, task in batch_tasks:
                    self.current_country = country_name
                    try:
                        result = await task
                        update_stats["processed_countries"] += 1
                        
                        if result["success"]:
                            update_stats["successful_countries"] += 1
                            update_stats["total_directions"] += result["directions_count"]
                        else:
                            update_stats["failed_countries"] += 1
                        
                        update_stats["countries_details"][country_name] = result
                        
                        logger.info(f"✅ {country_name}: {result['directions_count']} направлений "
                                  f"({result['execution_time_seconds']:.1f}с)")
                        
                    except Exception as e:
                        update_stats["processed_countries"] += 1
                        update_stats["failed_countries"] += 1
                        update_stats["countries_details"][country_name] = {
                            "success": False,
                            "error": str(e),
                            "directions_count": 0,
                            "execution_time_seconds": 0
                        }
                        logger.error(f"❌ Ошибка обновления {country_name}: {e}")
                
                # Пауза между батчами
                if i + self.countries_batch_size < total_countries:
                    logger.info(f"⏸️ Пауза между батчами ({self.batch_pause} сек)")
                    await asyncio.sleep(self.batch_pause)
            
            # Завершение цикла
            end_time = datetime.now()
            execution_time = end_time - start_time
            
            update_stats["end_time"] = end_time
            update_stats["execution_time_seconds"] = execution_time.total_seconds()
            update_stats["success_rate"] = (update_stats["successful_countries"] / total_countries * 100) if total_countries > 0 else 0
            
            self.last_update = end_time
            self.update_stats = update_stats
            self.current_batch = None
            self.current_country = None
            
            # Сохраняем статистику в кэш
            await cache_service.set("directions_cache_update_stats", update_stats, ttl=48*3600)
            
            # Проверяем качество результатов
            success_rate = update_stats["success_rate"]
            if success_rate < self.config.MIN_SUCCESS_RATE:
                logger.warning(f"⚠️ Низкий процент успешных обновлений: {success_rate:.1f}% < {self.config.MIN_SUCCESS_RATE}%")
                await self._send_warning_notification(f"Низкий процент успешных обновлений: {success_rate:.1f}%")
            
            logger.info(f"🏁 ЦИКЛ ОБНОВЛЕНИЯ ЗАВЕРШЕН")
            logger.info(f"📊 Итого: {update_stats['successful_countries']}/{total_countries} стран, "
                       f"{update_stats['total_directions']} направлений, "
                       f"время: {execution_time.total_seconds():.1f} сек, "
                       f"успешность: {success_rate:.1f}%")
            
            # Отправляем уведомление об успешном завершении
            await self._send_success_notification(update_stats)
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка в цикле обновления: {e}")
            logger.error(traceback.format_exc())
            await self._send_error_notification(e)
            raise
    
    async def _update_country_directions_with_retry(self, country_name: str, country_info: Dict) -> Dict[str, Any]:
        """Обновление направлений для одной страны с повторными попытками"""
        max_retries = 2 if self.config.RETRY_FAILED_COUNTRIES else 1
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info(f"🔄 Повторная попытка {attempt + 1}/{max_retries} для {country_name}")
                    await asyncio.sleep(10)  # Пауза перед повтором
                
                result = await self._update_country_directions(country_name, country_info)
                
                # Если успешно, возвращаем результат
                if result["success"]:
                    return result
                
                # Если не последняя попытка, продолжаем
                if attempt < max_retries - 1:
                    logger.warning(f"⚠️ Неудачная попытка {attempt + 1} для {country_name}: {result.get('error', 'Unknown error')}")
                    continue
                
                return result
                
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.warning(f"⚠️ Ошибка попытки {attempt + 1} для {country_name}: {e}")
                    continue
                else:
                    raise
    
    async def _update_country_directions(self, country_name: str, country_info: Dict) -> Dict[str, Any]:
        """Обновление направлений для одной страны"""
        country_id = country_info.get("country_id")
        
        if not country_id:
            return {
                "success": False,
                "error": "Нет country_id",
                "directions_count": 0,
                "execution_time_seconds": 0
            }
        
        start_time = datetime.now()
        
        try:
            logger.debug(f"🔄 Обновление направлений для {country_name} (ID: {country_id})")
            
            # Очищаем кэш для этой страны
            cache_key = f"directions_with_prices_country_{country_id}"
            await cache_service.delete(cache_key)
            
            # Получаем новые направления
            directions = await directions_service.get_directions_by_country(country_name)
            
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            # Анализ качества результатов
            with_prices = len([d for d in directions if d.get("min_price")])
            with_images = len([d for d in directions if d.get("image_link")])
            real_prices = len([d for d in directions if d.get("min_price") and not str(d.get("min_price", "")).endswith("000")])
            
            # Проверка качества если требуется
            quality_check_passed = True
            if self.config.REQUIRE_REAL_PRICES and directions:
                real_price_percentage = (real_prices / len(directions)) * 100
                if real_price_percentage < 50:  # Менее 50% реальных цен
                    quality_check_passed = False
            
            result = {
                "success": quality_check_passed,
                "directions_count": len(directions),
                "execution_time_seconds": execution_time,
                "quality_stats": {
                    "with_prices": with_prices,
                    "with_images": with_images,
                    "real_prices": real_prices,
                    "price_coverage": f"{(with_prices/len(directions)*100):.1f}%" if directions else "0%",
                    "image_coverage": f"{(with_images/len(directions)*100):.1f}%" if directions else "0%",
                    "real_price_coverage": f"{(real_prices/len(directions)*100):.1f}%" if directions else "0%"
                }
            }
            
            if not quality_check_passed:
                result["error"] = f"Качество данных не соответствует требованиям (реальные цены: {real_prices}/{len(directions)})"
            
            return result
            
        except Exception as e:
            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()
            
            logger.error(f"❌ Ошибка обновления {country_name}: {e}")
            
            return {
                "success": False,
                "error": str(e),
                "directions_count": 0,
                "execution_time_seconds": execution_time
            }
    
    async def _send_success_notification(self, stats: Dict[str, Any]):
        """Отправка уведомления об успешном обновлении"""
        if not self.config.ENABLE_NOTIFICATIONS:
            return
        
        try:
            message = (f"✅ Обновление кэша направлений завершено успешно\n"
                      f"📊 {stats['successful_countries']}/{stats['total_countries']} стран\n"
                      f"🎯 {stats['total_directions']} направлений\n"
                      f"⏱️ {stats['execution_time_seconds']:.1f} секунд\n"
                      f"📈 Успешность: {stats['success_rate']:.1f}%")
            
            await self._send_notification("Кэш направлений обновлен", message)
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления об успехе: {e}")
    
    async def _send_warning_notification(self, warning: str):
        """Отправка предупреждения"""
        if not self.config.ENABLE_NOTIFICATIONS:
            return
        
        try:
            await self._send_notification("Предупреждение обновления кэша", f"⚠️ {warning}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки предупреждения: {e}")
    
    async def _send_error_notification(self, error: Exception):
        """Отправка уведомления об ошибке"""
        if not self.config.ENABLE_NOTIFICATIONS:
            return
        
        try:
            message = f"❌ Ошибка обновления кэша направлений: {str(error)}"
            await self._send_notification("Ошибка обновления кэша", message)
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления об ошибке: {e}")
    
    async def _send_notification(self, subject: str, message: str):
        """Отправка уведомления (email или webhook)"""
        try:
            # Email уведомление
            if self.config.NOTIFICATION_EMAIL:
                # Здесь можно добавить отправку email
                logger.info(f"📧 Email уведомление: {subject}")
            
            # Webhook уведомление
            if self.config.NOTIFICATION_WEBHOOK:
                # Здесь можно добавить отправку webhook
                logger.info(f"🔔 Webhook уведомление: {subject}")
            
            logger.debug(f"📨 Уведомление: {subject} - {message}")
            
        except Exception as e:
            logger.error(f"❌ Ошибка отправки уведомления: {e}")

# Остальные методы остаются без изменений...
# (get_update_status, force_update_now и т.д.)

# Создаем единственный экземпляр сервиса
directions_cache_update_service = DirectionsCacheUpdateService()