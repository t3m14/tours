import asyncio
from typing import List

from app.core.tourvisor_client import tourvisor_client
from app.services.cache_service import cache_service
from app.services.random_tours_service import random_tours_service
from app.config import settings
from app.models.tour import HotTourInfo, RandomTourRequest
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class RandomToursUpdateService:
    """Сервис для обновления случайных туров через фоновую задачу"""
    
    def __init__(self):
        self.countries = settings.POPULAR_COUNTRIES.copy()
        self.cities = settings.DEPARTURE_CITIES.copy()
        self.target_count = settings.RANDOM_TOURS_COUNT
    
    async def update_random_tours(self):
        """Обновление случайных туров"""
        logger.info("🔄 Начато обновление случайных туров")
        
        try:
            # Сначала пробуем горящие туры (быстрый способ)
            hot_tours_result = await self._try_hot_tours_method()
            
            if hot_tours_result and len(hot_tours_result) >= self.target_count:
                logger.info(f"🔥 Успешно получено {len(hot_tours_result)} туров через горящие туры")
                await self._save_tours_to_cache(hot_tours_result)
                return
            
            # Если горящие туры не дали результата, используем обычный поиск
            logger.info("🔍 Горящие туры недоступны, используем обычный поиск")
            search_result = await self._try_search_method()
            
            if search_result and len(search_result) > 0:
                logger.info(f"✅ Обновлено {len(search_result)} случайных туров через поиск")
                await self._save_tours_to_cache(search_result)
            else:
                logger.warning("⚠️ Не удалось получить туры через поиск")
                await self._create_fallback_mock_data()
                
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении случайных туров: {e}")
            # В случае ошибки создаем mock-данные
            await self._create_fallback_mock_data()
    
    async def _try_hot_tours_method(self) -> List[HotTourInfo]:
        """Попытка получить туры через горящие туры"""
        try:
            logger.info("🔥 Пробуем получить туры через горящие туры")
            
            all_hot_tours = []
            
            for city in self.cities:
                try:
                    # Получаем горящие туры для каждого города
                    hot_tours_data = await tourvisor_client.get_hot_tours(
                        city=city,
                        items=10
                    )
                    
                    tours_list = hot_tours_data.get("hottours", [])
                    if not isinstance(tours_list, list):
                        tours_list = [tours_list] if tours_list else []
                    
                    logger.info(f"🔥 Город {city}: найдено {len(tours_list)} горящих туров")
                    
                    # Преобразуем в HotTourInfo объекты
                    for tour_data in tours_list:
                        try:
                            tour = HotTourInfo(**tour_data)
                            all_hot_tours.append(tour)
                        except Exception as tour_error:
                            logger.debug(f"Ошибка при создании объекта тура: {tour_error}")
                            continue
                    
                    # Задержка между запросами
                    await asyncio.sleep(0.5)
                    
                except Exception as city_error:
                    logger.warning(f"🔥 Ошибка для города {city}: {city_error}")
                    continue
            
            if not all_hot_tours:
                logger.info("ℹ️ Горящие туры не вернули результатов")
                return []
            
            # Перемешиваем и берем нужное количество
            import random
            random.shuffle(all_hot_tours)
            selected_tours = all_hot_tours[:self.target_count]
            
            logger.info(f"🔥 Отобрано {len(selected_tours)} горящих туров")
            return selected_tours
            
        except Exception as e:
            logger.error(f"🔥 Ошибка при получении горящих туров: {e}")
            return []
    
    async def _try_search_method(self) -> List[HotTourInfo]:
        """Попытка получить туры через обычный поиск"""
        try:
            logger.info("🔍 Пробуем получить туры через обычный поиск")
            
            # Используем новый RandomToursService
            request = RandomTourRequest(count=self.target_count)
            result = await random_tours_service._generate_random_tours_via_search(request.count)
            
            if result:
                logger.info(f"🔍 Получено {len(result)} туров через поиск")
                return result
            else:
                logger.warning("🔍 Поиск не вернул результатов")
                return []
                
        except Exception as e:
            logger.error(f"🔍 Ошибка при поиске туров: {e}")
            return []
    
    async def _save_tours_to_cache(self, tours: List[HotTourInfo]):
        """Сохранение туров в кэш"""
        try:
            tours_data = [tour.dict() for tour in tours]
            
            await cache_service.set(
                "random_tours_from_search",
                tours_data,
                ttl=settings.POPULAR_TOURS_CACHE_TTL
            )
            
            logger.info(f"💾 Сохранено {len(tours)} туров в кэш")
            
        except Exception as e:
            logger.error(f"💾 Ошибка при сохранении в кэш: {e}")
    
    async def _create_fallback_mock_data(self):
        """Создание резервных mock-данных на основе реальных справочников"""
        try:
            logger.info("🎭 Создание резервных mock-данных...")
            
            # Получаем реальные справочники
            countries_data = await tourvisor_client.get_references("country")
            departures_data = await tourvisor_client.get_references("departure")
            
            countries_list = countries_data.get("lists", {}).get("countries", {}).get("country", [])
            departures_list = departures_data.get("lists", {}).get("departures", {}).get("departure", [])
            
            # Если справочники пустые, используем жестко заданные данные
            if not countries_list:
                countries_list = [
                    {"id": "1", "name": "Египет"},
                    {"id": "4", "name": "Турция"},
                    {"id": "22", "name": "Таиланд"}
                ]
            
            if not departures_list:
                departures_list = [
                    {"id": "1", "name": "Москва", "namefrom": "Москвы"},
                    {"id": "2", "name": "Пермь", "namefrom": "Перми"},
                    {"id": "3", "name": "Екатеринбург", "namefrom": "Екатеринбурга"}
                ]
            
            mock_tours = []
            popular_countries = ["Египет", "Турция", "Таиланд", "ОАЭ", "Греция", "Кипр"]
            
            for i in range(self.target_count):
                # Выбираем данные
                country_name = popular_countries[i % len(popular_countries)]
                
                # Находим реальные коды
                country_code = None
                for country in countries_list:
                    if country.get("name") == country_name:
                        country_code = country.get("id")
                        break
                
                city_data = departures_list[i % len(departures_list)] if departures_list else {}
                
                import random
                base_price = 40000 + (i * 15000) + random.randint(-8000, 20000)
                
                mock_tour_data = {
                    "countrycode": country_code or str(i + 1),
                    "countryname": country_name,
                    "departurecode": city_data.get("id", str((i % 3) + 1)),
                    "departurename": city_data.get("name", f"Город {i+1}"),
                    "departurenamefrom": city_data.get("namefrom", f"Города {i+1}"),
                    "operatorcode": str(10 + i),
                    "operatorname": f"TourOperator {i+1}",
                    "hotelcode": str(200 + i),
                    "hotelname": f"RESORT {country_name.upper()} {i+1}",
                    "hotelstars": 3 + (i % 3),
                    "hotelregioncode": str(100 + i),
                    "hotelregionname": f"Курорт {country_name}",
                    "hotelpicture": f"https://via.placeholder.com/250x150/{'4a90e2' if i % 2 == 0 else 'e74c3c'}/ffffff?text=Resort+{i+1}",
                    "fulldesclink": f"https://example.com/hotel/{200+i}",
                    "flydate": f"{15 + i}.07.2025",
                    "nights": 7 + (i % 7),
                    "meal": ["All Inclusive", "Ultra All Inclusive", "Полупансион"][i % 3],
                    "price": float(base_price),
                    "priceold": float(base_price + random.randint(5000, 12000)),
                    "currency": "RUB"
                }
                
                # Создаем объект HotTourInfo
                try:
                    mock_tour = HotTourInfo(**mock_tour_data)
                    mock_tours.append(mock_tour)
                except Exception as tour_error:
                    logger.warning(f"Ошибка при создании mock тура: {tour_error}")
                    continue
            
            # Сохраняем mock-данные в кэш
            await self._save_tours_to_cache(mock_tours)
            
            logger.info(f"✅ Созданы и сохранены {len(mock_tours)} резервных mock-туров")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при создании резервных данных: {e}")

# Глобальная функция для запуска обновления
async def update_random_tours():
    """Запуск обновления случайных туров"""
    service = RandomToursUpdateService()
    
    # Первое обновление при старте
    await service.update_random_tours()
    
    while True:
        try:
            logger.info("😴 Ожидание следующего обновления туров (24 часа)")
            # Ждем до следующего обновления (24 часа)
            await asyncio.sleep(86400)
            
            # Обновляем туры
            await service.update_random_tours()
            
        except Exception as e:
            logger.error(f"💥 Критическая ошибка в задаче обновления случайных туров: {e}")
            # При ошибке ждем 1 час перед повтором
            await asyncio.sleep(3600)