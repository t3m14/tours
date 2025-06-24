# app/services/directions_service.py

import logging
from typing import List, Dict, Any, Optional
from app.core.tourvisor_client import tourvisor_client
from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)

class DirectionsService:
    """Новый сервис для получения направлений по странам"""
    
    def __init__(self):
        pass  # Используем глобальный tourvisor_client
        
    # Маппинг стран из ТЗ (исправлены коды согласно API)
    COUNTRIES_MAPPING = {
        "Россия": {"country_id": 47, "country_code": 47},
        "Турция": {"country_id": 4, "country_code": 4},
        "Таиланд": {"country_id": 2, "country_code": 2},  # ИСПРАВЛЕНО: было 22, стало 2
        "ОАЭ": {"country_id": 9, "country_code": 9},  # ИСПРАВЛЕНО: было 15, стало 9
        "Египет": {"country_id": 1, "country_code": 1},
        "Мальдивы": {"country_id": 8, "country_code": 8},  # ИСПРАВЛЕНО: было 35, стало 8
        "Китай": {"country_id": 13, "country_code": 13},  # ИСПРАВЛЕНО: было 26, стало 13
        "Шри-Ланка": {"country_id": 12, "country_code": 12},  # ИСПРАВЛЕНО: было 24, стало 12
        "Абхазия": {"country_id": 46, "country_code": 46},
        "Куба": {"country_id": 10, "country_code": 10},
        "Индия": {"country_id": 3, "country_code": 3},  # ИСПРАВЛЕНО: было 23, стало 3
        "Вьетнам": {"country_id": 16, "country_code": 16},  # ИСПРАВЛЕНО: было 25, стало 16
        "Камбоджа": {"country_id": 40, "country_code": 40},
    }

    async def get_directions_by_country(self, country_name: str) -> List[Dict[str, Any]]:
        """
        Получение направлений для конкретной страны
        
        Алгоритм:
        1. Страна > получаем 12 туристических городов этой страны 
        2. Создаём список этих городов с фильтром по country_id
        3. Для каждого города запускаем укороченный поиск
        4. Получаем min_price из статуса поиска
        
        Args:
            country_name: Название страны из списка
            
        Returns:
            List[Dict]: Список направлений с country_name, country_id, city_name, min_price
        """
        try:
            logger.info(f"🌍 Получение направлений для страны: {country_name}")
            
            # Проверяем что страна есть в нашем маппинге
            if country_name not in self.COUNTRIES_MAPPING:
                raise ValueError(f"Страна '{country_name}' не найдена в списке поддерживаемых стран")
            
            country_info = self.COUNTRIES_MAPPING[country_name]
            country_id = country_info["country_id"]
            
            if country_id is None:
                logger.warning(f"⚠️ Код страны для '{country_name}' не определен")
                return []
            
            logger.info(f"🔍 Получаем города для country_id: {country_id}")
            
            # Кэшируем результат на 2 часа (поиски дорогие)
            cache_key = f"directions_with_prices_country_{country_id}"
            cached_result = await cache_service.get(cache_key)
            if cached_result:
                logger.info(f"📦 Возвращаем кэшированные данные с ценами для {country_name}: {len(cached_result)} направлений")
                return cached_result
            
            # Получаем 12 туристических городов для данной страны
            cities = await self._get_top_cities_for_country(country_id, limit=12)
            logger.info(f"🏙️ Получено {len(cities)} городов из API")
            
            # Формируем результат с поиском минимальных цен
            result = []
            for i, city in enumerate(cities):
                city_name = city.get("name", "")
                region_id = city.get("id")
                
                if not city_name or not region_id:
                    continue
                
                logger.info(f"🔍 [{i+1}/{len(cities)}] Поиск цен для города: {city_name}")
                
                # Запускаем поиск для получения минимальной цены и картинки
                min_price, image_link = await self._get_min_price_and_image_for_region(country_id, region_id, city_name)
                
                direction_item = {
                    "country_name": country_name,
                    "country_id": country_id,
                    "city_name": city_name,
                    "min_price": min_price,
                    "image_link": image_link
                }
                result.append(direction_item)
                logger.debug(f"➕ Добавлен город: {city_name}, цена: {min_price}, картинка: {'✅' if image_link else '❌'}")
                
                # Уменьшенная задержка между поисками
                if i < len(cities) - 1:  # Не ждем после последнего
                    import asyncio
                    await asyncio.sleep(0.5)  # Уменьшено с 1 сек до 0.5 сек
            
            # Кэшируем на 2 часа (поиски дорогие)
            await cache_service.set(cache_key, result, ttl=7200)
            
            logger.info(f"✅ Получено {len(result)} направлений с ценами для {country_name}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения направлений для {country_name}: {e}")
            raise

    async def get_all_directions(self) -> List[Dict[str, Any]]:
        """
        Получение всех направлений для всех стран из списка
        
        Returns:
            List[Dict]: Список всех направлений с фильтром по country_id
        """
        try:
            logger.info("🌐 Получение всех направлений")
            
            all_directions = []
            
            for country_name in self.COUNTRIES_MAPPING.keys():
                try:
                    country_directions = await self.get_directions_by_country(country_name)
                    all_directions.extend(country_directions)
                except Exception as e:
                    logger.error(f"❌ Ошибка для страны {country_name}: {e}")
                    continue
            
            logger.info(f"✅ Получено {len(all_directions)} направлений всего")
            return all_directions
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения всех направлений: {e}")
            raise

    async def _get_top_cities_for_country(self, country_id: int, limit: int = 12) -> List[Dict[str, Any]]:
        """
        Получение топ-N туристических городов для страны через API
        
        Args:
            country_id: ID страны
            limit: Максимальное количество городов (по умолчанию 12)
            
        Returns:
            List[Dict]: Список топ городов
        """
        try:
            logger.info(f"🌆 Запрашиваем топ-{limit} городов для country_id: {country_id}")
            
            # Используем правильный справочник "region" с параметром regcountry
            regions_data = await tourvisor_client.get_references(
                "region", 
                regcountry=country_id
            )
            
            logger.debug(f"📄 Получен ответ API для страны {country_id}")
            
            # Исправляем путь к данным - они находятся в lists.regions.region
            regions = regions_data.get("lists", {}).get("regions", {}).get("region", [])
            if not isinstance(regions, list):
                regions = [regions] if regions else []
            
            logger.info(f"🗂️ Извлечено {len(regions)} регионов из ответа API")
            
            # Проверяем что регионы принадлежат правильной стране
            valid_regions = []
            for region in regions:
                region_country = region.get("country")
                if region_country and str(region_country) == str(country_id):
                    valid_regions.append(region)
                else:
                    logger.warning(f"⚠️ Пропускаем регион {region.get('name')} - принадлежит стране {region_country}, а не {country_id}")
            
            logger.info(f"✅ Валидных регионов: {len(valid_regions)} из {len(regions)}")
            
            # Если недостаточно регионов, попробуем fallback
            if len(valid_regions) < limit:
                logger.warning(f"⚠️ Недостаточно регионов ({len(valid_regions)} < {limit}), пробуем fallback")
                fallback_regions = await self._get_fallback_regions(country_id, limit)
                if fallback_regions:
                    valid_regions.extend(fallback_regions)
                    # Убираем дубликаты по ID
                    seen_ids = set()
                    unique_regions = []
                    for region in valid_regions:
                        region_id = region.get("id")
                        if region_id not in seen_ids:
                            seen_ids.add(region_id)
                            unique_regions.append(region)
                    valid_regions = unique_regions
            
            # Ограничиваем до нужного количества
            top_cities = valid_regions[:limit]
            
            # Если все еще мало, добавляем синтетические города
            if len(top_cities) < limit:
                logger.warning(f"⚠️ Все еще мало городов ({len(top_cities)} < {limit}), добавляем синтетические")
                synthetic_cities = self._create_synthetic_cities(country_id, limit - len(top_cities))
                top_cities.extend(synthetic_cities)
            
            for i, city in enumerate(top_cities[:3]):  # Показываем первые 3 для примера
                logger.debug(f"  📍 Город {i+1}: {city.get('name', 'Без названия')} (ID: {city.get('id', 'N/A')})")
            
            logger.info(f"🏁 Итого городов: {len(top_cities)}")
            return top_cities
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения городов для страны {country_id}: {e}")
            # В случае ошибки возвращаем синтетические города
            return self._create_synthetic_cities(country_id, limit)

    async def _get_fallback_regions(self, country_id: int, limit: int) -> List[Dict[str, Any]]:
        """Fallback получение регионов через отели"""
        try:
            logger.info(f"🔄 Fallback: получение регионов через отели для страны {country_id}")
            
            # Получаем отели страны
            hotels_data = await tourvisor_client.get_references(
                "hotel",
                hotcountry=country_id
            )
            
            hotels = hotels_data.get("lists", {}).get("hotels", {}).get("hotel", [])
            if not isinstance(hotels, list):
                hotels = [hotels] if hotels else []
            
            # Извлекаем уникальные регионы из отелей
            regions_from_hotels = {}
            for hotel in hotels:
                region_id = hotel.get("regioncode")
                region_name = hotel.get("regionname")
                if region_id and region_name:
                    if region_id not in regions_from_hotels:
                        regions_from_hotels[region_id] = {
                            "id": region_id,
                            "name": region_name,
                            "country": str(country_id)
                        }
            
            fallback_regions = list(regions_from_hotels.values())[:limit]
            logger.info(f"🔄 Fallback нашел {len(fallback_regions)} регионов")
            return fallback_regions
            
        except Exception as e:
            logger.error(f"❌ Ошибка fallback для страны {country_id}: {e}")
            return []

    def _create_synthetic_cities(self, country_id: int, count: int) -> List[Dict[str, Any]]:
        """Создание синтетических городов для минимального количества"""
        
        # Популярные города по странам (с правильными кодами)
        popular_cities_by_country = {
            1: ["Шарм-Эль-Шейх", "Хургада", "Каир", "Александрия", "Марса Алам", "Дахаб", "Таба", "Сафага", "Эль Гуна", "Сома Бей", "Макади Бей", "Нувейба"],
            2: ["Пхукет", "Паттайя", "Бангкок", "Самуи", "Краби", "Пхи Пхи", "Хуа Хин", "Чиангмай", "Као Лак", "Ко Чанг", "Районг", "Сурат Тани"],  # Таиланд
            3: ["Гоа", "Керала", "Мумбаи", "Дели", "Агра", "Джайпур", "Ченнай", "Бангалор", "Калькутта", "Варанаси", "Ришикеш", "Дарджилинг"],  # Индия
            4: ["Анталья", "Стамбул", "Кемер", "Сиде", "Белек", "Аланья", "Мармарис", "Бодрум", "Фетхие", "Каппадокия", "Измир", "Кушадасы"],  # Турция
            8: ["Мале", "Атолл Ари", "Атолл Баа", "Атолл Лавиани", "Атолл Каафу", "Атолл Рас", "Атолл Даалу", "Атолл Фаафу", "Атолл Ха", "Атолл Лхавиани", "Атолл Мииму", "Атолл Ваavu"],  # Мальдивы
            9: ["Дубай", "Абу-Даби", "Шарджа", "Аджман", "Рас-эль-Хайма", "Фуджейра", "Умм-эль-Кайвайн", "Аль-Айн", "Дибба", "Корфаккан", "Хор Факкан", "Дибба Аль-Хисн"],  # ОАЭ
            10: ["Гавана", "Варадеро", "Кайо Коко", "Кайо Санта Мария", "Ольгин", "Сантьяго де Куба", "Тринидад", "Сьенфуэгос", "Кайо Ларго", "Матансас", "Пинар дель Рио", "Камагуэй"],  # Куба
            12: ["Коломбо", "Канди", "Галле", "Нувара Элия", "Анурадхапура", "Полоннарува", "Сигирия", "Дамбулла", "Тринкомали", "Хиккадува", "Мирисса", "Бентота"],  # Шри-Ланка
            13: ["Пекин", "Шанхай", "Гуанчжоу", "Хайнань", "Сиань", "Чэнду", "Ханчжоу", "Сучжоу", "Гуйлинь", "Лицзян", "Дали", "Куньмин"],  # Китай
            16: ["Хошимин", "Ханой", "Нячанг", "Фукуок", "Далат", "Хойан", "Хюэ", "Дананг", "Фантьет", "Вунгтау", "Сапа", "Халонг"],  # Вьетнам
            40: ["Сием Реап", "Пном Пень", "Сиануквиль", "Баттамбанг", "Кампот", "Кеп", "Кох Ронг", "Кратие", "Мондулкири", "Ратанакири", "Преах Вихеар", "Стынг Тренг"],  # Камбоджа
            46: ["Сухум", "Гагра", "Пицунда", "Новый Афон", "Очамчира", "Гудаута", "Цандрипш", "Мюссера", "Рица", "Псху", "Ткуарчал", "Гали"],  # Абхазия
            47: ["Москва", "Санкт-Петербург", "Сочи", "Калининград", "Казань", "Екатеринбург", "Новгород", "Суздаль", "Золотое кольцо", "Байкал", "Камчатка", "Алтай"]  # Россия
        }
        
        cities = popular_cities_by_country.get(country_id, [f"Город {i+1}" for i in range(count)])
        
        synthetic_cities = []
        for i in range(min(count, len(cities))):
            synthetic_cities.append({
                "id": f"synthetic_{country_id}_{i+1000}",
                "name": cities[i],
                "country": str(country_id),
                "synthetic": True
            })
        
        logger.info(f"🏗️ Создано {len(synthetic_cities)} синтетических городов для страны {country_id}")
        return synthetic_cities

    async def filter_directions_by_country_id(self, country_id: int, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Фильтрация направлений по country_id (как требуется в ТЗ)
        
        Args:
            country_id: ID страны для фильтрации
            limit: Лимит результатов
            
        Returns:
            List[Dict]: Отфильтрованные направления
        """
        try:
            logger.info(f"🔍 Фильтрация направлений по country_id: {country_id}")
            
            # Находим название страны по ID
            country_name = None
            for name, info in self.COUNTRIES_MAPPING.items():
                if info["country_id"] == country_id:
                    country_name = name
                    break
            
            if not country_name:
                logger.warning(f"⚠️ Страна с country_id {country_id} не найдена в маппинге")
                return []
            
            # Получаем направления для найденной страны
            directions = await self.get_directions_by_country(country_name)
            
            # Применяем лимит если указан
            if limit is not None:
                directions = directions[:limit]
                logger.info(f"⚡ Применен лимит: {limit} из {len(directions)} результатов")
            
            return directions
            
        except Exception as e:
            logger.error(f"❌ Ошибка фильтрации по country_id {country_id}: {e}")
            return []

    async def _get_min_price_and_image_for_region(self, country_id: int, region_id: str, city_name: str) -> tuple[Optional[int], Optional[str]]:
        """
        Получение минимальной цены и картинки для региона через укороченный поиск
        
        Args:
            country_id: ID страны
            region_id: ID региона (города)
            city_name: Название города (для логов)
            
        Returns:
            tuple: (минимальная цена, ссылка на картинку) или (None, None) если не найдены
        """
        try:
            logger.debug(f"💰🖼️ Поиск цены и картинки для города {city_name} (region_id: {region_id})")
            
            # Подготавливаем параметры укороченного поиска
            from datetime import datetime, timedelta
            
            # Даты: завтра + неделя (короткий диапазон)
            tomorrow = datetime.now() + timedelta(days=1)
            week_later = datetime.now() + timedelta(days=8)
            
            search_params = {
                "departure": 1,  # Москва по умолчанию
                "country": country_id,
                "regions": region_id,
                "datefrom": tomorrow.strftime("%d.%m.%Y"),
                "dateto": week_later.strftime("%d.%m.%Y"),
                "nightsfrom": 7,
                "nightsto": 10,
                "adults": 2,
                "format": "json"
            }
            
            # Запускаем поиск
            logger.debug(f"🚀 Запуск поиска для {city_name}")
            request_id = await tourvisor_client.search_tours(search_params)
            
            if not request_id:
                logger.warning(f"⚠️ Не удалось запустить поиск для {city_name}")
                return None, None
            
            logger.debug(f"🔄 Request ID для {city_name}: {request_id}")
            
            # Ждем результат поиска (максимум 20 секунд вместо 30)
            import asyncio
            max_attempts = 10  # 10 попыток по 2 секунды = 20 сек
            
            for attempt in range(max_attempts):
                try:
                    # Получаем статус поиска
                    status_result = await tourvisor_client.get_search_status(request_id)
                    
                    if not status_result:
                        continue
                        
                    status_data = status_result.get("data", {}).get("status", {})
                    state = status_data.get("state", "")
                    min_price = status_data.get("minprice")
                    hotels_found = status_data.get("hotelsfound", 0)
                    tours_found = status_data.get("toursfound", 0)
                    
                    logger.debug(f"🔍 Попытка {attempt+1}: состояние={state}, цена={min_price}, отели={hotels_found}, туры={tours_found}")
                    
                    if state == "finished":
                        # Получаем цену
                        price = None
                        if min_price is not None:
                            price_val = int(min_price) if str(min_price).replace('0', '').replace('.', '').isdigit() else 0
                            
                            # Проверяем валидность цены
                            if price_val > 0 and price_val < 1000000:  # Разумные пределы цены
                                price = price_val
                                logger.info(f"✅ Найдена цена для {city_name}: {price} руб.")
                            elif price_val == 0:
                                if hotels_found == 0 or tours_found == 0:
                                    logger.warning(f"🚫 Нет туров для {city_name}")
                                    return None, None
                                else:
                                    logger.warning(f"⚠️ Цена 0 для {city_name}")
                                    price = None
                        
                        # Получаем картинку из результатов поиска
                        image_link = await self._extract_image_from_search_results(request_id, city_name)
                        
                        # Fallback: если нет картинки, но есть цена, попробуем достать из других поисков
                        if not image_link and price:
                            image_link = await self._get_fallback_image_for_region(country_id, region_id, city_name)
                        
                        return price, image_link
                    
                    elif state == "error":
                        logger.warning(f"❌ Ошибка поиска для {city_name}")
                        break
                    
                    # Если поиск еще идет, ждем
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.debug(f"🔄 Ошибка проверки статуса для {city_name}: {e}")
                    await asyncio.sleep(2)
                    continue
            
            logger.warning(f"⏰ Таймаут поиска для {city_name} (20 сек)")
            
            # Если реальная цена не найдена, генерируем мок
            mock_price = self._generate_mock_price(country_id, city_name)
            mock_image = await self._get_fallback_image_for_region(country_id, region_id, city_name)
            
            if mock_price:
                logger.info(f"🎭 Мок цена для {city_name}: {mock_price} руб.")
            
            return mock_price, mock_image
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения цены и картинки для {city_name}: {e}")
            return None, None

    async def _get_fallback_image_for_region(self, country_id: int, region_id: str, city_name: str) -> Optional[str]:
        """
        Fallback получение картинки для региона через отели
        
        Args:
            country_id: ID страны
            region_id: ID региона
            city_name: Название города (для логов)
            
        Returns:
            Optional[str]: Ссылка на картинку или None
        """
        try:
            logger.debug(f"🔄 Fallback поиск картинки для {city_name}")
            
            # Получаем отели региона напрямую
            hotels_data = await tourvisor_client.get_references(
                "hotel",
                hotcountry=country_id,
                hotregion=region_id
            )
            
            hotels = hotels_data.get("lists", {}).get("hotels", {}).get("hotel", [])
            if not isinstance(hotels, list):
                hotels = [hotels] if hotels else []
            
            logger.debug(f"🏨 Fallback найдено {len(hotels)} отелей для {city_name}")
            
            # Ищем первую валидную картинку
            for hotel in hotels[:5]:  # Проверяем первые 5 отелей
                # Пробуем разные поля с картинками
                for pic_field in ["picturelink", "picture", "image", "photo"]:
                    picture_link = hotel.get(pic_field)
                    if picture_link and self._is_valid_image_link(picture_link):
                        logger.info(f"🖼️ Fallback картинка для {city_name}: {picture_link}")
                        return picture_link
            
            # Если все еще нет картинки, генерируем заглушку
            fallback_image = self._generate_fallback_image_link(country_id, city_name)
            if fallback_image:
                logger.info(f"🎨 Заглушка картинки для {city_name}: {fallback_image}")
                return fallback_image
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка fallback картинки для {city_name}: {e}")
            return None

    def _generate_fallback_image_link(self, country_id: int, city_name: str) -> Optional[str]:
        """Генерация заглушки картинки на основе страны и города"""
        
        # Ваши локальные картинки стран
        country_fallback_images = {
            1: "/static/mockup_images/egypt.jpg",        # Египет
            2: "/static/mockup_images/thailand.webp",     # Таиланд  
            3: "/static/mockup_images/india.webp",        # Индия
            4: "/static/mockup_images/turkey.jpeg",       # Турция
            8: "/static/mockup_images/maldives.jpg",      # Мальдивы
            9: "/static/mockup_images/oae.jpg",           # ОАЭ
            10: "/static/mockup_images/kuba.jpg",         # Куба
            12: "/static/mockup_images/sri_lanka.jpg",    # Шри-Ланка
            13: "/static/mockup_images/china.jpg",        # Китай
            16: "/static/mockup_images/vietnam.jpg",      # Вьетнам
            40: "/static/mockup_images/kambodja.jpg",     # Камбоджа
            46: "/static/mockup_images/abkhazia.jpg",     # Абхазия
            47: "/static/mockup_images/russia.webp",      # Россия
        }
        
        # Возвращаем картинку страны
        fallback = country_fallback_images.get(country_id)
        if fallback:
            # Проверяем что файл существует
            import os
            file_path = os.path.join(os.path.dirname(__file__), "mockup_images", os.path.basename(fallback))
            if os.path.exists(file_path):
                logger.debug(f"🎨 Заглушка для страны {country_id}: {fallback}")
                return fallback
            else:
                logger.warning(f"⚠️ Файл заглушки не найден: {file_path}")
        
        # Общая заглушка если страна не найдена или файл отсутствует
        logger.debug(f"❓ Нет заглушки для страны {country_id}, используем общую")
        return None  # Возвращаем None если нет заглушки

    async def _extract_image_from_search_results(self, request_id: str, city_name: str) -> Optional[str]:
        """
        Извлечение картинки из результатов поиска
        
        Args:
            request_id: ID запроса поиска
            city_name: Название города (для логов)
            
        Returns:
            Optional[str]: Ссылка на картинку или None
        """
        try:
            logger.debug(f"🖼️ Извлечение картинки для {city_name} из результатов поиска {request_id}")
            
            # Получаем результаты поиска
            search_results = await tourvisor_client.get_search_results(request_id)
            
            if not search_results:
                logger.debug(f"🔍 Нет результатов поиска для {city_name}")
                return None
            
            # Ищем отели в результатах
            result_data = search_results.get("data", {}).get("result", {})
            hotels = result_data.get("hotel", [])
            
            if not isinstance(hotels, list):
                hotels = [hotels] if hotels else []
            
            logger.debug(f"🏨 Найдено {len(hotels)} отелей в результатах для {city_name}")
            
            # Ищем первую валидную картинку
            for i, hotel in enumerate(hotels):
                picture_link = hotel.get("picturelink")
                hotel_name = hotel.get("hotelname", f"Отель {i+1}")
                
                if picture_link and self._is_valid_image_link(picture_link):
                    logger.info(f"🖼️ Найдена картинка для {city_name}: {hotel_name} - {picture_link}")
                    return picture_link
                else:
                    logger.debug(f"⚠️ Пропускаем невалидную картинку от {hotel_name}: {picture_link}")
            
            logger.warning(f"🚫 Не найдено валидных картинок для {city_name}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения картинки для {city_name}: {e}")
            return None

    def _is_valid_image_link(self, link: str) -> bool:
        """Проверка валидности ссылки на картинку"""
        if not link or not isinstance(link, str):
            return False
        
        # Проверяем что это URL
        if not (link.startswith("http://") or link.startswith("https://")):
            return False
        
        # Проверяем на популярные расширения изображений
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
        link_lower = link.lower()
        
        # Либо есть расширение, либо содержит паттерны картинок
        has_extension = any(link_lower.endswith(ext) for ext in image_extensions)
        has_image_pattern = any(pattern in link_lower for pattern in ['image', 'img', 'pic', 'photo', 'hotel_pics'])
        
        return has_extension or has_image_pattern

# Создаем единственный экземпляр сервиса
directions_service = DirectionsService()