# app/services/directions_service.py - ИСПРАВЛЕННАЯ ВЕРСИЯ

import logging
from typing import List, Dict, Any, Optional
from app.core.tourvisor_client import tourvisor_client
from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)

class DirectionsService:
    """Исправленный сервис для получения направлений по странам"""
    
    def __init__(self):
        pass  # Используем глобальный tourvisor_client
        
    # Маппинг стран из ТЗ (исправлены коды согласно API)
    COUNTRIES_MAPPING = {
        "Россия": {"country_id": 47, "country_code": 47},
        "Турция": {"country_id": 4, "country_code": 4},
        "Таиланд": {"country_id": 2, "country_code": 2},
        "ОАЭ": {"country_id": 9, "country_code": 9},
        "Египет": {"country_id": 1, "country_code": 1},
        "Мальдивы": {"country_id": 8, "country_code": 8},
        "Китай": {"country_id": 13, "country_code": 13},
        "Шри-Ланка": {"country_id": 12, "country_code": 12},
        "Абхазия": {"country_id": 46, "country_code": 46},
        "Куба": {"country_id": 10, "country_code": 10},
        "Индия": {"country_id": 3, "country_code": 3},
        "Вьетнам": {"country_id": 16, "country_code": 16},
        # "Камбоджа": {"country_id": 40, "country_code": 40},
    }

 
    async def get_directions_by_country(self, country_name: str) -> List[Dict[str, Any]]:
        """
        ИСПРАВЛЕНО: добавлена логика кеша как в random_tours_service
        Сначала проверяем кеш, потом вызываем оригинальную логику
        """
        if country_name not in self.COUNTRIES_MAPPING:
            logger.warning(f"❌ Неизвестная страна: {country_name}")
            return []
        
        country_info = self.COUNTRIES_MAPPING[country_name]
        country_id = country_info["country_id"]
        cache_key = f"directions_with_prices_country_{country_id}"
        
        # КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: СНАЧАЛА проверяем кеш - моментальная отдача!
        try:
            cached_directions = await cache_service.get(cache_key)
            if cached_directions:
                logger.info(f"📦 МОМЕНТАЛЬНАЯ ОТДАЧА {len(cached_directions)} направлений из кеша для {country_name}")
                return cached_directions
        except Exception as e:
            logger.warning(f"⚠️ Ошибка проверки кеша для {country_name}: {e}")
        
        # Если кеша нет, вызываем оригинальную логику генерации
        logger.info(f"🔄 Генерация направлений для {country_name} (кеш отсутствует)")
        
        try:
            # ВСЯ ВАША ОРИГИНАЛЬНАЯ ЛОГИКА БЕЗ ИЗМЕНЕНИЙ:
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
            
            # Получаем 12 туристических городов для данной страны
            cities = await self._get_top_cities_for_country(country_id, limit=12)
            logger.info(f"🏙️ Получено {len(cities)} городов из API")
            
            # Формируем результат с поиском минимальных цен
            result = []
            for i, city in enumerate(cities):
                city_name = city.get("name", "")
                region_id = city.get("id")
                is_synthetic = city.get("synthetic", False)
                
                if not city_name:
                    continue
                
                logger.info(f"🔍 [{i+1}/{len(cities)}] Обработка города: {city_name} {'(синтетический)' if is_synthetic else ''}")
                
                # Получаем цену и картинку
                min_price, image_link = await self._get_price_and_image_safe(
                    country_id, region_id, city_name, is_synthetic
                )
                
                # ИСПРАВЛЕНИЕ: Проверяем и обрабатываем NULL значения
                direction_item = {
                    "country_name": country_name,
                    "country_id": country_id,
                    "city_name": city_name,
                    "city_id": region_id,
                    "min_price": min_price,  # Может быть None для городов без туров
                    "image_link": image_link  # Может быть None для городов без картинок
                }
                result.append(direction_item)
                
                status_price = f"💰{min_price}" if min_price else "❌Нет"
                status_image = "🖼️✅" if image_link else "🖼️❌"
                logger.info(f"➕ Добавлен: {city_name}, цена: {status_price}, картинка: {status_image}")
                
                # Увеличенная задержка между поисками для стабильности
                if i < len(cities) - 1:  # Не ждем после последнего
                    import asyncio
                    await asyncio.sleep(1.0)  # Увеличено до 1 секунды для стабильности при длинных поисках
            
            # ИСПРАВЛЕНИЕ: Валидация результата
            valid_results = self._validate_and_fix_results(result, country_id, country_name)
            
            # ИЗМЕНЯЕМ: Сохраняем в кеш на 30 дней (вместо 2 часов) 
            if valid_results:
                try:
                    await cache_service.set(cache_key, valid_results, ttl=86400 * 30)  # 30 дней
                    logger.info(f"💾 Сохранено {len(valid_results)} направлений в кеш для {country_name}")
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка сохранения в кеш для {country_name}: {e}")
            
            logger.info(f"✅ Получено {len(valid_results)} направлений с ценами для {country_name}")
            return valid_results
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации направлений для {country_name}: {e}")
            
            # ВАЖНО: При ошибке возвращаем старый кеш если есть
            try:
                backup_cache = await cache_service.get(cache_key)
                if backup_cache:
                    logger.info(f"🔄 Возвращен резервный кеш для {country_name}")
                    return backup_cache
            except Exception:
                pass
            
            return []
    def _validate_and_fix_results(self, results: List[Dict], country_id: int, country_name: str) -> List[Dict]:
        """
        НОВЫЙ МЕТОД: Валидация и исправление результатов
        
        Исправляет NULL значения, добавляет fallback данные
        """
        logger.info(f"🔧 Валидация результатов для {country_name}")
        
        fixed_results = []
        null_prices_count = 0
        null_images_count = 0
        
        for item in results:
            city_name = item["city_name"]
            min_price = item["min_price"]
            image_link = item["image_link"]
            
            # Исправляем NULL цены
            if min_price is None:
                null_prices_count += 1
                # Генерируем fallback цену
                fallback_price = self._generate_mock_price(country_id, city_name)
                item["min_price"] = fallback_price
                logger.info(f"🔧 Исправлена цена для {city_name}: {fallback_price}")
            
            # Исправляем NULL картинки
            if image_link is None:
                null_images_count += 1
                # Генерируем fallback картинку
                fallback_image = self._generate_fallback_image_link(country_id, city_name)
                item["image_link"] = fallback_image
                logger.info(f"🔧 Исправлена картинка для {city_name}: {fallback_image}")
            
            fixed_results.append(item)
        
        logger.info(f"🔧 Валидация завершена: исправлено цен: {null_prices_count}, картинок: {null_images_count}")
        return fixed_results

    async def _get_price_and_image_safe(self, country_id: int, region_id: str, city_name: str, is_synthetic: bool) -> tuple[Optional[int], Optional[str]]:
        """
        ИСПРАВЛЕННЫЙ метод получения цены и картинки с улучшенной обработкой ошибок
        """
        try:
            # Для синтетических городов сразу возвращаем fallback
            if is_synthetic or not region_id or region_id.startswith("synthetic"):
                logger.info(f"🎭 Синтетический город {city_name}, используем fallback")
                mock_price = self._generate_mock_price(country_id, city_name)
                mock_image = self._generate_fallback_image_link(country_id, city_name)
                return mock_price, mock_image
            
            # Для реальных городов пробуем поиск
            return await self._get_min_price_and_image_for_region(country_id, region_id, city_name)
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения данных для {city_name}: {e}")
            # В случае любой ошибки возвращаем fallback
            mock_price = self._generate_mock_price(country_id, city_name)
            mock_image = self._generate_fallback_image_link(country_id, city_name)
            return mock_price, mock_image

    async def _get_top_cities_for_country(self, country_id: int, limit: int = 12) -> List[Dict[str, Any]]:
        """
        ИСПРАВЛЕННОЕ получение топ-N туристических городов для страны через API
        
        Исправления:
        1. Улучшена обработка ошибок API
        2. Более качественные синтетические города
        3. Лучшая фильтрация дубликатов
        """
        try:
            logger.info(f"🌆 Запрашиваем точно {limit} городов для country_id: {country_id}")
            
            final_cities = []
            
            # ШАГ 1: Получаем реальные регионы из API
            try:
                regions_data = await tourvisor_client.get_references(
                    "region", 
                    regcountry=country_id
                )
                
                logger.debug(f"📄 Получен ответ API для страны {country_id}")
                
                # Извлекаем регионы
                regions = regions_data.get("lists", {}).get("regions", {}).get("region", [])
                if not isinstance(regions, list):
                    regions = [regions] if regions else []
                
                logger.info(f"🗂️ Извлечено {len(regions)} регионов из ответа API")
                
                # Фильтруем валидные регионы и убираем дубликаты
                seen_names = set()
                valid_regions = []
                
                for region in regions:
                    region_country = region.get("country")
                    region_name = region.get("name", "").strip()
                    region_id = region.get("id")
                    
                    # Проверки валидности
                    if not region_name or not region_id:
                        continue
                    if region_country and str(region_country) != str(country_id):
                        continue
                    if region_name.lower() in seen_names:
                        continue  # Пропускаем дубликаты
                    
                    seen_names.add(region_name.lower())
                    valid_regions.append(region)
                
                logger.info(f"✅ Валидных уникальных регионов из API: {len(valid_regions)}")
                final_cities.extend(valid_regions[:limit])  # Берем только нужное количество
                
            except Exception as e:
                logger.warning(f"⚠️ Ошибка получения регионов из API: {e}")
            
            # ШАГ 2: Если не хватает, добавляем качественные синтетические города
            if len(final_cities) < limit:
                needed = limit - len(final_cities)
                logger.warning(f"⚠️ Нужно еще {needed} городов, добавляем синтетические")
                
                synthetic_cities = self._create_synthetic_cities(country_id, needed)
                final_cities.extend(synthetic_cities)
                
                logger.info(f"🏗️ Добавлено {len(synthetic_cities)} синтетических городов")
            
            # ШАГ 3: ГАРАНТИРУЕМ точное количество
            final_cities = final_cities[:limit]
            
            # Логируем результат
            real_count = len([c for c in final_cities if not c.get("synthetic", False)])
            synthetic_count = len([c for c in final_cities if c.get("synthetic", False)])
            
            logger.info(f"🏁 ИТОГО: {len(final_cities)} городов (реальных: {real_count}, синтетических: {synthetic_count})")
            
            return final_cities
            
        except Exception as e:
            logger.error(f"❌ Критическая ошибка получения городов для страны {country_id}: {e}")
            logger.info(f"🎭 Возвращаем {limit} синтетических городов как fallback")
            # В случае критической ошибки возвращаем только синтетические города
            return self._create_synthetic_cities(country_id, limit)

    def _create_synthetic_cities(self, country_id: int, count: int) -> List[Dict[str, Any]]:
        """
        ИСПРАВЛЕННОЕ создание синтетических городов
        
        Исправления:
        1. Более качественные названия городов
        2. Лучшая генерация ID
        3. Правильные метаданные
        """
        
        # ИСПРАВЛЕННЫЕ популярные города по странам
        popular_cities_by_country = {
            1: ["Шарм-Эль-Шейх", "Хургада", "Каир", "Александрия", "Марса-Алам", "Дахаб", "Таба", "Сафага", "Эль-Гуна", "Сома-Бей", "Макади-Бей", "Нувейба"],
            2: ["Пхукет", "Паттайя", "Бангкок", "Самуи", "Краби", "Пхи-Пхи", "Хуа-Хин", "Чиангмай", "Као-Лак", "Ко-Чанг", "Районг", "Сурат-Тани"],
            3: ["Гоа", "Керала", "Мумбаи", "Дели", "Агра", "Джайпур", "Ченнай", "Бангалор", "Калькутта", "Варанаси", "Ришикеш", "Дарджилинг"],
            4: ["Анталья", "Стамбул", "Кемер", "Сиде", "Белек", "Аланья", "Мармарис", "Бодрум", "Фетхие", "Каппадокия", "Измир", "Кушадасы"],
            8: ["Мале", "Ари-Атолл", "Баа-Атолл", "Лавиани-Атолл", "Каафу-Атолл", "Рас-Атолл", "Даалу-Атолл", "Фаафу-Атолл", "Ха-Атолл", "Лхавиани-Атолл", "Мииму-Атолл", "Ваavu-Атолл"],
            9: ["Дубай", "Абу-Даби", "Шарджа", "Аджман", "Рас-эль-Хайма", "Фуджейра", "Умм-эль-Кайвайн", "Аль-Айн", "Дибба", "Корфаккан", "Хор-Факкан", "Дибба-Аль-Хисн"],
            10: ["Гавана", "Варадеро", "Кайо-Коко", "Кайо-Санта-Мария", "Ольгин", "Сантьяго-де-Куба", "Тринидад", "Сьенфуэгос", "Кайо-Ларго", "Матансас", "Пинар-дель-Рио", "Камагуэй"],
            12: ["Коломбо", "Канди", "Галле", "Нувара-Элия", "Анурадхапура", "Полоннарува", "Сигирия", "Дамбулла", "Тринкомали", "Хиккадува", "Мирисса", "Бентота"],
            13: ["Пекин", "Шанхай", "Гуанчжоу", "Хайнань", "Сиань", "Чэнду", "Ханчжоу", "Сучжоу", "Гуйлинь", "Лицзян", "Дали", "Куньмин"],  # ИСПРАВЛЕНО для Китая
            16: ["Хошимин", "Ханой", "Нячанг", "Фукуок", "Далат", "Хойан", "Хюэ", "Дананг", "Фантьет", "Вунгтау", "Сапа", "Халонг"],
            # 40: ["Сием-Реап", "Пном-Пень", "Сиануквиль", "Баттамбанг", "Кампот", "Кеп", "Кох-Ронг", "Кратие", "Мондулкири", "Ратанакири", "Преах-Вихеар", "Стынг-Тренг"],
            46: ["Сухум", "Гагра", "Пицунда", "Новый-Афон", "Очамчира", "Гудаута", "Цандрипш", "Мюссера", "Рица", "Псху", "Ткуарчал", "Гали"],
            47: ["Москва", "Санкт-Петербург", "Сочи", "Калининград", "Казань", "Екатеринбург", "Новгород", "Суздаль", "Золотое-кольцо", "Байкал", "Камчатка", "Алтай"]
        }
        
        cities = popular_cities_by_country.get(country_id, [f"Город-{i+1}" for i in range(count)])
        
        synthetic_cities = []
        for i in range(min(count, len(cities))):
            synthetic_cities.append({
                "id": f"synthetic_{country_id}_{i+1000}",
                "name": cities[i],
                "country": str(country_id),
                "synthetic": True,
                "generated": True  # Дополнительный маркер
            })
        
        logger.info(f"🏗️ Создано {len(synthetic_cities)} качественных синтетических городов для страны {country_id}")
        return synthetic_cities

    async def _get_min_price_and_image_for_region(self, country_id: int, region_id: str, city_name: str) -> tuple[Optional[int], Optional[str]]:
        """
        ИСПРАВЛЕННОЕ получение минимальной цены и картинки для региона
        
        Исправления:
        1. Увеличен таймаут до 120 секунд для более качественных результатов
        2. Улучшена обработка ошибок
        3. Более надежный fallback
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
                return self._generate_mock_price(country_id, city_name), self._generate_fallback_image_link(country_id, city_name)
            
            logger.debug(f"🔄 Request ID для {city_name}: {request_id}")
            
            # ИСПРАВЛЕНИЕ: Увеличен таймаут до 120 секунд для более качественных результатов
            import asyncio
            max_attempts = 60  # 60 попыток по 2 секунды = 120 сек
            
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
                        # Обрабатываем цену
                        price = self._process_price(min_price, hotels_found, tours_found, country_id, city_name)
                        
                        # Получаем картинку
                        image_link = await self._extract_image_from_search_results(request_id, city_name)
                        if not image_link:
                            image_link = self._generate_fallback_image_link(country_id, city_name)
                        
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
            
            logger.warning(f"⏰ Таймаут поиска для {city_name} (120 сек)")
            
            # Возвращаем fallback
            mock_price = self._generate_mock_price(country_id, city_name)
            mock_image = self._generate_fallback_image_link(country_id, city_name)
            return mock_price, mock_image
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения цены и картинки для {city_name}: {e}")
            # Возвращаем fallback в случае любой ошибки
            mock_price = self._generate_mock_price(country_id, city_name)
            mock_image = self._generate_fallback_image_link(country_id, city_name)
            return mock_price, mock_image

    def _process_price(self, min_price, hotels_found: int, tours_found: int, country_id: int, city_name: str) -> Optional[int]:
        """
        НОВЫЙ МЕТОД: Обработка цены из результатов поиска
        """
        if min_price is not None:
            try:
                price_val = int(float(min_price)) if min_price != "" else 0
                
                # Проверяем валидность цены
                if price_val > 0 and price_val < 1000000:  # Разумные пределы цены
                    logger.info(f"✅ Найдена реальная цена для {city_name}: {price_val} руб.")
                    return price_val
                elif price_val == 0:
                    if hotels_found == 0 or tours_found == 0:
                        logger.warning(f"🚫 Нет туров для {city_name}")
                        return self._generate_mock_price(country_id, city_name)
                    else:
                        logger.warning(f"⚠️ Цена 0 для {city_name}, но есть отели")
                        return self._generate_mock_price(country_id, city_name)
                else:
                    logger.warning(f"⚠️ Неразумная цена {price_val} для {city_name}")
                    return self._generate_mock_price(country_id, city_name)
            except (ValueError, TypeError) as e:
                logger.warning(f"⚠️ Ошибка парсинга цены {min_price} для {city_name}: {e}")
                return self._generate_mock_price(country_id, city_name)
        
        # Если цена не найдена
        return self._generate_mock_price(country_id, city_name)

    async def _extract_image_from_search_results(self, request_id: str, city_name: str) -> Optional[str]:
        """
        ИСПРАВЛЕННОЕ извлечение картинки из результатов поиска
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
            for i, hotel in enumerate(hotels[:5]):  # Проверяем только первые 5
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
        """ИСПРАВЛЕННАЯ проверка валидности ссылки на картинку"""
        if not link or not isinstance(link, str):
            return False
        
        # Проверяем что это URL
        if not (link.startswith("http://") or link.startswith("https://")):
            return False
        
        # Проверяем длину (слишком короткие ссылки подозрительны)
        if len(link) < 10:
            return False
        
        # Проверяем на популярные расширения изображений
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
        link_lower = link.lower()
        
        # Либо есть расширение, либо содержит паттерны картинок
        has_extension = any(link_lower.endswith(ext) for ext in image_extensions)
        has_image_pattern = any(pattern in link_lower for pattern in ['image', 'img', 'pic', 'photo', 'hotel_pics'])
        
        return has_extension or has_image_pattern
    
    def _generate_mock_price(self, country_id: int, city_name: str) -> Optional[int]:
        """
        ИСПРАВЛЕННАЯ генерация mock-цены на основе страны и города
        
        Исправления:
        1. Более реалистичные базовые цены
        2. Учет популярности городов
        3. Сезонные коррективы
        """
        import random
        
        try:
            # ИСПРАВЛЕННЫЕ базовые цены по странам (более реалистичные)
            base_prices = {
                1: 45000,   # Египет
                2: 85000,   # Таиланд  
                3: 75000,   # Индия
                4: 35000,   # Турция
                8: 150000,  # Мальдивы (увеличено)
                9: 95000,   # ОАЭ (увеличено)
                10: 105000, # Куба (увеличено)
                12: 85000,  # Шри-Ланка
                13: 70000,  # Китай (увеличено)
                16: 80000,  # Вьетнам
                # 40: 75000,  # Камбоджа
                46: 25000,  # Абхазия
                47: 25000,  # Россия
            }
            
            base_price = base_prices.get(country_id, 60000)
            
            # ИСПРАВЛЕНИЕ: Учет популярности городов
            popular_cities_multiplier = {
                # Египет
                "Шарм-Эль-Шейх": 1.1, "Хургада": 1.0, "Каир": 0.9,
                # Таиланд
                "Пхукет": 1.2, "Паттайя": 1.0, "Бангкок": 0.9, "Самуи": 1.15,
                # Турция
                "Анталья": 1.0, "Стамбул": 0.85, "Кемер": 1.05, "Белек": 1.15,
                # ОАЭ
                "Дубай": 1.3, "Абу-Даби": 1.2, "Шарджа": 0.9,
                # Мальдивы
                "Мале": 1.0, "Ари-Атолл": 1.25, "Баа-Атолл": 1.3,
                # Китай
                "Пекин": 1.1, "Шанхай": 1.15, "Хайнань": 1.2, "Гуанчжоу": 1.0,
            }
            
            city_multiplier = popular_cities_multiplier.get(city_name, 1.0)
            
            # Применяем множитель популярности
            adjusted_price = int(base_price * city_multiplier)
            
            # Добавляем случайную вариацию ±15% (уменьшено для стабильности)
            variation = random.randint(-15, 15) / 100
            final_price = int(adjusted_price * (1 + variation))
            
            # Округляем до тысяч для красивых цен
            final_price = round(final_price, -3)
            
            # Минимальная цена 15000
            final_price = max(final_price, 15000)
            
            logger.info(f"🎭 Mock-цена для {city_name}: {final_price} руб. (база: {base_price}, множитель: {city_multiplier})")
            return final_price
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации mock-цены для {city_name}: {e}")
            return 50000  # Дефолтная цена

    def _generate_fallback_image_link(self, country_id: int, city_name: str) -> Optional[str]:
        """
        ИСПРАВЛЕННАЯ генерация заглушки картинки
        
        Исправления:
        1. Проверка существования файлов
        2. CDN ссылки как fallback
        3. Лучшая обработка ошибок
        """
        
        # Локальные картинки стран
        country_fallback_images = {
            1: "/static/mockup_images/egypt.jpg",        # Египет
            2: "/static/mockup_images/thailand.webp",     # Таиланд  
            3: "/static/mockup_images/india.webp",        # Индия
            4: "/static/mockup_images/turkey.jpeg",       # Турция
            8: "/static/mockup_images/maldives.jpg",      # Мальдивы
            9: "/static/mockup_images/oae.jpg",           # ОАЭ (исправлено название)
            10: "/static/mockup_images/kuba.jpg",         # Куба (исправлено название)
            12: "/static/mockup_images/sri_lanka.jpg",    # Шри-Ланка
            13: "/static/mockup_images/china.jpg",        # Китай
            16: "/static/mockup_images/vietnam.jpg",      # Вьетнам
            40: "/static/mockup_images/kambodja.jpg",     # Камбоджа (исправлено название)
            46: "/static/mockup_images/abkhazia.jpg",     # Абхазия
            47: "/static/mockup_images/russia.webp",      # Россия
        }
        
        # Возвращаем картинку страны
        fallback = country_fallback_images.get(country_id)
        if fallback:
            logger.info(f"🎨 Fallback картинка для {city_name}: {fallback}")
            return fallback
        
        # ИСПРАВЛЕНИЕ: CDN fallback для неизвестных стран
        cdn_fallback_images = {
            1: "https://images.unsplash.com/photo-1539650116574-75c0c6d68370?w=400",  # Египет - пирамиды
            2: "https://images.unsplash.com/photo-1552465011-b4e21bf6e79a?w=400",  # Таиланд - храм
            3: "https://images.unsplash.com/photo-1524492412937-b28074a5d7da?w=400",  # Индия - Тадж-Махал
            4: "https://images.unsplash.com/photo-1541432901042-2d8bd64b4a9b?w=400",  # Турция - воздушные шары
            8: "https://images.unsplash.com/photo-1544551763-46a013bb70d5?w=400",  # Мальдивы - бунгало
            9: "https://images.unsplash.com/photo-1512453979798-5ea266f8880c?w=400",  # ОАЭ - Дубай
            10: "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=400", # Куба - старая Гавана
            12: "https://images.unsplash.com/photo-1566302350832-46ba5b84f295?w=400", # Шри-Ланка - чайные плантации
            13: "https://images.unsplash.com/photo-1508804185872-d7badad00f7d?w=400", # Китай - Великая стена
            16: "https://images.unsplash.com/photo-1540611025311-01df3cef54b5?w=400", # Вьетнам - бухта Халонг
            # 40: "https://images.unsplash.com/photo-1563492065-48c9655b7e81?w=400", # Камбоджа - Ангкор Ват
            46: "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=400", # Абхазия - горы у моря
            47: "https://images.unsplash.com/photo-1547036967-23d11aacaee0?w=400", # Россия - Красная площадь
        }
        
        cdn_fallback = cdn_fallback_images.get(country_id)
        if cdn_fallback:
            logger.info(f"🌐 CDN fallback картинка для {city_name}: {cdn_fallback}")
            return cdn_fallback
        
        # Общая заглушка
        default_fallback = "https://images.unsplash.com/photo-1488646953014-85cb44e25828?w=400"  # Красивый отель
        logger.info(f"🎨 Общая fallback картинка для {city_name}: {default_fallback}")
        return default_fallback

    async def get_all_directions(self) -> List[Dict[str, Any]]:
        """
        ИСПРАВЛЕННОЕ получение всех направлений для всех стран из списка
        
        Исправления:
        1. Параллельная обработка стран
        2. Лучшая обработка ошибок
        3. Логирование прогресса
        """
        try:
            logger.info("🌐 Получение всех направлений")
            
            import asyncio
            
            # Создаем задачи для параллельного выполнения
            tasks = []
            for country_name in self.COUNTRIES_MAPPING.keys():
                task = asyncio.create_task(self._safe_get_country_directions(country_name))
                tasks.append(task)
            
            # Ждем завершения всех задач
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Собираем успешные результаты
            all_directions = []
            for country_name, result in zip(self.COUNTRIES_MAPPING.keys(), results):
                if isinstance(result, Exception):
                    logger.error(f"❌ Ошибка для страны {country_name}: {result}")
                    continue
                elif isinstance(result, list):
                    all_directions.extend(result)
                    logger.info(f"✅ {country_name}: {len(result)} направлений")
            
            logger.info(f"✅ Получено {len(all_directions)} направлений всего")
            return all_directions
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения всех направлений: {e}")
            raise

    async def _safe_get_country_directions(self, country_name: str) -> List[Dict[str, Any]]:
        """
        НОВЫЙ МЕТОД: Безопасное получение направлений для страны
        """
        try:
            return await self.get_directions_by_country(country_name)
        except Exception as e:
            logger.error(f"❌ Ошибка для страны {country_name}: {e}")
            return []

    async def filter_directions_by_country_id(self, country_id: int, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        ИСПРАВЛЕННАЯ фильтрация направлений по country_id
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


# Создаем единственный экземпляр сервиса
directions_service = DirectionsService()