import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any

from app.core.tourvisor_client import tourvisor_client
from app.services.cache_service import cache_service
from app.services.directions_service import directions_service
from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class CacheWarmupService:
    """Сервис для прогрева кэша популярными турами"""
    
    def __init__(self):
        self.countries = settings.POPULAR_COUNTRIES
        self.cities = settings.DEPARTURE_CITIES
        
    async def warm_up_cache(self):
        """Основной метод прогрева кэша"""
        logger.info("🔥 Начат прогрев кэша")
        
        try:
            # Прогреваем справочники (быстро и полезно)
            await self._warm_references()
            
            # Прогреваем направления с фотографиями (заменяет горящие туры)
            await self._warm_directions()
            
            # Прогреваем популярные поисковые запросы (только если есть время)
            await self._warm_popular_searches_limited()
            
            logger.info("✅ Прогрев кэша завершен успешно")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при прогреве кэша: {e}")
    
    async def _warm_directions(self):
        """Прогрев направлений с фотографиями отелей"""
        logger.info("🌍 Прогрев направлений...")
        
        try:
            # Используем новый DirectionsService для прогрева
            await directions_service.refresh_directions()
            logger.info("✅ Направления с фотографиями обновлены")
            
        except Exception as e:
            logger.error(f"🌍 Ошибка при прогреве направлений: {e}")
    
    async def _warm_popular_searches_limited(self):
        """Ограниченный прогрев популярных поисковых запросов"""
        logger.info("🔍 Прогрев популярных поисков (ограниченно)...")
        
        # Только самые популярные комбинации для экономии времени
        search_combinations = [
            # Египет из Москвы на неделю
            {
                "departure": 1, "country": 1,
                "nightsfrom": 7, "nightsto": 10,
                "adults": 2, "child": 0
            },
            # Турция из Москвы на неделю  
            {
                "departure": 1, "country": 4,
                "nightsfrom": 7, "nightsto": 10,
                "adults": 2, "child": 0
            },
            # Таиланд из Москвы на 10 дней
            {
                "departure": 1, "country": 22,
                "nightsfrom": 10, "nightsto": 14,
                "adults": 2, "child": 0
            }
        ]
        
        # Даты на ближайшие 2 недели
        today = datetime.now()
        date_range = {
            "datefrom": (today + timedelta(days=7)).strftime("%d.%m.%Y"),
            "dateto": (today + timedelta(days=14)).strftime("%d.%m.%Y")
        }
        
        for i, search_params in enumerate(search_combinations):
            try:
                full_params = {**search_params, **date_range}
                
                logger.info(f"🔍 Поиск {i+1}/3: страна {search_params['country']} из города {search_params['departure']}")
                
                # Запускаем поиск
                request_id = await tourvisor_client.search_tours(full_params)
                
                # Ждем завершения поиска (максимум 15 секунд)
                max_wait_time = 15
                wait_count = 0
                
                while wait_count < max_wait_time:
                    await asyncio.sleep(2)
                    wait_count += 2
                    
                    status_result = await tourvisor_client.get_search_status(request_id)
                    status = status_result.get("data", {}).get("status", {})
                    
                    if status.get("state") == "finished":
                        # Получаем результаты
                        results = await tourvisor_client.get_search_results(request_id, 1, 10)
                        
                        # Кэшируем результаты
                        cache_key = f"popular_search:{search_params['country']}_{search_params['departure']}_{search_params['nightsfrom']}"
                        await cache_service.set(
                            cache_key,
                            results,
                            ttl=settings.POPULAR_TOURS_CACHE_TTL
                        )
                        
                        logger.info(f"✅ Закэширован поиск: страна {search_params['country']}")
                        break
                
                # Задержка между поисками
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"🔍 Ошибка при прогреве поиска {i+1}: {e}")
                continue
    
    async def _warm_references(self):
        """Прогрев справочников"""
        logger.info("📋 Прогрев справочников...")
        
        reference_types = [
            "departure",
            "country", 
            "meal",
            "stars",
            "operator",
            "services"
        ]
        
        for ref_type in reference_types:
            try:
                data = await tourvisor_client.get_references(ref_type)
                
                cache_key = f"reference:{ref_type}"
                await cache_service.set(
                    cache_key,
                    data,
                    ttl=86400  # 24 часа для справочников
                )
                
                logger.info(f"📋 Справочник {ref_type} закэширован")
                await asyncio.sleep(0.2)
                
            except Exception as e:
                logger.error(f"📋 Ошибка при кэшировании справочника {ref_type}: {e}")
        
        # Кэшируем курорты для популярных стран
        for country in self.countries:
            try:
                regions_data = await tourvisor_client.get_references(
                    "region",
                    regcountry=country
                )
                
                cache_key = f"reference:regions_country_{country}"
                await cache_service.set(
                    cache_key,
                    regions_data,
                    ttl=86400
                )
                
                logger.info(f"📋 Курорты для страны {country} закэшированы")
                await asyncio.sleep(0.2)
                
            except Exception as e:
                logger.error(f"📋 Ошибка при кэшировании курортов для страны {country}: {e}")

# Глобальная функция для запуска прогрева
async def warm_up_cache():
    """Запуск прогрева кэша"""
    warmup_service = CacheWarmupService()
    
    while True:
        try:
            await warmup_service.warm_up_cache()
            
            logger.info("😴 Следующий прогрев кэша через 6 часов")
            # Следующий прогрев через 6 часов
            await asyncio.sleep(21600)
            
        except Exception as e:
            logger.error(f"💥 Критическая ошибка в задаче прогрева кэша: {e}")
            # При ошибке ждем 30 минут перед повтором
            await asyncio.sleep(1800)