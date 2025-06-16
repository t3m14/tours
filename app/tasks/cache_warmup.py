import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any

from app.core.tourvisor_client import tourvisor_client
from app.services.cache_service import cache_service
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
        logger.info("Начат прогрев кэша популярных туров")
        
        try:
            # Прогреваем горящие туры
            await self._warm_hot_tours()
            
            # Прогреваем популярные направления
            await self._warm_popular_searches()
            
            # Прогреваем справочники
            await self._warm_references()
            
            logger.info("Прогрев кэша завершен успешно")
            
        except Exception as e:
            logger.error(f"Ошибка при прогреве кэша: {e}")
    
    async def _warm_hot_tours(self):
        """Прогрев горящих туров"""
        logger.info("Прогрев горящих туров...")
        
        for city in self.cities:
            try:
                # Загружаем горящие туры для каждого города
                hot_tours = await tourvisor_client.get_hot_tours(
                    city=city,
                    items=20
                )
                
                cache_key = f"hot_tours:city_{city}"
                await cache_service.set(
                    cache_key,
                    hot_tours,
                    ttl=settings.POPULAR_TOURS_CACHE_TTL
                )
                
                logger.info(f"Загружены горящие туры для города {city}")
                
                # Загружаем горящие туры по странам
                for country in self.countries:
                    country_hot_tours = await tourvisor_client.get_hot_tours(
                        city=city,
                        items=10,
                        countries=str(country)
                    )
                    
                    cache_key = f"hot_tours:city_{city}_country_{country}"
                    await cache_service.set(
                        cache_key,
                        country_hot_tours,
                        ttl=settings.POPULAR_TOURS_CACHE_TTL
                    )
                    
                    # Задержка между запросами
                    await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Ошибка при загрузке горящих туров для города {city}: {e}")
                continue
    
    async def _warm_popular_searches(self):
        """Прогрев популярных поисковых запросов"""
        logger.info("Прогрев популярных поисков...")
        
        # Базовые параметры поиска
        base_search_params = [
            {"nights_from": 7, "nights_to": 10, "adults": 2, "child": 0},
            {"nights_from": 3, "nights_to": 5, "adults": 2, "child": 0},
            {"nights_from": 10, "nights_to": 14, "adults": 2, "child": 1, "childage1": 8},
        ]
        
        # Даты на месяц вперед
        today = datetime.now()
        date_ranges = [
            {
                "datefrom": (today + timedelta(days=7)).strftime("%d.%m.%Y"),
                "dateto": (today + timedelta(days=14)).strftime("%d.%m.%Y")
            },
            {
                "datefrom": (today + timedelta(days=14)).strftime("%d.%m.%Y"),
                "dateto": (today + timedelta(days=21)).strftime("%d.%m.%Y")
            },
            {
                "datefrom": (today + timedelta(days=21)).strftime("%d.%m.%Y"),
                "dateto": (today + timedelta(days=28)).strftime("%d.%m.%Y")
            }
        ]
        
        for city in self.cities:
            for country in self.countries:
                for search_params in base_search_params:
                    for date_range in date_ranges:
                        try:
                            # Формируем параметры поиска
                            full_params = {
                                "departure": city,
                                "country": country,
                                "nightsfrom": search_params["nights_from"],
                                "nightsto": search_params["nights_to"],
                                "adults": search_params["adults"],
                                "child": search_params["child"],
                                **date_range
                            }
                            
                            if search_params.get("childage1"):
                                full_params["childage1"] = search_params["childage1"]
                            
                            # Запускаем поиск
                            request_id = await tourvisor_client.search_tours(full_params)
                            
                            # Ждем завершения поиска
                            max_wait_time = 30  # Максимум 30 секунд
                            wait_count = 0
                            
                            while wait_count < max_wait_time:
                                await asyncio.sleep(2)
                                wait_count += 2
                                
                                status_result = await tourvisor_client.get_search_status(request_id)
                                status = status_result.get("data", {}).get("status", {})
                                
                                if status.get("state") == "finished":
                                    # Получаем результаты
                                    results = await tourvisor_client.get_search_results(request_id, 1, 20)
                                    
                                    # Кэшируем результаты
                                    cache_key = f"popular_search:{city}_{country}_{search_params['nights_from']}_{search_params['nights_to']}_{search_params['adults']}_{search_params['child']}"
                                    await cache_service.set(
                                        cache_key,
                                        results,
                                        ttl=settings.POPULAR_TOURS_CACHE_TTL
                                    )
                                    
                                    logger.info(f"Закэширован поиск: город {city}, страна {country}")
                                    break
                            
                            # Задержка между поисками
                            await asyncio.sleep(1)
                            
                        except Exception as e:
                            logger.error(f"Ошибка при прогреве поиска {city}-{country}: {e}")
                            continue
    
    async def _warm_references(self):
        """Прогрев справочников"""
        logger.info("Прогрев справочников...")
        
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
                
                logger.info(f"Справочник {ref_type} закэширован")
                await asyncio.sleep(0.2)
                
            except Exception as e:
                logger.error(f"Ошибка при кэшировании справочника {ref_type}: {e}")
        
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
                
                logger.info(f"Курорты для страны {country} закэшированы")
                await asyncio.sleep(0.2)
                
            except Exception as e:
                logger.error(f"Ошибка при кэшировании курортов для страны {country}: {e}")

# Глобальная функция для запуска прогрева
async def warm_up_cache():
    """Запуск прогрева кэша"""
    warmup_service = CacheWarmupService()
    
    while True:
        try:
            await warmup_service.warm_up_cache()
            
            # Следующий прогрев через 6 часов
            await asyncio.sleep(21600)
            
        except Exception as e:
            logger.error(f"Критическая ошибка в задаче прогрева кэша: {e}")
            # При ошибке ждем 30 минут перед повтором
            await asyncio.sleep(1800)