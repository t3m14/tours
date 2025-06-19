# app/services/directions_service.py

import asyncio
from typing import List
from datetime import datetime

from app.services.cache_service import cache_service
from app.services.mass_directions_collector import mass_directions_collector
from app.models.tour import DirectionInfo
from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class DirectionsService:
    """Обновленный сервис для работы с направлениями с использованием массового сборщика"""
    
    def __init__(self):
        self.cache = cache_service
        self.mass_collector = mass_directions_collector
        
        # Ключи кэша для API ответов (краткосрочный кэш)
        self.API_CACHE_KEY = "api_directions_response"
        self.API_CACHE_TTL = 3600  # 1 час
    
    async def get_directions_with_prices(self) -> List[DirectionInfo]:
        """
        Получение списка направлений с минимальными ценами и фотографиями отелей
        Сначала проверяет API кэш, потом долгосрочный кэш, потом запускает сбор
        """
        
        # 1. Проверяем краткосрочный API кэш
        api_cached = await self.cache.get(self.API_CACHE_KEY)
        if api_cached:
            logger.info(f"📸 Возвращено {len(api_cached)} направлений из API кэша")
            return [DirectionInfo(**item) for item in api_cached]
        
        # 2. Проверяем долгосрочный кэш из массового сборщика
        master_directions = await self.mass_collector._get_cached_master_directions()
        if master_directions and len(master_directions) >= 10:
            logger.info(f"🌍 Возвращено {len(master_directions)} направлений из долгосрочного кэша")
            
            # Сохраняем в API кэш для быстрого доступа
            await self._cache_api_response(master_directions)
            return master_directions
        
        # 3. Если нет кэша - запускаем сбор
        logger.info("🔄 Нет кэшированных направлений, запускаем сбор...")
        return await self.collect_all_directions()

    async def collect_all_directions(self, force_rebuild: bool = False) -> List[DirectionInfo]:
        """
        Запуск массового сбора всех направлений
        
        Args:
            force_rebuild: Принудительный пересбор даже если кэш существует
        """
        logger.info("🌍 Запуск массового сбора направлений")
        
        try:
            directions = await self.mass_collector.collect_all_directions(force_rebuild)
            
            if directions:
                # Сохраняем в API кэш для быстрого доступа
                await self._cache_api_response(directions)
                logger.info(f"✅ Массовый сбор завершен: {len(directions)} направлений")
            
            return directions
            
        except Exception as e:
            logger.error(f"❌ Ошибка при массовом сборе направлений: {e}")
            # Возвращаем fallback направления
            return await self.mass_collector._get_fallback_directions()

    async def refresh_directions(self) -> List[DirectionInfo]:
        """Принудительное обновление направлений"""
        logger.info("🔄 Принудительное обновление направлений")
        
        # Очищаем API кэш
        await self.cache.delete(self.API_CACHE_KEY)
        
        # Запускаем принудительный пересбор
        return await self.collect_all_directions(force_rebuild=True)

    async def get_directions_subset(self, limit: int = None) -> List[DirectionInfo]:
        """
        Получение подмножества направлений (например, только популярные)
        
        Args:
            limit: Максимальное количество направлений для возврата
        """
        all_directions = await self.get_directions_with_prices()
        
        if limit and len(all_directions) > limit:
            # Берем популярные страны первыми
            popular_countries = ["Египет", "Турция", "Таиланд", "Греция", "ОАЭ", "Мальдивы"]
            
            popular_directions = []
            other_directions = []
            
            for direction in all_directions:
                if direction.name in popular_countries:
                    popular_directions.append(direction)
                else:
                    other_directions.append(direction)
            
            # Сначала популярные, потом остальные
            limited_directions = (popular_directions + other_directions)[:limit]
            
            logger.info(f"📊 Возвращено {len(limited_directions)} из {len(all_directions)} направлений")
            return limited_directions
        
        return all_directions

    async def get_directions_status(self) -> dict:
        """Получение статуса системы направлений"""
        try:
            # Получаем статус от массового сборщика
            mass_status = await self.mass_collector.get_collection_status()
            
            # Добавляем информацию об API кэше
            api_cached = await self.cache.get(self.API_CACHE_KEY)
            
            return {
                **mass_status,
                "api_cache": {
                    "exists": bool(api_cached),
                    "directions_count": len(api_cached) if api_cached else 0,
                    "ttl_hours": self.API_CACHE_TTL // 3600
                },
                "endpoints": {
                    "get_directions": "/api/v1/tours/directions",
                    "collect_all": "/api/v1/tours/directions/collect-all",
                    "refresh_directions": "/api/v1/tours/directions/refresh", 
                    "check_status": "/api/v1/tours/directions/status",
                    "clear_cache": "/api/v1/tours/directions/clear-cache"
                },
                "features": {
                    "mass_country_collection": True,
                    "long_term_caching": True,
                    "real_hotel_photos": True,
                    "min_prices_from_search": True,
                    "api_cache_ttl_hours": self.API_CACHE_TTL // 3600,
                    "master_cache_ttl_days": mass_status.get("cache_info", {}).get("ttl_days", 30),
                    "parallel_processing": True,
                    "progress_tracking": True
                }
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "recommendation": "use_collect_all_endpoint"
            }

    async def fix_cache_issues(self) -> dict:
        """Исправление проблем с кэшированием направлений"""
        try:
            logger.info("🔧 Исправляем проблемы с кэшем направлений")
            
            # 1. Очищаем все кэши направлений
            clear_result = await self.mass_collector.clear_all_directions_cache()
            
            # 2. Запускаем массовый сбор
            logger.info("🔧 Запускаем массовый сбор направлений...")
            new_directions = await self.collect_all_directions(force_rebuild=True)
            
            # 3. Проверяем результат
            api_cache_check = await self.cache.get(self.API_CACHE_KEY)
            master_cache_check = await self.mass_collector._get_cached_master_directions()
            
            return {
                "success": True,
                "actions_performed": [
                    f"Очищены ключи кэша: {clear_result.get('cleared_keys', [])}",
                    f"Выполнен массовый сбор: {len(new_directions)} направлений",
                    f"API кэш {'создан' if api_cache_check else 'НЕ создан'}",
                    f"Долгосрочный кэш {'создан' if master_cache_check else 'НЕ создан'}"
                ],
                "generated_directions": [
                    {
                        "name": d.name,
                        "has_real_photo": not d.image_link.startswith("https://via.placeholder.com"),
                        "price": d.min_price
                    }
                    for d in new_directions[:10]  # Первые 10 для примера
                ],
                "statistics": {
                    "total_directions": len(new_directions),
                    "with_real_photos": len([d for d in new_directions if not d.image_link.startswith("https://via.placeholder.com")]),
                    "average_price": sum(d.min_price for d in new_directions) / len(new_directions) if new_directions else 0
                },
                "recommendations": [
                    "Проверьте endpoints /api/v1/tours/directions",
                    "Используйте /api/v1/tours/directions/status для мониторинга",
                    "Массовый сбор выполняется автоматически при необходимости"
                ]
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка при исправлении кэша: {e}")
            return {
                "success": False,
                "error": str(e),
                "recommendations": [
                    "Проверьте подключение к TourVisor API",
                    "Попробуйте /api/v1/tours/directions/collect-all",
                    "Проверьте логи для детальной диагностики"
                ]
            }

    async def clear_all_cache(self) -> dict:
        """Полная очистка всех кэшей направлений"""
        try:
            # Очищаем API кэш
            await self.cache.delete(self.API_CACHE_KEY)
            
            # Очищаем кэши массового сборщика
            mass_clear_result = await self.mass_collector.clear_all_directions_cache()
            
            return {
                "success": True,
                "message": "Все кэши направлений очищены",
                "details": mass_clear_result
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    async def _cache_api_response(self, directions: List[DirectionInfo]):
        """Сохранение направлений в API кэш"""
        try:
            directions_data = [direction.dict() for direction in directions]
            await self.cache.set(
                self.API_CACHE_KEY,
                directions_data,
                ttl=self.API_CACHE_TTL
            )
            logger.debug(f"💾 Сохранено {len(directions)} направлений в API кэш")
            
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения в API кэш: {e}")

    def _get_country_name(self, country_code: int) -> str:
        """Получение названия страны по коду (расширенный список)"""
        country_map = {
            1: "Египет", 4: "Турция", 8: "Греция", 9: "Кипр", 11: "Болгария",
            15: "ОАЭ", 16: "Тунис", 17: "Черногория", 19: "Испания", 20: "Италия",
            22: "Таиланд", 23: "Индия", 24: "Шри-Ланка", 25: "Вьетнам", 26: "Китай",
            27: "Индонезия", 28: "Малайзия", 29: "Сингапур", 30: "Филиппины",
            31: "Маврикий", 32: "Сейшелы", 33: "Танзания", 34: "Кения", 35: "Мальдивы"
        }
        return country_map.get(country_code, f"Страна {country_code}")

# Создаем экземпляр обновленного сервиса направлений
directions_service = DirectionsService()