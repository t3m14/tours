import asyncio
from typing import List

from app.core.tourvisor_client import tourvisor_client
from app.services.cache_service import cache_service
from app.config import settings
from app.models.tour import HotTourInfo
from app.services.tour_service import tour_service
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class RandomToursService:
    """Сервис для обновления случайных туров через обычный поиск"""
    
    def __init__(self):
        self.countries = settings.POPULAR_COUNTRIES.copy()
        self.cities = settings.DEPARTURE_CITIES.copy()
        self.target_count = settings.RANDOM_TOURS_COUNT
    
    async def update_random_tours(self):
        """Обновление случайных туров через поиск"""
        logger.info("🔄 Начато обновление случайных туров через поиск")
        
        try:
            # Сначала пытаемся получить горящие туры (более быстрый метод)
            logger.info("🔥 Попытка получения туров через горящие туры...")
            hot_tours = await self._try_get_hot_tours()
            
            if hot_tours:
                logger.info(f"✅ Получено {len(hot_tours)} горящих туров")
                # Кэшируем горящие туры
                await cache_service.set(
                    "random_tours_from_search",
                    [tour.dict() for tour in hot_tours],
                    ttl=settings.POPULAR_TOURS_CACHE_TTL
                )
            else:
                logger.info("ℹ️ Горящие туры не вернули результатов")
                logger.info("🔍 Горящие туры недоступны, используем обычный поиск")
                
                # Генерируем новый набор случайных туров через поиск
                random_tours = await tour_service._generate_random_tours_via_search(self.target_count)
                
                if random_tours:
                    logger.info(f"✅ Обновлено {len(random_tours)} случайных туров через поиск")
                else:
                    logger.warning("⚠️ Не удалось сгенерировать случайные туры через поиск")
                    
                    # Fallback: создаем mock-данные на основе реальных справочников
                    logger.info("🎭 Создаем fallback mock-данные...")
                    await self._create_fallback_mock_data()
                
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении случайных туров: {e}")
            # В случае ошибки также создаем mock-данные
            await self._create_fallback_mock_data()
    
    async def _try_get_hot_tours(self) -> List[HotTourInfo]:
        """Попытка получить горящие туры из разных городов"""
        all_hot_tours = []
        
        for city in self.cities:
            try:
                logger.info(f"🔥 Получение горящих туров для города {city}")
                
                hot_tours_data = await tourvisor_client.get_hot_tours(
                    city=city,
                    items=20
                )
                
                hot_count = hot_tours_data.get("hotcount", 0)
                tours_list = hot_tours_data.get("hottours", [])
                
                logger.info(f"🔥 Город {city}: найдено {hot_count} горящих туров")
                
                if tours_list:
                    for tour_data in tours_list:
                        try:
                            hot_tour = HotTourInfo(**tour_data)
                            all_hot_tours.append(hot_tour)
                        except Exception as tour_error:
                            logger.warning(f"⚠️ Ошибка создания объекта тура: {tour_error}")
                            continue
                
                # Прерываем если набрали достаточно туров
                if len(all_hot_tours) >= self.target_count:
                    break
                    
                # Небольшая задержка между запросами
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.warning(f"⚠️ Ошибка получения горящих туров для города {city}: {e}")
                continue
        
        # Возвращаем только нужное количество туров
        return all_hot_tours[:self.target_count]
    
    async def _create_fallback_mock_data(self):
        """Создание резервных mock-данных на основе реальных справочников"""
        try:
            logger.info("🎭 Создание резервных mock-данных...")
            
            # Получаем реальные справочники
            try:
                countries_data = await tourvisor_client.get_references("country")
                departures_data = await tourvisor_client.get_references("departure")
                
                countries_list = countries_data.get("lists", {}).get("countries", {}).get("country", [])
                departures_list = departures_data.get("lists", {}).get("departures", {}).get("departure", [])
                
                if not countries_list:
                    countries_list = countries_data.get("country", [])
                if not departures_list:
                    departures_list = departures_data.get("departure", [])
                    
            except Exception as ref_error:
                logger.warning(f"⚠️ Ошибка получения справочников: {ref_error}")
                countries_list = []
                departures_list = []
            
            mock_tours = []
            popular_countries = ["Египет", "Турция", "Таиланд", "ОАЭ", "Греция", "Кипр"]
            
            for i, country_name in enumerate(popular_countries[:self.target_count]):
                # Находим реальные коды
                country_code = None
                for country in countries_list:
                    if isinstance(country, dict) and country.get("name") == country_name:
                        country_code = country.get("id")
                        break
                
                city_data = {}
                if departures_list and i < len(departures_list):
                    city_data = departures_list[i] if isinstance(departures_list[i], dict) else {}
                
                import random
                base_price = 40000 + (i * 15000) + random.randint(-8000, 20000)
                
                mock_tour_data = {
                    "countrycode": str(country_code or (i + 1)),
                    "countryname": country_name,
                    "departurecode": str(city_data.get("id", i + 1)),
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
                
                try:
                    hot_tour = HotTourInfo(**mock_tour_data)
                    mock_tours.append(hot_tour)
                except Exception as mock_error:
                    logger.warning(f"⚠️ Ошибка создания mock тура {i}: {mock_error}")
                    continue
            
            # Сохраняем mock-данные в кэш
            if mock_tours:
                await cache_service.set(
                    "random_tours_from_search",
                    [tour.dict() for tour in mock_tours],
                    ttl=settings.POPULAR_TOURS_CACHE_TTL
                )
                
                logger.info(f"✅ Созданы и сохранены {len(mock_tours)} резервных mock-туров")
            else:
                logger.error("❌ Не удалось создать ни одного mock тура")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при создании резервных данных: {e}")

# Глобальная функция для запуска обновления
async def update_random_tours():
    """Запуск обновления случайных туров"""
    service = RandomToursService()
    
    try:
        # Первое обновление при старте
        await service.update_random_tours()
        
        while True:
            try:
                # Ждем до следующего обновления (24 часа)
                logger.info("😴 Ожидание следующего обновления туров (24 часа)")
                await asyncio.sleep(86400)
                
                # Обновляем туры
                await service.update_random_tours()
                
            except Exception as e:
                logger.error(f"💥 Ошибка в цикле обновления случайных туров: {e}")
                # При ошибке ждем 1 час перед повтором
                logger.info("⏰ Ожидание 1 час перед повтором")
                await asyncio.sleep(3600)
                
    except Exception as e:
        logger.error(f"💥 Критическая ошибка в задаче обновления случайных туров: {e}")
        # Критическая ошибка - пытаемся создать хотя бы mock данные
        try:
            await service._create_fallback_mock_data()
        except:
            logger.error("💀 Не удалось создать даже mock данные")