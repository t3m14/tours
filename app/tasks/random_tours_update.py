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
    
    async def _create_fallback_mock_data(self):
        """Создание резервных mock-данных на основе реальных справочников"""
        try:
            logger.info("🎭 Создание резервных mock-данных...")
            
            # Получаем реальные справочники
            countries_data = await tourvisor_client.get_references("country")
            departures_data = await tourvisor_client.get_references("departure")
            
            countries_list = countries_data.get("lists", {}).get("countries", {}).get("country", [])
            departures_list = departures_data.get("lists", {}).get("departures", {}).get("departure", [])
            
            mock_tours = []
            popular_countries = ["Египет", "Турция", "Таиланд", "ОАЭ", "Греция", "Кипр"]
            
            for i, country_name in enumerate(popular_countries[:self.target_count]):
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
                    "departurecode": city_data.get("id", str(i + 1)),
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
                
                mock_tours.append(mock_tour_data)
            
            # Сохраняем mock-данные в кэш
            await cache_service.set(
                "random_tours_from_search",
                mock_tours,
                ttl=settings.POPULAR_TOURS_CACHE_TTL
            )
            
            logger.info(f"✅ Созданы и сохранены {len(mock_tours)} резервных mock-туров")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при создании резервных данных: {e}")

# Глобальная функция для запуска обновления
async def update_random_tours():
    """Запуск обновления случайных туров"""
    service = RandomToursService()
    
    # Первое обновление при старте
    await service.update_random_tours()
    
    while True:
        try:
            # Ждем до следующего обновления (24 часа)
            await asyncio.sleep(86400)
            
            # Обновляем туры
            await service.update_random_tours()
            
        except Exception as e:
            logger.error(f"💥 Критическая ошибка в задаче обновления случайных туров: {e}")
            # При ошибке ждем 1 час перед повтором
            await asyncio.sleep(3600)