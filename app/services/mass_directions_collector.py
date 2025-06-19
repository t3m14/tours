"""
Сервис для массового сбора и долгосрочного кэширования направлений
Собирает направления из ВСЕХ доступных стран и сохраняет в долгосрочный кэш
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from app.services.cache_service import cache_service
from app.services.photo_service import photo_service
from app.services.price_service import price_service
from app.core.tourvisor_client import tourvisor_client
from app.models.tour import DirectionInfo
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class MassDirectionsCollector:
    """Сервис для массового сбора всех возможных направлений"""
    
    def __init__(self):
        self.cache = cache_service
        self.photo_service = photo_service
        self.price_service = price_service
        
        # Ключи кэша для долгосрочного хранения
        self.MASTER_DIRECTIONS_KEY = "master_directions_all_countries"
        self.DIRECTIONS_METADATA_KEY = "directions_metadata"
        self.COUNTRY_PROGRESS_KEY = "directions_collection_progress"
        
        # TTL для долгосрочного хранения (30 дней)
        self.LONG_TERM_TTL = 2592000  # 30 дней
        
    async def collect_all_directions(self, force_rebuild: bool = False) -> List[DirectionInfo]:
        """
        Массовый сбор направлений из ВСЕХ доступных стран
        
        Args:
            force_rebuild: Принудительный пересбор даже если кэш существует
        """
        logger.info("🌍 НАЧИНАЕМ МАССОВЫЙ СБОР ВСЕХ НАПРАВЛЕНИЙ")
        
        # Проверяем существующий кэш
        if not force_rebuild:
            cached_directions = await self._get_cached_master_directions()
            if cached_directions and len(cached_directions) > 10:
                logger.info(f"📦 Возвращено {len(cached_directions)} направлений из долгосрочного кэша")
                return cached_directions
        
        logger.info("🔄 Запускаем полный сбор направлений...")
        
        # Получаем список всех стран
        all_countries = await self._get_all_available_countries()
        logger.info(f"🌎 Найдено {len(all_countries)} стран для обработки")
        
        if not all_countries:
            logger.error("❌ Не удалось получить список стран")
            return await self._get_fallback_directions()
        
        # Собираем направления по всем странам
        all_directions = await self._collect_directions_from_countries(all_countries)
        
        # Сохраняем в долгосрочный кэш
        if all_directions:
            await self._save_master_directions(all_directions, all_countries)
            logger.info(f"✅ МАССОВЫЙ СБОР ЗАВЕРШЕН: {len(all_directions)} направлений")
        else:
            logger.warning("⚠️ Не удалось собрать направления, используем fallback")
            all_directions = await self._get_fallback_directions()
        
        return all_directions
    
    async def _get_all_available_countries(self) -> List[Dict[str, Any]]:
        """Получение списка всех доступных стран из API"""
        try:
            logger.info("📋 Получаем полный список стран...")
            
            countries_data = await tourvisor_client.get_references("country")
            countries_list = countries_data.get("country", [])
            
            if not isinstance(countries_list, list):
                countries_list = [countries_list] if countries_list else []
            
            # Фильтруем страны с валидными кодами
            valid_countries = []
            for country in countries_list:
                country_id = country.get("id")
                country_name = country.get("name")
                
                if country_id and country_name:
                    try:
                        # Проверяем что ID - это число
                        int(country_id)
                        valid_countries.append({
                            "id": int(country_id),
                            "name": country_name
                        })
                    except (ValueError, TypeError):
                        continue
            
            logger.info(f"📋 Валидных стран: {len(valid_countries)}")
            
            # Сортируем по популярности (популярные страны первыми)
            popular_countries = [1, 4, 22, 8, 15, 35, 9, 11]  # Египет, Турция, Таиланд и т.д.
            
            def country_priority(country):
                return 0 if country["id"] in popular_countries else 1
            
            valid_countries.sort(key=country_priority)
            
            return valid_countries
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении списка стран: {e}")
            return []
    
    async def _collect_directions_from_countries(self, countries: List[Dict[str, Any]]) -> List[DirectionInfo]:
        """Сбор направлений из всех стран"""
        all_directions = []
        
        logger.info(f"🔄 Начинаем обработку {len(countries)} стран...")
        
        # Сохраняем прогресс
        await self._save_collection_progress(0, len(countries), "starting")
        
        for i, country in enumerate(countries):
            country_id = country["id"]
            country_name = country["name"]
            
            try:
                logger.info(f"🌍 [{i+1}/{len(countries)}] Обрабатываем {country_name}")
                
                # Обновляем прогресс
                await self._save_collection_progress(i+1, len(countries), f"processing_{country_name}")
                
                direction = await self._collect_single_direction(country_id, country_name)
                
                if direction:
                    all_directions.append(direction)
                    logger.info(f"✅ {country_name}: цена {direction.min_price}, фото: {'✓' if not direction.image_link.startswith('https://via.placeholder.com') else '✗'}")
                else:
                    logger.warning(f"⚠️ {country_name}: не удалось создать направление")
                
                # Задержка между странами для снижения нагрузки на API
                await asyncio.sleep(0.5)
                
                # Промежуточное сохранение каждые 10 стран
                if (i + 1) % 10 == 0:
                    logger.info(f"💾 Промежуточное сохранение: {len(all_directions)} направлений")
                    await self._save_partial_directions(all_directions)
                
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке {country_name}: {e}")
                continue
        
        # Финальное сохранение прогресса
        await self._save_collection_progress(len(countries), len(countries), "completed")
        
        logger.info(f"🏁 Обработка завершена: {len(all_directions)} направлений из {len(countries)} стран")
        return all_directions
    
    async def _collect_single_direction(self, country_id: int, country_name: str) -> Optional[DirectionInfo]:
        """Сбор одного направления для страны"""
        try:
            # Получаем фото и цену параллельно
            photo_task = self.photo_service.get_country_hotel_photo_fast(country_id, country_name)
            price_task = self.price_service.get_country_min_price(country_id, country_name)
            
            # Ждем результатов с таймаутом
            try:
                hotel_photo, min_price = await asyncio.wait_for(
                    asyncio.gather(photo_task, price_task, return_exceptions=True),
                    timeout=15.0  # 15 секунд максимум на страну
                )
            except asyncio.TimeoutError:
                logger.warning(f"⏰ Таймаут для {country_name}, используем fallback")
                hotel_photo = None
                min_price = 50000.0
            
            # Обрабатываем возможные исключения
            if isinstance(hotel_photo, Exception):
                logger.debug(f"❌ Ошибка получения фото для {country_name}: {hotel_photo}")
                hotel_photo = None
            
            if isinstance(min_price, Exception):
                logger.debug(f"❌ Ошибка получения цены для {country_name}: {min_price}")
                min_price = self.price_service.get_default_prices().get(country_id, 50000.0)
            
            # Fallback для фото
            if not hotel_photo:
                hotel_photo = self.photo_service.get_fallback_image(country_id, country_name)
            
            return DirectionInfo(
                name=country_name,
                image_link=hotel_photo,
                min_price=float(min_price)
            )
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка для {country_name}: {e}")
            return None
    
    async def _save_master_directions(self, directions: List[DirectionInfo], countries: List[Dict[str, Any]]):
        """Сохранение мастер-списка направлений в долгосрочный кэш"""
        try:
            # Сохраняем сами направления
            directions_data = [direction.dict() for direction in directions]
            await self.cache.set(
                self.MASTER_DIRECTIONS_KEY,
                directions_data,
                ttl=self.LONG_TERM_TTL
            )
            
            # Сохраняем метаданные
            metadata = {
                "collection_date": datetime.now().isoformat(),
                "total_countries_processed": len(countries),
                "total_directions_collected": len(directions),
                "countries_with_real_photos": len([d for d in directions if not d.image_link.startswith("https://via.placeholder.com")]),
                "average_price": sum(d.min_price for d in directions) / len(directions) if directions else 0,
                "price_range": {
                    "min": min(d.min_price for d in directions) if directions else 0,
                    "max": max(d.min_price for d in directions) if directions else 0
                },
                "countries_list": [c["name"] for c in countries],
                "ttl_days": self.LONG_TERM_TTL // 86400
            }
            
            await self.cache.set(
                self.DIRECTIONS_METADATA_KEY,
                metadata,
                ttl=self.LONG_TERM_TTL
            )
            
            logger.info(f"💾 Сохранено {len(directions)} направлений в долгосрочный кэш")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении в долгосрочный кэш: {e}")
    
    async def _save_partial_directions(self, directions: List[DirectionInfo]):
        """Промежуточное сохранение направлений"""
        try:
            partial_key = f"{self.MASTER_DIRECTIONS_KEY}_partial"
            directions_data = [direction.dict() for direction in directions]
            await self.cache.set(partial_key, directions_data, ttl=86400)  # 24 часа
            
        except Exception as e:
            logger.debug(f"❌ Ошибка промежуточного сохранения: {e}")
    
    async def _save_collection_progress(self, current: int, total: int, status: str):
        """Сохранение прогресса сбора"""
        try:
            progress_data = {
                "current": current,
                "total": total,
                "percentage": (current / total * 100) if total > 0 else 0,
                "status": status,
                "last_update": datetime.now().isoformat()
            }
            
            await self.cache.set(
                self.COUNTRY_PROGRESS_KEY,
                progress_data,
                ttl=86400  # 24 часа
            )
            
        except Exception as e:
            logger.debug(f"❌ Ошибка сохранения прогресса: {e}")
    
    async def _get_cached_master_directions(self) -> Optional[List[DirectionInfo]]:
        """Получение направлений из долгосрочного кэша"""
        try:
            cached_data = await self.cache.get(self.MASTER_DIRECTIONS_KEY)
            if cached_data:
                return [DirectionInfo(**item) for item in cached_data]
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении из долгосрочного кэша: {e}")
            return None
    
    async def _get_fallback_directions(self) -> List[DirectionInfo]:
        """Fallback направления если не удалось собрать из API"""
        logger.info("🎭 Создаем fallback направления")
        
        fallback_countries = [
            {"id": 1, "name": "Египет", "price": 45000},
            {"id": 4, "name": "Турция", "price": 35000},
            {"id": 22, "name": "Таиланд", "price": 95000},
            {"id": 8, "name": "Греция", "price": 55000},
            {"id": 15, "name": "ОАЭ", "price": 75000},
            {"id": 35, "name": "Мальдивы", "price": 180000},
            {"id": 9, "name": "Кипр", "price": 45000},
            {"id": 11, "name": "Болгария", "price": 40000},
            {"id": 16, "name": "Тунис", "price": 50000},
            {"id": 17, "name": "Черногория", "price": 60000},
            {"id": 19, "name": "Испания", "price": 70000},
            {"id": 20, "name": "Италия", "price": 80000},
            {"id": 23, "name": "Индия", "price": 85000},
            {"id": 24, "name": "Шри-Ланка", "price": 90000},
            {"id": 25, "name": "Вьетнам", "price": 75000},
        ]
        
        directions = []
        for country in fallback_countries:
            direction = DirectionInfo(
                name=country["name"],
                image_link=self.photo_service.get_fallback_image(country["id"], country["name"]),
                min_price=float(country["price"])
            )
            directions.append(direction)
        
        return directions
    
    async def get_collection_status(self) -> Dict[str, Any]:
        """Получение статуса сбора направлений"""
        try:
            # Проверяем долгосрочный кэш
            master_directions = await self.cache.get(self.MASTER_DIRECTIONS_KEY)
            metadata = await self.cache.get(self.DIRECTIONS_METADATA_KEY)
            progress = await self.cache.get(self.COUNTRY_PROGRESS_KEY)
            
            return {
                "master_cache": {
                    "exists": bool(master_directions),
                    "directions_count": len(master_directions) if master_directions else 0,
                    "last_collection": metadata.get("collection_date") if metadata else None,
                    "countries_processed": metadata.get("total_countries_processed") if metadata else 0,
                    "real_photos_count": metadata.get("countries_with_real_photos") if metadata else 0
                },
                "current_progress": progress,
                "cache_info": {
                    "master_key": self.MASTER_DIRECTIONS_KEY,
                    "ttl_days": self.LONG_TERM_TTL // 86400,
                    "metadata_available": bool(metadata)
                },
                "statistics": metadata if metadata else {},
                "recommendations": self._get_recommendations(master_directions, metadata, progress)
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "recommendations": ["Запустите полный сбор направлений"]
            }
    
    def _get_recommendations(self, master_directions, metadata, progress) -> List[str]:
        """Получение рекомендаций по состоянию системы"""
        recommendations = []
        
        if not master_directions:
            recommendations.append("🔄 Запустите полный сбор направлений: /api/v1/tours/directions/collect-all")
            
        elif metadata:
            # Проверяем возраст данных
            try:
                collection_date = datetime.fromisoformat(metadata["collection_date"])
                days_old = (datetime.now() - collection_date).days
                
                if days_old > 30:
                    recommendations.append(f"🔄 Данные устарели ({days_old} дней), рекомендуется обновление")
                elif days_old > 7:
                    recommendations.append(f"📊 Данные {days_old} дней назад, в порядке")
                else:
                    recommendations.append("✅ Данные свежие")
                    
            except:
                pass
                
            # Проверяем количество
            directions_count = metadata.get("total_directions_collected", 0)
            if directions_count < 10:
                recommendations.append("⚠️ Мало направлений, попробуйте пересобрать")
            elif directions_count < 20:
                recommendations.append("📈 Среднее количество направлений")
            else:
                recommendations.append(f"🎯 Отличное количество: {directions_count} направлений")
        
        return recommendations
    
    async def clear_all_directions_cache(self) -> Dict[str, Any]:
        """Полная очистка кэша направлений"""
        try:
            keys_to_clear = [
                self.MASTER_DIRECTIONS_KEY,
                self.DIRECTIONS_METADATA_KEY,
                self.COUNTRY_PROGRESS_KEY,
                f"{self.MASTER_DIRECTIONS_KEY}_partial",
                "directions_with_prices_and_photos"  # Старый ключ
            ]
            
            cleared_keys = []
            for key in keys_to_clear:
                if await self.cache.delete(key):
                    cleared_keys.append(key)
            
            return {
                "success": True,
                "message": f"Очищено {len(cleared_keys)} ключей кэша",
                "cleared_keys": cleared_keys
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

# Создаем экземпляр сервиса
mass_directions_collector = MassDirectionsCollector()