import asyncio
from typing import List
from datetime import datetime, timedelta
import random

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
            # Сначала пытаемся получить туры через горящие туры (быстрее)
            random_tours = await self._try_hot_tours_approach()
            
            # Если горящие туры не сработали, используем обычный поиск
            if not random_tours or len(random_tours) < 3:
                logger.info("🔍 Горящие туры недоступны, используем обычный поиск")
                search_tours = await tour_service._generate_random_tours_via_search(self.target_count)
                
                # Комбинируем результаты
                all_tours = (random_tours or []) + search_tours
                random_tours = all_tours[:self.target_count]
            
            if random_tours and len(random_tours) >= 3:
                logger.info(f"✅ Обновлено {len(random_tours)} случайных туров")
                
                # Сохраняем в кэш
                await cache_service.set(
                    "random_tours_from_search",
                    [tour.dict() for tour in random_tours],
                    ttl=settings.POPULAR_TOURS_CACHE_TTL
                )
            else:
                logger.warning("⚠️ Не удалось получить достаточно туров, создаем fallback данные")
                await self._create_fallback_mock_data()
                
        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении случайных туров: {e}")
            # В случае ошибки также создаем mock-данные
            await self._create_fallback_mock_data()
    
    async def _try_hot_tours_approach(self) -> List[HotTourInfo]:
        """Попытка получить туры через горящие туры"""
        try:
            logger.info("🔥 Попытка получения туров через горящие туры...")
            
            all_hot_tours = []
            
            # Пробуем получить горящие туры из разных городов
            for city in self.cities:
                try:
                    # Получаем горящие туры для города
                    hot_tours_data = await tourvisor_client.get_hot_tours(
                        city=city,
                        items=10,
                        maxdays=30  # Туры на ближайший месяц
                    )
                    
                    tours_list = hot_tours_data.get("hottours", [])
                    hot_count = hot_tours_data.get("hotcount", 0)
                    
                    logger.info(f"🔥 Город {city}: найдено {hot_count} горящих туров")
                    
                    if tours_list and hot_count > 0:
                        # Конвертируем в нужный формат
                        for tour_data in tours_list[:3]:  # Максимум 3 тура с города
                            try:
                                hot_tour = HotTourInfo(**tour_data)
                                all_hot_tours.append(hot_tour)
                            except Exception as conv_error:
                                logger.warning(f"⚠️ Ошибка конвертации тура: {conv_error}")
                                continue
                    
                    # Небольшая задержка между запросами
                    await asyncio.sleep(0.5)
                    
                except Exception as city_error:
                    logger.warning(f"⚠️ Ошибка получения горящих туров для города {city}: {city_error}")
                    continue
            
            # Перемешиваем и берем нужное количество
            if all_hot_tours:
                random.shuffle(all_hot_tours)
                selected_tours = all_hot_tours[:self.target_count]
                logger.info(f"✅ Получено {len(selected_tours)} туров через горящие туры")
                return selected_tours
            
            logger.info("ℹ️ Горящие туры не вернули результатов")
            return []
            
        except Exception as e:
            logger.error(f"❌ Ошибка при получении горящих туров: {e}")
            return []
    
    async def _create_fallback_mock_data(self):
        """Создание резервных mock-данных на основе реальных справочников"""
        try:
            logger.info("🎭 Создание резервных mock-данных...")
            
            # Получаем реальные справочники
            countries_data = await tourvisor_client.get_references("country")
            departures_data = await tourvisor_client.get_references("departure")
            
            # Извлекаем списки
            countries_list = self._extract_reference_list(countries_data, "country")
            departures_list = self._extract_reference_list(departures_data, "departure")
            
            mock_tours = []
            popular_countries = ["Египет", "Турция", "Таиланд", "ОАЭ", "Греция", "Кипр"]
            
            for i, country_name in enumerate(popular_countries[:self.target_count]):
                # Находим реальные коды
                country_code = self._find_country_code(countries_list, country_name)
                city_data = departures_list[i % len(departures_list)] if departures_list else {}
                
                # Генерируем реалистичные данные
                base_price = self._generate_realistic_price(country_name)
                nights = random.choice([7, 10, 12, 14])
                stars = random.choice([3, 4, 5])
                
                # Вычисляем даты
                days_offset = random.randint(7, 30)
                fly_date = (datetime.now() + timedelta(days=days_offset)).strftime("%d.%m.%Y")
                
                mock_tour_data = {
                    "countrycode": country_code or str(i + 1),
                    "countryname": country_name,
                    "departurecode": city_data.get("id", str(i + 1)),
                    "departurename": city_data.get("name", f"Город {i+1}"),
                    "departurenamefrom": city_data.get("namefrom", f"Города {i+1}"),
                    "operatorcode": str(10 + i),
                    "operatorname": self._get_realistic_operator_name(i),
                    "hotelcode": str(200 + i),
                    "hotelname": self._generate_hotel_name(country_name, i),
                    "hotelstars": stars,
                    "hotelregioncode": str(100 + i),
                    "hotelregionname": self._get_popular_resort(country_name),
                    "hotelpicture": f"https://via.placeholder.com/250x150/{self._get_country_color(i)}/ffffff?text=Resort+{i+1}",
                    "fulldesclink": f"https://example.com/hotel/{200+i}",
                    "flydate": fly_date,
                    "nights": nights,
                    "meal": self._get_realistic_meal(stars),
                    "price": float(base_price),
                    "priceold": float(base_price + random.randint(5000, 15000)),
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
    
    def _extract_reference_list(self, data: dict, ref_type: str) -> list:
        """Извлечение списка из справочника"""
        try:
            # Различные возможные структуры ответа
            if ref_type in data:
                items = data[ref_type]
            elif "lists" in data:
                lists_data = data["lists"]
                ref_key = f"{ref_type}s" if not ref_type.endswith('y') else f"{ref_type[:-1]}ies"
                if ref_key in lists_data:
                    items = lists_data[ref_key].get(ref_type, [])
                else:
                    items = lists_data.get(ref_type, [])
            else:
                items = []
            
            # Нормализуем в список
            if not isinstance(items, list):
                items = [items] if items else []
            
            return items
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка извлечения справочника {ref_type}: {e}")
            return []
    
    def _find_country_code(self, countries_list: list, country_name: str) -> str:
        """Поиск кода страны по названию"""
        for country in countries_list:
            if isinstance(country, dict) and country.get("name") == country_name:
                return str(country.get("id", ""))
        return ""
    
    def _generate_realistic_price(self, country_name: str) -> int:
        """Генерация реалистичной цены по стране"""
        price_ranges = {
            "Египет": (35000, 65000),
            "Турция": (40000, 80000),
            "Таиланд": (70000, 120000),
            "ОАЭ": (80000, 150000),
            "Греция": (50000, 90000),
            "Кипр": (45000, 85000),
        }
        
        min_price, max_price = price_ranges.get(country_name, (40000, 80000))
        return random.randint(min_price, max_price)
    
    def _get_realistic_operator_name(self, index: int) -> str:
        """Получение реалистичного названия оператора"""
        operators = [
            "Anex Tour", "Pegas Touristik", "TUI", "Coral Travel", 
            "TEZ TOUR", "Sunmar", "ICS Travel Group", "Biblio Globus"
        ]
        return operators[index % len(operators)]
    
    def _generate_hotel_name(self, country_name: str, index: int) -> str:
        """Генерация названия отеля"""
        prefixes = {
            "Египет": ["SULTANA", "PHARAOH", "PYRAMIDS", "NILE"],
            "Турция": ["CLUB", "ROYAL", "SULTAN", "PALACE"],
            "Таиланд": ["PARADISE", "TROPICAL", "BAMBOO", "GOLDEN"],
            "ОАЭ": ["ATLANTIS", "EMIRATES", "LUXURY", "PEARL"],
            "Греция": ["BLUE", "AEGEAN", "OLYMPIA", "MEDITERRANEAN"],
            "Кипр": ["VENUS", "APHRODITE", "CRYSTAL", "SUNSHINE"]
        }
        
        country_prefixes = prefixes.get(country_name, ["RESORT", "HOTEL", "PALACE"])
        prefix = country_prefixes[index % len(country_prefixes)]
        
        return f"{prefix} {country_name.upper()} RESORT"
    
    def _get_popular_resort(self, country_name: str) -> str:
        """Получение популярного курорта"""
        resorts = {
            "Египет": "Хургада",
            "Турция": "Анталья", 
            "Таиланд": "Пхукет",
            "ОАЭ": "Дубай",
            "Греция": "Крит",
            "Кипр": "Пафос"
        }
        return resorts.get(country_name, f"Курорт {country_name}")
    
    def _get_realistic_meal(self, stars: int) -> str:
        """Получение реалистичного типа питания по звездности"""
        if stars >= 5:
            return random.choice(["All Inclusive", "Ultra All Inclusive"])
        elif stars >= 4:
            return random.choice(["All Inclusive", "Полупансион", "Полный пансион"])
        else:
            return random.choice(["Завтраки", "Полупансион", "All Inclusive"])
    
    def _get_country_color(self, index: int) -> str:
        """Получение цвета для изображения страны"""
        colors = ["4a90e2", "e74c3c", "2ecc71", "f39c12", "9b59b6", "1abc9c"]
        return colors[index % len(colors)]

# Глобальная функция для запуска обновления
async def update_random_tours():
    """Запуск обновления случайных туров"""
    service = RandomToursService()
    
    # Первое обновление при старте
    await service.update_random_tours()
    
    while True:
        try:
            # Ждем до следующего обновления (24 часа)
            logger.info("😴 Следующее обновление случайных туров через 24 часа...")
            await asyncio.sleep(86400)
            
            # Обновляем туры
            await service.update_random_tours()
            
        except Exception as e:
            logger.error(f"💥 Критическая ошибка в задаче обновления случайных туров: {e}")
            # При ошибке ждем 1 час перед повтором
            await asyncio.sleep(3600)