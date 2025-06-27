# app/services/specific_tour_service.py

import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from app.core.tourvisor_client import tourvisor_client
from app.services.cache_service import cache_service
from app.models.tour import FoundTourInfo, SpecificTourSearchRequest
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class SpecificTourService:
    """Сервис для поиска конкретных туров по критериям"""
    
    def __init__(self):
        self.cache = cache_service
        
        # Маппинг типов питания (код -> название)
        self.meal_types = {
            1: "Без питания",
            2: "Завтрак", 
            3: "Полупансион",
            4: "Полный пансион",
            5: "Всё включено",
            6: "Ultra All Inclusive",
            7: "All Inclusive"
        }
    
    async def find_specific_tour(self, search_request: SpecificTourSearchRequest) -> Dict[str, Any]:
        """Поиск конкретного тура по критериям - возвращает отель и все туры в него"""
        try:
            logger.info(f"🔎 Поиск тура: страна {search_request.country}, вылет {search_request.departure}")
            
            # Генерируем ключ кэша
            cache_key = self._generate_cache_key(search_request)
            
            # Проверяем кэш
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                logger.info("✅ Найден результат в кэше")
                return cached_result
            
            # Выполняем поиск
            found_hotel_with_tours = await self._execute_tour_search(search_request)
            
            if not found_hotel_with_tours:
                # Пробуем расширенный поиск
                logger.info("🔍 Основной поиск не дал результатов, пробуем fallback")
                found_hotel_with_tours = await self._execute_fallback_search(search_request)
            
            if found_hotel_with_tours:
                # Кэшируем результат на 30 минут
                await self.cache.set(cache_key, found_hotel_with_tours, ttl=1800)
                logger.info(f"✅ Найден отель: {found_hotel_with_tours['hotel_info']['hotel_name']} с {len(found_hotel_with_tours['tours'])} турами")
                return found_hotel_with_tours
            else:
                raise ValueError("Тур не найден по заданным критериям")
                
        except Exception as e:
            logger.error(f"❌ Ошибка поиска конкретного тура: {e}")
            raise
    
    async def find_tour_by_hotel_name(self, hotel_name: str, departure: int, country: int, 
                                    nights: int = 7, adults: int = 2, children: int = 0) -> Dict[str, Any]:
        """Упрощенный поиск тура по названию отеля"""
        search_request = SpecificTourSearchRequest(
            departure=departure,
            country=country,
            hotel_name=hotel_name,
            nights=nights,
            adults=adults,
            children=children
        )
        return await self.find_specific_tour(search_request)
    
    async def find_tour_by_criteria(self, departure: int, country: int, hotel_stars: int,
                                  meal_type: int, max_price: Optional[int] = None,
                                  nights: int = 7, adults: int = 2) -> Dict[str, Any]:
        """Поиск тура по основным критериям"""
        search_request = SpecificTourSearchRequest(
            departure=departure,
            country=country,
            hotel_stars=hotel_stars,
            meal_type=meal_type,
            max_price=max_price,
            nights=nights,
            adults=adults
        )
        return await self.find_specific_tour(search_request)
    
    async def _execute_tour_search(self, search_request: SpecificTourSearchRequest) -> Optional[Dict[str, Any]]:
        """Выполнение точного поиска тура"""
        try:
            # Строим параметры для TourVisor API
            search_params = self._build_search_params(search_request)
            
            # Если указано название отеля, найдем его ID
            if search_request.hotel_name and not search_request.hotel_id:
                hotel_id = await self._find_hotel_id_by_name(
                    search_request.hotel_name, 
                    search_request.country
                )
                if hotel_id:
                    search_params["hotels"] = hotel_id
                    logger.info(f"🏨 Найден ID отеля '{search_request.hotel_name}': {hotel_id}")
                else:
                    logger.warning(f"❌ Не найден ID для отеля '{search_request.hotel_name}'")
                    return None
            
            # Выполняем поиск
            logger.info(f"🔍 Параметры поиска: {search_params}")
            
            # Запускаем поиск
            request_id = await tourvisor_client.search_tours(search_params)
            
            # Ждем результатов (максимум 12 секунд)
            for attempt in range(12):
                await asyncio.sleep(1)
                
                status = await tourvisor_client.get_search_status(request_id)
                status_data = status.get("data", {}).get("status", {})
                
                state = status_data.get("state", "searching")
                hotels_found = int(status_data.get("hotelsfound", 0)) if status_data.get("hotelsfound") else 0
                
                logger.info(f"🔍 Поиск: попытка {attempt+1}, состояние: {state}, отелей найдено: {hotels_found}")
                
                # Прерываем если есть результаты или поиск завершен
                if state == "finished" or (hotels_found > 0 and attempt >= 3):
                    break
            
            # Получаем результаты
            results = await tourvisor_client.get_search_results(request_id, 1, 10)
            logger.info(f"🔍 Получены результаты поиска")
            
            # Извлекаем результат
            hotel_with_tours = await self._extract_hotel_with_all_tours(results, search_request)
            
            if hotel_with_tours:
                logger.info(f"✅ Найден отель с турами: {hotel_with_tours['hotel_info']['hotel_name']}")
                return hotel_with_tours
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка выполнения поиска: {e}")
            return None
    
    async def _execute_fallback_search(self, search_request: SpecificTourSearchRequest) -> Optional[Dict[str, Any]]:
        """Выполнение fallback поиска с расширенными параметрами"""
        try:
            logger.info("🔍 Выполняется fallback поиск")
            
            # Создаем копию запроса для fallback
            fallback_request = SpecificTourSearchRequest(**search_request.dict())
            
            # Убираем ограничения для более широкого поиска
            fallback_strategies = [
                {"remove": ["meal_type"], "description": "без ограничений по питанию"},
                {"remove": ["hotel_stars"], "description": "без ограничений по звездности"},
                {"remove": ["nights"], "description": "без ограничений по количеству ночей"},
                {"modify": {"max_price": None}, "description": "без ограничений по цене"},
                {"modify": {"date_from": None, "date_to": None}, "description": "без ограничений по датам"}
            ]
            
            for strategy in fallback_strategies:
                # Применяем стратегию
                if "remove" in strategy:
                    for field in strategy["remove"]:
                        setattr(fallback_request, field, None)
                
                if "modify" in strategy:
                    for field, value in strategy["modify"].items():
                        setattr(fallback_request, field, value)
                
                logger.info(f"🔄 Пробуем fallback стратегию: {strategy['description']}")
                
                # Выполняем поиск с измененными параметрами
                result = await self._execute_tour_search(fallback_request)
                
                if result:
                    result["is_fallback"] = True
                    result["fallback_strategy"] = strategy["description"]
                    logger.info(f"✅ Fallback успешен: {strategy['description']}")
                    return result
            
            logger.warning("❌ Все fallback стратегии не дали результатов")
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка fallback поиска: {e}")
            return None
    
    async def _extract_hotel_with_all_tours(self, results: Dict[str, Any], 
                                          search_request: SpecificTourSearchRequest) -> Optional[Dict[str, Any]]:
        """Извлечение отеля со всеми турами из результатов поиска"""
        try:
            data = results.get("data", {})
            result_data = data.get("result", {})
            hotel_list = result_data.get("hotel", [])
            
            if not isinstance(hotel_list, list):
                hotel_list = [hotel_list] if hotel_list else []
            
            if not hotel_list:
                logger.warning("❌ Отели не найдены в результатах поиска")
                return None
            
            logger.info(f"🏨 Найдено отелей: {len(hotel_list)}")
            
            # Выбираем лучший отель по релевантности
            best_hotel = self._select_best_hotel(hotel_list, search_request)
            
            if not best_hotel:
                logger.warning("❌ Не удалось выбрать лучший отель")
                return None
            
            # Собираем все туры для этого отеля
            tours_data = best_hotel.get("tours", {}).get("tour", [])
            
            if not isinstance(tours_data, list):
                tours_data = [tours_data] if tours_data else []
            
            logger.info(f"🎫 Найдено туров для отеля: {len(tours_data)}")
            
            # Получаем полную информацию об отеле
            hotel_code = best_hotel.get("hotelcode")
            hotel_info = await self._create_complete_hotel_info(best_hotel, hotel_code)
            
            # Создаем список всех туров
            all_tours = []
            for tour_data in tours_data:
                tour_info = self._create_tour_info(best_hotel, tour_data)
                all_tours.append(tour_info)
            
            # Сортируем туры по цене
            all_tours.sort(key=lambda x: x.get("price", 0))
            
            # Собираем статистику по турам
            tour_stats = self._calculate_tour_statistics(all_tours)
            
            return {
                "hotel_info": hotel_info,
                "tours": all_tours,
                "tours_count": len(all_tours),
                "search_results_count": len(hotel_list),
                "is_fallback": False,
                "fallback_strategy": None,
                **tour_stats
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка извлечения отеля с турами: {e}")
            return None
    
    async def _create_complete_hotel_info(self, hotel_data: Dict, hotel_code: str) -> Dict[str, Any]:
        """Создание полной информации об отеле"""
        try:
            # Базовая информация из результатов поиска
            base_info = self._create_hotel_info(hotel_data)
            
            # Получаем детальную информацию об отеле
            try:
                logger.info(f"🏨 Получаем детальную информацию об отеле {hotel_code}")
                detailed_info = await tourvisor_client.get_hotel_info(hotel_code, include_reviews=True)
                
                # Объединяем базовую и детальную информацию
                complete_info = self._merge_hotel_info(base_info, detailed_info)
                logger.info(f"✅ Получена полная информация об отеле {hotel_code}")
                
                return complete_info
                
            except Exception as detail_error:
                logger.warning(f"⚠️ Не удалось получить детальную информацию об отеле {hotel_code}: {detail_error}")
                # Возвращаем базовую информацию, если детальную получить не удалось
                return base_info
            
        except Exception as e:
            logger.error(f"❌ Ошибка создания информации об отеле: {e}")
            return self._create_hotel_info(hotel_data)
    
    def _merge_hotel_info(self, base_info: Dict, detailed_info: Dict) -> Dict[str, Any]:
        """Объединение базовой и детальной информации об отеле"""
        try:
            # Извлекаем данные из детального ответа
            hotel_details = detailed_info.get("data", {})
            
            # Создаем полную информацию об отеле
            complete_info = base_info.copy()
            
            # Обновляем основную информацию
            complete_info.update({
                # Контактная информация
                "phone": hotel_details.get("phone"),
                "website": hotel_details.get("site"),
                
                # Техническая информация
                "build_year": self._safe_int(hotel_details.get("build")),
                "renovation_year": self._safe_int(hotel_details.get("repair")),
                "hotel_area": hotel_details.get("square"),
                
                # Расширенное описание
                "description": hotel_details.get("description") or base_info.get("hotel_description"),
                "placement": hotel_details.get("placement"),
                
                # Координаты
                "location": {
                    "latitude": self._safe_float(hotel_details.get("coord1")),
                    "longitude": self._safe_float(hotel_details.get("coord2")),
                    "distance_to_sea": base_info.get("sea_distance")
                } if hotel_details.get("coord1") and hotel_details.get("coord2") else None,
                
                # Удобства и услуги
                "facilities": {
                    "territory": hotel_details.get("territory"),
                    "in_room": hotel_details.get("inroom"),
                    "room_types": self._parse_list_field(hotel_details.get("roomtypes")),
                    "services": self._parse_list_field(hotel_details.get("services")),
                    "services_free": self._parse_list_field(hotel_details.get("servicefree")),
                    "services_paid": self._parse_list_field(hotel_details.get("servicepay")),
                    "animation": hotel_details.get("animation"),
                    "child_services": hotel_details.get("child"),
                    "beach_description": hotel_details.get("beach"),
                    "meal_types": self._parse_list_field(hotel_details.get("meallist")),
                    "meal_description": hotel_details.get("mealtypes")
                },
                
                # Изображения
                "images": self._parse_images(hotel_details.get("images", [])),
                "images_count": self._safe_int(hotel_details.get("imagescount")),
                "main_image": hotel_details.get("images", [{}])[0] if hotel_details.get("images") else base_info.get("hotel_picture"),
                
                # Отзывы
                "reviews": self._parse_reviews(hotel_details.get("reviews", [])),
                
                # Обновляем метаданные
                "has_photos": bool(hotel_details.get("images")) or base_info.get("is_photo", False),
                "has_coordinates": bool(hotel_details.get("coord1") and hotel_details.get("coord2")) or base_info.get("is_coords", False),
                "has_description": bool(hotel_details.get("description")) or base_info.get("is_description", False),
                "has_reviews": bool(hotel_details.get("reviews")) or base_info.get("is_reviews", False),
            })
            
            return complete_info
            
        except Exception as e:
            logger.error(f"❌ Ошибка объединения информации об отеле: {e}")
            return base_info
    
    def _parse_images(self, images_data: Any) -> List[Dict[str, Any]]:
        """Парсинг изображений отеля"""
        try:
            if not images_data:
                return []
            
            images = []
            
            # Если images_data это список
            if isinstance(images_data, list):
                for img in images_data:
                    if isinstance(img, dict):
                        images.append({
                            "url": img.get("image") or img.get("url") or str(img),
                            "description": img.get("description")
                        })
                    else:
                        images.append({
                            "url": str(img),
                            "description": None
                        })
            
            # Если images_data это строка (одно изображение)
            elif isinstance(images_data, str):
                images.append({
                    "url": images_data,
                    "description": None
                })
            
            # Если images_data это словарь с ключом image
            elif isinstance(images_data, dict):
                image_list = images_data.get("image", [])
                if not isinstance(image_list, list):
                    image_list = [image_list] if image_list else []
                
                for img in image_list:
                    if isinstance(img, str):
                        images.append({
                            "url": img,
                            "description": None
                        })
                    elif isinstance(img, dict):
                        images.append({
                            "url": img.get("url") or str(img),
                            "description": img.get("description")
                        })
            
            return images
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга изображений: {e}")
            return []
    
    def _parse_reviews(self, reviews_data: Any) -> List[Dict[str, Any]]:
        """Парсинг отзывов об отеле"""
        try:
            if not reviews_data:
                return []
            
            reviews = []
            
            # Если reviews_data это словарь с ключом review
            if isinstance(reviews_data, dict):
                review_list = reviews_data.get("review", [])
                if not isinstance(review_list, list):
                    review_list = [review_list] if review_list else []
            elif isinstance(reviews_data, list):
                review_list = reviews_data
            else:
                return []
            
            for review in review_list:
                if isinstance(review, dict):
                    reviews.append({
                        "name": review.get("name"),
                        "content": review.get("content"),
                        "positive": review.get("positive"),
                        "negative": review.get("negative"),
                        "travel_time": review.get("traveltime"),
                        "rate": self._safe_int(review.get("rate")),
                        "review_date": review.get("reviewdate"),
                        "review_time": review.get("reviewtime"),
                        "source_link": review.get("sourcelink")
                    })
            
            return reviews[:5]  # Ограничиваем до 5 отзывов
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга отзывов: {e}")
            return []
    
    def _parse_list_field(self, field_data: Any) -> List[str]:
        """Парсинг списковых полей (услуги, типы номеров и т.д.)"""
        try:
            if not field_data:
                return []
            
            if isinstance(field_data, str):
                # Разделяем по точке с запятой (если removetags=1)
                if ';' in field_data:
                    return [item.strip() for item in field_data.split(';') if item.strip()]
                # Или по переносам строк
                elif '\n' in field_data:
                    return [item.strip() for item in field_data.split('\n') if item.strip()]
                else:
                    return [field_data.strip()]
            
            elif isinstance(field_data, list):
                return [str(item).strip() for item in field_data if str(item).strip()]
            
            else:
                return [str(field_data).strip()] if str(field_data).strip() else []
                
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга спискового поля: {e}")
            return []
    
    def _calculate_tour_statistics(self, tours: List[Dict]) -> Dict[str, Any]:
        """Расчет статистики по турам"""
        try:
            if not tours:
                return {
                    "price_range": None,
                    "operators": [],
                    "available_dates": [],
                    "meal_types": []
                }
            
            prices = [tour.get("price", 0) for tour in tours if tour.get("price")]
            operators = list(set([tour.get("operator_name") for tour in tours if tour.get("operator_name")]))
            dates = list(set([tour.get("fly_date") for tour in tours if tour.get("fly_date")]))
            meals = list(set([tour.get("meal") for tour in tours if tour.get("meal")]))
            
            return {
                "price_range": {
                    "min": min(prices) if prices else 0,
                    "max": max(prices) if prices else 0,
                    "avg": sum(prices) / len(prices) if prices else 0
                },
                "operators": operators,
                "available_dates": sorted(dates),
                "meal_types": meals
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка расчета статистики туров: {e}")
            return {
                "price_range": None,
                "operators": [],
                "available_dates": [],
                "meal_types": []
            }
    
    def _select_best_hotel(self, hotel_list: List[Dict], search_request: SpecificTourSearchRequest) -> Optional[Dict]:
        """Выбор лучшего отеля из списка по релевантности"""
        if not hotel_list:
            return None
        
        # Если указан конкретный отель по ID или имени, ищем его
        if search_request.hotel_id:
            for hotel in hotel_list:
                if str(hotel.get("hotelcode")) == str(search_request.hotel_id):
                    return hotel
        
        if search_request.hotel_name:
            search_name = search_request.hotel_name.lower()
            for hotel in hotel_list:
                hotel_name = hotel.get("hotelname", "").lower()
                if search_name in hotel_name:
                    return hotel
        
        # Иначе сортируем по релевантности и берем первый
        scored_hotels = []
        for hotel in hotel_list:
            score = self._calculate_hotel_score(hotel, search_request)
            scored_hotels.append((score, hotel))
        
        scored_hotels.sort(key=lambda x: x[0], reverse=True)
        return scored_hotels[0][1] if scored_hotels else None
    
    def _calculate_hotel_score(self, hotel: Dict, search_request: SpecificTourSearchRequest) -> float:
        """Расчет релевантности отеля"""
        score = 0.0
        
        # Звездность отеля
        if search_request.hotel_stars:
            hotel_stars = int(hotel.get("hotelstars", 0))
            if hotel_stars == search_request.hotel_stars:
                score += 10
            elif abs(hotel_stars - search_request.hotel_stars) == 1:
                score += 5
        
        # Рейтинг отеля
        hotel_rating = float(hotel.get("hotelrating", 0))
        if hotel_rating > 0:
            if search_request.rating and hotel_rating >= search_request.rating:
                score += 8
            else:
                score += hotel_rating * 2
        
        # Расстояние до моря (чем меньше, тем лучше)
        sea_distance = int(hotel.get("seadistance", 1000))
        if sea_distance <= 100:
            score += 5
        elif sea_distance <= 300:
            score += 3
        elif sea_distance <= 500:
            score += 1
        
        return score
    
    # Заменить метод _create_hotel_info в app/services/specific_tour_service.py

    def _create_hotel_info(self, hotel_data: Dict) -> Dict[str, Any]:
        """Создание базовой информации об отеле"""
        return {
            "hotel_id": self._safe_string(hotel_data.get("hotelcode")),
            "hotel_name": self._safe_string(hotel_data.get("hotelname", "")),
            "hotel_stars": self._safe_int(hotel_data.get("hotelstars")) or 3,
            "hotel_rating": self._safe_float(hotel_data.get("hotelrating")),
            "hotel_description": self._safe_string(hotel_data.get("hoteldescription")),
            "hotel_picture": self._safe_string(hotel_data.get("picturelink")),
            "hotel_review_link": self._safe_string(hotel_data.get("reviewlink")),
            "country_name": self._safe_string(hotel_data.get("countryname", "")),
            "country_code": self._safe_int(hotel_data.get("countrycode")) or 0,
            "region_name": self._safe_string(hotel_data.get("regionname", "")),
            "region_code": self._safe_int(hotel_data.get("regioncode")) or 0,
            "sea_distance": self._safe_int(hotel_data.get("seadistance")) or 0,
            "is_photo": bool(hotel_data.get("isphoto", 0)),
            "is_coords": bool(hotel_data.get("iscoords", 0)),
            "is_description": bool(hotel_data.get("isdescription", 0)),
            "is_reviews": bool(hotel_data.get("isreviews", 0)),
            "full_description_link": self._safe_string(hotel_data.get("fulldesclink"))
        }
    
    def _create_tour_info(self, hotel_data: Dict, tour_data: Dict) -> Dict[str, Any]:
        """Создание информации о туре"""
        return {
            "tour_id": self._safe_string(tour_data.get("tourid")),
            "operator_name": self._safe_string(tour_data.get("operatorname", "")),
            "operator_code": self._safe_string(tour_data.get("operatorcode")),
            "fly_date": self._safe_string(tour_data.get("flydate")),
            "nights": self._safe_int(tour_data.get("nights")) or 7,
            "price": self._safe_int(tour_data.get("price")) or 0,
            "fuel_charge": self._safe_int(tour_data.get("fuelcharge")) or 0,
            "price_ue": self._safe_float(tour_data.get("priceue")),
            "meal": self._safe_string(tour_data.get("meal", "")),
            "meal_russian": self._safe_string(tour_data.get("mealrussian", "")),
            "room_type": self._safe_string(tour_data.get("room", "")),
            "placement": self._safe_string(tour_data.get("placement", "")),
            "adults": self._safe_int(tour_data.get("adults")) or 2,
            "children": self._safe_int(tour_data.get("child")) or 0,
            "tour_name": self._safe_string(tour_data.get("tourname", "")),
            "tour_link": self._safe_string(tour_data.get("tourlink")),
            "currency": self._safe_string(tour_data.get("currency", "RUB")),
            "is_regular": bool(tour_data.get("regular", 0)),
            "is_promo": bool(tour_data.get("promo", 0)),
            "is_on_request": bool(tour_data.get("onrequest", 0)),
            "flight_status": self._safe_int(tour_data.get("flightstatus")),
            "hotel_status": self._safe_int(tour_data.get("hotelstatus")) or 1
        }

    def _safe_string(self, value: Any) -> str:
        """Безопасное преобразование в строку"""
        try:
            if value is None:
                return ""
            elif isinstance(value, dict):
                # Если пришел пустой словарь, возвращаем пустую строку
                return ""
            elif isinstance(value, (list, tuple)):
                # Если пришел список, возвращаем пустую строку
                return ""
            else:
                return str(value).strip()
        except (ValueError, TypeError):
            return ""

    def _build_search_params(self, search_request: SpecificTourSearchRequest) -> Dict[str, Any]:
        """Построение параметров для API TourVisor"""
        # Базовые параметры согласно документации TourVisor
        params = {
            "format": "xml",
            "departure": search_request.departure,
            "country": search_request.country,
            "adults": search_request.adults,
            "onpage": 10  # Ограничиваем количество результатов
        }
        
        # Опциональные параметры
        if search_request.children:
            params["child"] = search_request.children
        
        # Ночи - используем nightsfrom и nightsto
        if search_request.nights:
            params["nightsfrom"] = search_request.nights
            params["nightsto"] = search_request.nights
        else:
            # По умолчанию 7-10 ночей
            params["nightsfrom"] = 7
            params["nightsto"] = 10
        
        # Даты - если не указаны, берем ближайшие 2 недели
        if not search_request.date_from:
            start_date = datetime.now() + timedelta(days=7)
            params["datefrom"] = start_date.strftime("%d.%m.%Y")
        else:
            params["datefrom"] = search_request.date_from
        
        if not search_request.date_to:
            end_date = datetime.now() + timedelta(days=21)
            params["dateto"] = end_date.strftime("%d.%m.%Y")
        else:
            params["dateto"] = search_request.date_to
        
        # Звездность отеля
        if search_request.hotel_stars:
            params["stars"] = search_request.hotel_stars
        
        # ID отеля
        if search_request.hotel_id:
            params["hotels"] = search_request.hotel_id
        
        # Регион
        if search_request.region_code:
            params["regions"] = search_request.region_code
        
        # Тип питания
        if search_request.meal_type:
            params["meal"] = search_request.meal_type
        
        # Цена
        if search_request.max_price:
            params["priceto"] = search_request.max_price
        
        if search_request.min_price:
            params["pricefrom"] = search_request.min_price
        
        return params
async def _find_hotel_id_by_name(self, hotel_name: str, country_code: int) -> Optional[str]:
    """Поиск ID отеля по названию - ИСПРАВЛЕНО!"""
    try:
        logger.info(f"🔍 Поиск отеля '{hotel_name}' в стране {country_code}")
        
        # Получаем список отелей для страны
        hotels_data = await tourvisor_client.get_references(
            "hotel",
            hotcountry=country_code
        )
        
        # ИСПРАВЛЕНИЕ: отели находятся в другой структуре!
        hotels = []
        if "lists" in hotels_data and "hotels" in hotels_data["lists"]:
            hotels = hotels_data["lists"]["hotels"].get("hotel", [])
        else:
            # Fallback к старой структуре
            hotels = hotels_data.get("hotel", [])
        
        if not isinstance(hotels, list):
            hotels = [hotels] if hotels else []
        
        logger.info(f"📊 Найдено {len(hotels)} отелей в стране {country_code}")
        
        # Показываем первые 5 отелей для отладки
        if hotels:
            sample_names = [h.get("name", "NO_NAME") for h in hotels[:5]]
            logger.info(f"📝 Примеры отелей: {sample_names}")
        else:
            logger.warning(f"❌ Нет отелей для страны {country_code}!")
            return None
        
        # Ищем отель по имени (частичное совпадение)
        search_name = hotel_name.lower()
        
        # Сначала пытаемся найти точное совпадение
        for hotel in hotels:
            hotel_name_full = hotel.get("name", "").lower()
            if search_name == hotel_name_full:
                logger.info(f"✅ Точное совпадение: {hotel.get('name')} (ID: {hotel.get('id')})")
                return hotel.get("id")
        
        # Затем ищем частичное совпадение
        for hotel in hotels:
            hotel_name_full = hotel.get("name", "").lower()
            if search_name in hotel_name_full or hotel_name_full in search_name:
                logger.info(f"✅ Частичное совпадение: {hotel.get('name')} (ID: {hotel.get('id')})")
                return hotel.get("id")
        
        logger.warning(f"❌ Отель '{hotel_name}' не найден среди {len(hotels)} отелей")
        return None
        
    except Exception as e:
        logger.error(f"❌ Ошибка поиска отеля: {e}")
        return None
    def _generate_cache_key(self, search_request: SpecificTourSearchRequest) -> str:
        """Генерация ключа кэша"""
        key_parts = [
            f"dep_{search_request.departure}",
            f"country_{search_request.country}",
            f"adults_{search_request.adults}",
        ]
        
        if search_request.children:
            key_parts.append(f"child_{search_request.children}")
        
        if search_request.nights:
            key_parts.append(f"nights_{search_request.nights}")
        
        if search_request.hotel_stars:
            key_parts.append(f"stars_{search_request.hotel_stars}")
        
        if search_request.hotel_id:
            key_parts.append(f"hotel_{search_request.hotel_id}")
        
        if search_request.hotel_name:
            key_parts.append(f"name_{search_request.hotel_name.lower()}")
        
        if search_request.meal_type:
            key_parts.append(f"meal_{search_request.meal_type}")
        
        if search_request.max_price:
            key_parts.append(f"maxprice_{search_request.max_price}")
        
        if search_request.min_price:
            key_parts.append(f"minprice_{search_request.min_price}")
        
        return f"specific_tour_v3:{'_'.join(key_parts)}"
    
    def _safe_int(self, value: Any) -> Optional[int]:
        """Безопасное преобразование в int"""
        try:
            return int(value) if value is not None and str(value).strip() else None
        except (ValueError, TypeError):
            return None
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """Безопасное преобразование в float"""
        try:
            return float(value) if value is not None and str(value).strip() else None
        except (ValueError, TypeError):
            return None
    
    def get_search_suggestions(self, search_request: SpecificTourSearchRequest) -> List[str]:
        """Получение предложений по изменению критериев поиска"""
        suggestions = []
        
        if search_request.hotel_stars and search_request.hotel_stars > 3:
            suggestions.append(f"Попробуйте снизить звездность до {search_request.hotel_stars - 1} звезд")
        
        if search_request.max_price and search_request.max_price < 100000:
            suggestions.append(f"Увеличьте максимальную цену до {search_request.max_price + 20000} рублей")
        
        if search_request.meal_type and search_request.meal_type > 2:
            suggestions.append("Попробуйте изменить тип питания на 'Завтрак' или 'Без питания'")
        
        if search_request.nights and search_request.nights > 7:
            suggestions.append(f"Попробуйте сократить количество ночей до {search_request.nights - 1}")
        
        if search_request.rating and search_request.rating > 4.0:
            suggestions.append("Снизьте минимальный рейтинг отеля")
        
        suggestions.append("Попробуйте изменить даты поездки")
        suggestions.append("Рассмотрите другие курорты в этой стране")
        
        return suggestions

# Создаем экземпляр сервиса
specific_tour_service = SpecificTourService()