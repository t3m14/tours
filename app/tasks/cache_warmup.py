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
        logger.info("🔥 Начат прогрев кэша популярных туров")
        
        try:
            # Сначала прогреваем справочники (они быстрые)
            await self._warm_references()
            
            # Затем пытаемся получить горящие туры (если доступны)
            await self._warm_hot_tours()
            
            # И только потом делаем тяжелые поисковые запросы
            await self._warm_popular_searches()
            
            logger.info("✅ Прогрев кэша завершен успешно")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при прогреве кэша: {e}")
    
    async def _warm_references(self):
        """Прогрев справочников (быстро)"""
        logger.info("📚 Прогрев справочников...")
        
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
                
                logger.info(f"📖 Справочник {ref_type} закэширован")
                await asyncio.sleep(0.2)
                
            except Exception as e:
                logger.error(f"❌ Ошибка при кэшировании справочника {ref_type}: {e}")
        
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
                
                logger.info(f"🏖️ Курорты для страны {country} закэшированы")
                await asyncio.sleep(0.2)
                
            except Exception as e:
                logger.error(f"❌ Ошибка при кэшировании курортов для страны {country}: {e}")
    
    async def _warm_hot_tours(self):
        """Прогрев горящих туров (если доступны)"""
        logger.info("🔥 Прогрев горящих туров...")
        
        # Проверяем доступность горящих туров
        hot_tours_available = await self._check_hot_tours_availability()
        
        if not hot_tours_available:
            logger.warning("⚠️ Горящие туры недоступны, пропускаем этот этап")
            return
        
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
                
                logger.info(f"🔥 Горящие туры для города {city} загружены")
                
                # Загружаем горящие туры по странам (только если общие работают)
                if hot_tours.get("hotcount", 0) > 0:
                    for country in self.countries:
                        try:
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
                        except Exception as country_error:
                            logger.warning(f"⚠️ Ошибка горящих туров {city}-{country}: {country_error}")
                            continue
                
            except Exception as e:
                logger.error(f"❌ Ошибка при загрузке горящих туров для города {city}: {e}")
                continue
    
    async def _check_hot_tours_availability(self) -> bool:
        """Проверка доступности горящих туров"""
        try:
            # Пробуем получить несколько горящих туров из Москвы
            test_hot_tours = await tourvisor_client.get_hot_tours(
                city=1,  # Москва
                items=3
            )
            
            hot_count = test_hot_tours.get("hotcount", 0)
            logger.info(f"🧪 Тест горящих туров: найдено {hot_count} туров")
            
            return hot_count > 0
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка проверки горящих туров: {e}")
            return False
    
    async def _warm_popular_searches(self):
        """Прогрев популярных поисковых запросов (медленно)"""
        logger.info("🔍 Прогрев популярных поисков...")
        
        # Базовые параметры поиска (упрощенные)
        base_search_params = [
            {"nights_from": 7, "nights_to": 10, "adults": 2, "child": 0},
            {"nights_from": 10, "nights_to": 14, "adults": 2, "child": 0},
        ]
        
        # Даты на ближайшие 2 недели (не на месяц, чтобы быстрее)
        today = datetime.now()
        date_ranges = [
            {
                "datefrom": (today + timedelta(days=7)).strftime("%d.%m.%Y"),
                "dateto": (today + timedelta(days=14)).strftime("%d.%m.%Y")
            },
            {
                "datefrom": (today + timedelta(days=14)).strftime("%d.%m.%Y"),
                "dateto": (today + timedelta(days=21)).strftime("%d.%m.%Y")
            }
        ]
        
        search_count = 0
        max_searches = 6  # Ограничиваем количество поисков
        
        for city in self.cities:
            for country in self.countries:
                for search_params in base_search_params[:1]:  # Только первый вариант
                    for date_range in date_ranges[:1]:  # Только первый диапазон дат
                        
                        if search_count >= max_searches:
                            logger.info(f"✋ Достигнут лимит поисков ({max_searches})")
                            return
                        
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
                            
                            logger.info(f"🔍 Поиск {search_count + 1}/{max_searches}: {country} из {city}")
                            
                            # Запускаем поиск
                            request_id = await tourvisor_client.search_tours(full_params)
                            
                            # Ждем завершения поиска (сокращенное время)
                            search_completed = await self._wait_for_search_completion(request_id, max_wait=20)
                            
                            if search_completed:
                                # Получаем результаты
                                results = await tourvisor_client.get_search_results(request_id, 1, 15)
                                
                                # Кэшируем результаты
                                cache_key = f"popular_search:{city}_{country}_{search_params['nights_from']}_{search_params['nights_to']}"
                                await cache_service.set(
                                    cache_key,
                                    results,
                                    ttl=settings.POPULAR_TOURS_CACHE_TTL
                                )
                                
                                logger.info(f"✅ Поиск {city}-{country} закэширован")
                            else:
                                logger.warning(f"⏰ Поиск {city}-{country} не завершился вовремя")
                            
                            search_count += 1
                            
                            # Задержка между поисками
                            await asyncio.sleep(2)
                            
                        except Exception as e:
                            logger.error(f"❌ Ошибка при прогреве поиска {city}-{country}: {e}")
                            search_count += 1
                            continue
    
    async def _wait_for_search_completion(self, request_id: str, max_wait: int = 20) -> bool:
        """Ожидание завершения поиска с таймаутом"""
        try:
            for attempt in range(max_wait):
                await asyncio.sleep(1)
                
                status_result = await tourvisor_client.get_search_status(request_id)
                status = status_result.get("data", {}).get("status", {})
                
                state = status.get("state", "searching")
                progress = status.get("progress", 0)
                hotels_found = status.get("hotelsfound", 0)
                
                # Считаем поиск завершенным если:
                # 1. Статус "finished"
                # 2. Прогресс >= 70% и найдены отели
                # 3. Прошло >= 15 секунд и найдены отели
                if (state == "finished" or 
                    (progress >= 70 and hotels_found > 0) or
                    (attempt >= 15 and hotels_found > 0)):
                    
                    logger.debug(f"✅ Поиск завершен: состояние={state}, прогресс={progress}%, отелей={hotels_found}")
                    return True
            
            logger.debug(f"⏰ Таймаут поиска {request_id}")
            return False
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка ожидания поиска {request_id}: {e}")
            return False

# Глобальная функция для запуска прогрева
async def warm_up_cache():
    """Запуск прогрева кэша"""
    warmup_service = CacheWarmupService()
    
    # Первый прогрев при старте
    await warmup_service.warm_up_cache()
    
    while True:
        try:
            # Следующий прогрев через 6 часов
            logger.info("😴 Следующий прогрев кэша через 6 часов...")
            await asyncio.sleep(21600)
            
            await warmup_service.warm_up_cache()
            
        except Exception as e:
            logger.error(f"💥 Критическая ошибка в задаче прогрева кэша: {e}")
            # При ошибке ждем 30 минут перед повтором
            await asyncio.sleep(1800)