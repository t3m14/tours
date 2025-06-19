# app/tasks/mass_directions_update.py

import asyncio
from datetime import datetime, timedelta

from app.services.mass_directions_collector import mass_directions_collector
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class MassDirectionsUpdateService:
    """Сервис для периодического обновления направлений в фоновом режиме"""
    
    def __init__(self):
        self.collector = mass_directions_collector
        
    async def check_and_update_directions(self):
        """Проверка и обновление направлений если необходимо"""
        try:
            logger.info("🌍 Проверяем состояние направлений...")
            
            # Получаем статус текущих направлений
            status = await self.collector.get_collection_status()
            master_cache = status.get("master_cache", {})
            
            should_update = False
            reason = ""
            
            # Проверяем существование кэша
            if not master_cache.get("exists"):
                should_update = True
                reason = "Кэш направлений отсутствует"
            
            # Проверяем возраст данных
            elif master_cache.get("last_collection"):
                try:
                    collection_date = datetime.fromisoformat(master_cache["last_collection"])
                    days_old = (datetime.now() - collection_date).days
                    
                    if days_old > 30:  # Обновляем раз в месяц
                        should_update = True
                        reason = f"Данные устарели ({days_old} дней)"
                except:
                    should_update = True
                    reason = "Не удалось определить возраст данных"
            
            # Проверяем количество направлений
            elif master_cache.get("directions_count", 0) < 10:
                should_update = True
                reason = f"Мало направлений ({master_cache.get('directions_count', 0)})"
            
            if should_update:
                logger.info(f"🔄 Запускаем обновление направлений. Причина: {reason}")
                await self._perform_directions_update()
            else:
                directions_count = master_cache.get("directions_count", 0)
                logger.info(f"✅ Направления актуальны ({directions_count} направлений)")
                
        except Exception as e:
            logger.error(f"❌ Ошибка при проверке направлений: {e}")
    
    async def _perform_directions_update(self):
        """Выполнение обновления направлений"""
        try:
            logger.info("🌍 Начинаем массовый сбор направлений...")
            
            # Запускаем массовый сбор
            directions = await self.collector.collect_all_directions(force_rebuild=True)
            
            if directions:
                logger.info(f"✅ Обновление завершено: {len(directions)} направлений")
                
                # Логируем статистику
                real_photos = len([d for d in directions if not d.image_link.startswith("https://via.placeholder.com")])
                avg_price = sum(d.min_price for d in directions) / len(directions) if directions else 0
                
                logger.info(f"📊 Статистика: реальных фото {real_photos}/{len(directions)}, средняя цена {avg_price:.0f}")
            else:
                logger.warning("⚠️ Обновление не дало результатов")
                
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении направлений: {e}")

# Глобальная функция для запуска фоновой задачи
async def periodic_directions_update():
    """Периодическое обновление направлений"""
    service = MassDirectionsUpdateService()
    
    # Первая проверка через 10 минут после запуска (чтобы не перегружать старт)
    await asyncio.sleep(600)
    
    while True:
        try:
            await service.check_and_update_directions()
            
            # Следующая проверка через 24 часа
            logger.info("😴 Следующая проверка направлений через 24 часа")
            await asyncio.sleep(86400)
            
        except Exception as e:
            logger.error(f"💥 Критическая ошибка в задаче обновления направлений: {e}")
            # При ошибке ждем 2 часа перед повтором
            await asyncio.sleep(7200)

# Функция для запуска одноразового массового сбора при старте приложения
async def initial_directions_collection():
    """Одноразовый сбор направлений при старте приложения"""
    try:
        logger.info("🚀 Проверяем необходимость первоначального сбора направлений...")
        
        service = MassDirectionsUpdateService()
        
        # Проверяем состояние кэша
        status = await mass_directions_collector.get_collection_status()
        master_cache = status.get("master_cache", {})
        
        if not master_cache.get("exists") or master_cache.get("directions_count", 0) < 5:
            logger.info("🌍 Запускаем первоначальный сбор направлений...")
            
            # Запускаем сбор в фоновом режиме
            asyncio.create_task(service._perform_directions_update())
            
            logger.info("✅ Первоначальный сбор направлений запущен в фоне")
        else:
            directions_count = master_cache.get("directions_count", 0)
            logger.info(f"✅ Направления уже существуют ({directions_count} шт.), сбор не требуется")
            
    except Exception as e:
        logger.error(f"❌ Ошибка при первоначальном сборе направлений: {e}")
        
        # В случае ошибки запускаем fallback сбор
        try:
            logger.info("🎭 Запускаем fallback создание направлений...")
            fallback_directions = await mass_directions_collector._get_fallback_directions()
            
            await mass_directions_collector._save_master_directions(
                fallback_directions, 
                [{"id": i, "name": d.name} for i, d in enumerate(fallback_directions, 1)]
            )
            
            logger.info(f"✅ Создано {len(fallback_directions)} fallback направлений")
            
        except Exception as fallback_error:
            logger.error(f"❌ Ошибка даже при создании fallback направлений: {fallback_error}")