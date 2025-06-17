import asyncio
from typing import Dict, Any
from datetime import datetime, timedelta

from app.core.tourvisor_client import tourvisor_client
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class PriceService:
    """Сервис для работы с ценами туров"""
    
    @staticmethod
    def get_default_prices() -> Dict[int, float]:
        """Дефолтные цены по странам"""
        return {
            1: 85000.0,    # Египет
            4: 75000.0,    # Турция
            22: 180000.0,  # Таиланд
            8: 95000.0,    # Греция
            15: 120000.0,  # ОАЭ
            35: 250000.0   # Мальдивы
        }
    
    async def get_country_min_price(self, country_code: int, country_name: str) -> float:
        """Получение минимальной цены для страны с улучшенной логикой"""
        try:
            logger.info(f"💰 Получение минимальной цены для {country_name}")
            
            # Пробуем разные варианты поиска для получения цены
            price_search_variants = [
                {  # Стандартный поиск на неделю
                    "nightsfrom": 7, "nightsto": 10,
                    "adults": 2, "child": 0
                },
                {  # Короткий тур
                    "nightsfrom": 3, "nightsto": 7,
                    "adults": 2, "child": 0
                },
                {  # Длинный тур
                    "nightsfrom": 10, "nightsto": 14,
                    "adults": 2, "child": 0
                }
            ]
            
            best_price = None
            
            for variant in price_search_variants:
                try:
                    search_params = {
                        "departure": 1,  # Москва
                        "country": country_code,
                        "datefrom": (datetime.now() + timedelta(days=7)).strftime("%d.%m.%Y"),
                        "dateto": (datetime.now() + timedelta(days=21)).strftime("%d.%m.%Y"),
                        **variant
                    }
                    
                    request_id = await tourvisor_client.search_tours(search_params)
                    
                    # Ждем результатов (максимум 5 секунд)
                    for attempt in range(5):
                        await asyncio.sleep(1)
                        
                        status_result = await tourvisor_client.get_search_status(request_id)
                        status_data = status_result.get("data", {}).get("status", {})
                        
                        # Проверяем минимальную цену в статусе
                        min_price_from_status = status_data.get("minprice")
                        if min_price_from_status and float(min_price_from_status) > 0:
                            price = float(min_price_from_status)
                            if best_price is None or price < best_price:
                                best_price = price
                            logger.info(f"💰 Найдена цена {price} для {country_name} (вариант {variant})")
                            break
                        
                        if status_data.get("state") == "finished":
                            # Получаем результаты для поиска цены
                            results = await tourvisor_client.get_search_results(request_id, 1, 5)
                            extracted_price = self._extract_min_price_from_results(results)
                            if extracted_price > 0:
                                if best_price is None or extracted_price < best_price:
                                    best_price = extracted_price
                                logger.info(f"💰 Извлечена цена {extracted_price} для {country_name}")
                            break
                    
                    # Если нашли приемлемую цену, можем остановиться
                    if best_price and best_price > 0:
                        break
                    
                    # Задержка между вариантами
                    await asyncio.sleep(0.3)
                    
                except Exception as variant_error:
                    logger.debug(f"💰 Ошибка с вариантом цены {variant}: {variant_error}")
                    continue
            
            # Если получили цену, возвращаем её
            if best_price and best_price > 0:
                logger.info(f"💰✅ Финальная цена для {country_name}: {best_price}")
                return best_price
            
            # Иначе возвращаем дефолтную цену
            default_prices = self.get_default_prices()
            fallback_price = default_prices.get(country_code, 80000.0)
            logger.warning(f"💰 Используем дефолтную цену для {country_name}: {fallback_price}")
            return fallback_price
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения цены для {country_name}: {e}")
            # Возвращаем дефолтную цену при ошибке
            default_prices = self.get_default_prices()
            return default_prices.get(country_code, 80000.0)
    
    def _extract_min_price_from_results(self, results: Dict[str, Any]) -> float:
        """Извлечение минимальной цены из результатов поиска"""
        try:
            data = results.get("data", {})
            
            # Проверяем статус
            status = data.get("status", {})
            min_price_from_status = status.get("minprice")
            if min_price_from_status:
                return float(min_price_from_status)
            
            # Ищем в результатах
            result_data = data.get("result", {})
            hotel_list = result_data.get("hotel", [])
            
            if not isinstance(hotel_list, list):
                hotel_list = [hotel_list] if hotel_list else []
            
            prices = []
            for hotel in hotel_list:
                hotel_price = hotel.get("price")
                if hotel_price:
                    prices.append(float(hotel_price))
                
                # Также проверяем цены туров
                tours = hotel.get("tours", {}).get("tour", [])
                if not isinstance(tours, list):
                    tours = [tours] if tours else []
                
                for tour in tours:
                    tour_price = tour.get("price")
                    if tour_price:
                        prices.append(float(tour_price))
            
            return min(prices) if prices else 0.0
            
        except Exception as e:
            logger.error(f"❌ Ошибка при извлечении цены: {e}")
            return 0.0

# Создаем экземпляр сервиса цен
price_service = PriceService()