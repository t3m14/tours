# app/api/v1/directions.py
from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional
from app.services.directions_service import directions_service
from app.services.cache_service import cache_service  # ← ДОБАВИТЬ ЭТУ СТРОКУ
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()

@router.get("/countries/list")
async def get_supported_countries():
    """
    Получение списка поддерживаемых стран с их ID
    """
    countries = []
    for name, info in directions_service.COUNTRIES_MAPPING.items():
        if info["country_id"] is not None:  # Только страны с определенными ID
            countries.append({
                "country_name": name,
                "country_id": info["country_id"]
            })
    
    return {
        "countries": countries,
        "total": len(countries)
    }

@router.get("/debug/regions/{country_id}")
async def debug_regions_for_country(country_id: int):
    """
    Отладочный endpoint для проверки получения регионов
    """
    try:
        logger.info(f"🔍 Отладка регионов для страны {country_id}")
        
        # Прямой запрос к API
        from app.core.tourvisor_client import tourvisor_client
        
        regions_data = await tourvisor_client.get_references("region", regcountry=country_id)
        
        return {
            "country_id": country_id,
            "raw_response": regions_data,
            "regions_count": len(regions_data.get("lists", {}).get("regions", {}).get("region", []))
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка отладки для страны {country_id}: {e}")
        return {
            "error": str(e),
            "country_id": country_id,
            "status": "error"
        }

@router.get("/country/{country_id}")
async def get_directions_by_country_id(country_id: int) -> Dict[str, Any]:
    """
    Получение направлений для конкретной страны по ID
    
    Args:
        country_id: ID страны (например: 4 для Турции, 1 для Египта)
        
    Returns:
        Dict: Информация о стране и список направлений
    """
    try:
        logger.info(f"🎯 API запрос направлений для country_id: {country_id}")
        
        # Находим название страны по ID
        country_name = None
        for name, info in directions_service.COUNTRIES_MAPPING.items():
            if info["country_id"] == country_id:
                country_name = name
                break
        
        if not country_name:
            raise HTTPException(status_code=404, detail=f"Страна с ID {country_id} не найдена")
        
        directions = await directions_service.get_directions_by_country(country_name)
        
        return {
            "country_name": country_name,
            "country_id": country_id,
            "total_directions": len(directions),
            "directions": directions
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка API направлений для country_id {country_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")

@router.get("/country/{country_id}/flat")
async def get_directions_flat_by_id(country_id: int) -> List[Dict[str, Any]]:
    """
    Получение направлений в плоском формате по ID страны (как в ТЗ)
    
    Формат ответа:
    {
        country_name: "Турция",
        country_id: 4,
        city_name: "Анталья", 
        min_price: 45000
    }
    
    Args:
        country_id: ID страны (например: 4 для Турции)
        
    Returns:
        List[Dict]: Список направлений с полями country_name, country_id, city_name, min_price
    """
    try:
        logger.info(f"📋 API плоский список с ценами для country_id: {country_id}")
        
        # Находим название страны по ID
        country_name = None
        for name, info in directions_service.COUNTRIES_MAPPING.items():
            if info["country_id"] == country_id:
                country_name = name
                break
        
        if not country_name:
            raise HTTPException(status_code=404, detail=f"Страна с ID {country_id} не найдена")
        
        directions = await directions_service.get_directions_by_country(country_name)
        
        logger.info(f"✅ Возвращаем {len(directions)} направлений с минимальными ценами")
        return directions
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка API плоского списка для country_id {country_id}: {e}")
@router.get("/country/{country_id}/quick")
async def get_directions_quick(country_id: int) -> List[Dict[str, Any]]:
    """
    Быстрое получение направлений без поиска цен (для тестирования)
    
    Args:
        country_id: ID страны 
        
    Returns:
        List[Dict]: Список направлений без min_price
    """
    try:
        logger.info(f"⚡ Быстрый запрос направлений для country_id: {country_id}")
        
        # Находим название страны по ID
        country_name = None
        for name, info in directions_service.COUNTRIES_MAPPING.items():
            if info["country_id"] == country_id:
                country_name = name
                break
        
        if not country_name:
            raise HTTPException(status_code=404, detail=f"Страна с ID {country_id} не найдена")
        
        # Получаем только города без поиска цен
        cities = await directions_service._get_top_cities_for_country(country_id, limit=12)
        
        result = []
        for city in cities:
            city_name = city.get("name", "")
            if city_name:
                direction_item = {
                    "country_name": country_name,
                    "country_id": country_id,
                    "city_name": city_name,
                    "min_price": None  # Без поиска цен
                }
                result.append(direction_item)
        
        logger.info(f"⚡ Быстро получено {len(result)} направлений")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка быстрого запроса для country_id {country_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")
async def get_directions_with_filter(
    country_id: Optional[int] = Query(None, description="ID страны для фильтрации"),
    limit: Optional[int] = Query(None, ge=1, le=100, description="Лимит результатов")
) -> Dict[str, Any]:
    """
    Получение направлений с фильтрацией по country_id (как в ТЗ)
    """
    try:
        logger.info(f"🔍 API фильтр направлений: country_id={country_id}, limit={limit}")
        
        # Получаем все направления
        all_directions = await directions_service.get_all_directions()
        
        # Фильтруем по country_id если указан
        if country_id is not None:
            all_directions = [d for d in all_directions if d["country_id"] == country_id]
        
        # Применяем лимит если указан
        if limit is not None:
            all_directions = all_directions[:limit]
        
        return {
            "filter_applied": {
                "country_id": country_id,
                "limit": limit
            },
            "total_results": len(all_directions),
            "directions": all_directions
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка API фильтра направлений: {e}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")

@router.get("/test/{country_id}")
async def test_country_directions_by_id(country_id: int):
    """
    Тестовый endpoint для проверки работы с конкретной страной по ID
    """
    try:
        logger.info(f"🧪 Тест направлений для country_id: {country_id}")
        
        # Находим название страны по ID
        country_name = None
        for name, info in directions_service.COUNTRIES_MAPPING.items():
            if info["country_id"] == country_id:
                country_name = name
                break
        
        if not country_name:
            return {
                "error": f"Страна с ID {country_id} не найдена",
                "available_countries": {
                    name: info["country_id"] 
                    for name, info in directions_service.COUNTRIES_MAPPING.items() 
                    if info["country_id"] is not None
                }
            }
        
        # Пытаемся получить направления
        directions = await directions_service.get_directions_by_country(country_name)
        
        return {
            "success": True,
            "country_name": country_name,
            "country_id": country_id,
            "directions_count": len(directions),
            "sample_directions": directions[:3] if directions else [],
            "status": "ok"
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка теста для country_id {country_id}: {e}")
        return {
            "error": str(e),
            "country_id": country_id,
            "status": "error"
        }
# Добавить в app/api/v1/directions.py

@router.delete("/cache/clear")
async def clear_directions_cache():
    """
    Очистка кэша направлений
    
    Удаляет все закэшированные данные направлений для всех стран.
    Полезно для принудительного обновления данных.
    """
    try:
        logger.info("🗑️ Запрос на очистку кэша направлений")
        
        # Получаем все ключи кэша связанные с направлениями
        cache_patterns = [
            "directions_with_prices_country_*",  # Кэш с ценами по странам
            "directions_country_*",              # Обычный кэш направлений
            "top_cities_country_*",              # Кэш городов
            "regions_*",                         # Кэш регионов
        ]
        
        total_deleted = 0
        deleted_by_pattern = {}
        
        for pattern in cache_patterns:
            try:
                # Получаем все ключи по паттерну
                keys = await cache_service.get_keys_pattern(pattern)
                
                if keys:
                    # Удаляем все найденные ключи
                    for key in keys:
                        await cache_service.delete(key)
                    
                    deleted_by_pattern[pattern] = len(keys)
                    total_deleted += len(keys)
                    logger.info(f"🗑️ Удалено {len(keys)} ключей по паттерну: {pattern}")
                else:
                    deleted_by_pattern[pattern] = 0
                    logger.info(f"🔍 Нет ключей для паттерна: {pattern}")
                    
            except Exception as e:
                logger.error(f"❌ Ошибка очистки паттерна {pattern}: {e}")
                deleted_by_pattern[pattern] = f"error: {str(e)}"
        
        logger.info(f"✅ Всего удалено {total_deleted} ключей кэша направлений")
        
        return {
            "success": True,
            "message": f"Кэш направлений очищен успешно",
            "total_deleted": total_deleted,
            "details": deleted_by_pattern,
            "next_actions": [
                "Следующие запросы к /directions будут генерировать новые данные",
                "Кэш будет постепенно заполняться при новых запросах"
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка очистки кэша направлений: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Ошибка при очистке кэша: {str(e)}"
        )

@router.get("/cache/status")
async def get_cache_status():
    """
    Получение статуса кэша направлений
    
    Показывает какие данные закэшированы и когда истекает срок действия.
    """
    try:
        logger.info("📊 Запрос статуса кэша направлений")
        
        cache_patterns = [
            "directions_with_prices_country_*",
            "directions_country_*", 
            "top_cities_country_*",
            "regions_*"
        ]
        
        cache_status = {}
        total_keys = 0
        
        for pattern in cache_patterns:
            try:
                keys = await cache_service.get_keys_pattern(pattern)
                
                if keys:
                    pattern_info = {
                        "count": len(keys),
                        "keys": keys[:10],  # Показываем первые 10 ключей
                        "has_more": len(keys) > 10
                    }
                    
                    # Пробуем получить TTL для первого ключа
                    if keys:
                        try:
                            ttl = await cache_service.get_ttl(keys[0])
                            if ttl:
                                pattern_info["example_ttl_seconds"] = ttl
                        except:
                            pass
                else:
                    pattern_info = {
                        "count": 0,
                        "keys": [],
                        "has_more": False
                    }
                
                cache_status[pattern] = pattern_info
                total_keys += pattern_info["count"]
                
            except Exception as e:
                cache_status[pattern] = {
                    "error": str(e),
                    "count": 0
                }
        
        return {
            "total_cached_keys": total_keys,
            "cache_patterns": cache_status,
            "recommendations": {
                "clear_cache": "POST /api/v1/directions/cache/clear",
                "force_refresh": "Добавьте параметр ?force_refresh=true к любому запросу направлений"
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения статуса кэша: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при получении статуса кэша: {str(e)}"
        )

@router.post("/refresh/{country_id}")
async def force_refresh_country_directions(country_id: int):
    """
    Принудительное обновление направлений для конкретной страны
    
    Очищает кэш и генерирует новые данные для указанной страны.
    """
    try:
        logger.info(f"🔄 Принудительное обновление направлений для страны {country_id}")
        
        # Находим название страны
        country_name = None
        for name, info in directions_service.COUNTRIES_MAPPING.items():
            if info["country_id"] == country_id:
                country_name = name
                break
        
        if not country_name:
            raise HTTPException(
                status_code=404, 
                detail=f"Страна с ID {country_id} не найдена"
            )
        
        # Очищаем кэш для этой страны
        cache_key = f"directions_with_prices_country_{country_id}"
        await cache_service.delete(cache_key)
        logger.info(f"🗑️ Очищен кэш для страны {country_name}")
        
        # Генерируем новые данные
        directions = await directions_service.get_directions_by_country(country_name)
        
        return {
            "success": True,
            "country_name": country_name,
            "country_id": country_id,
            "directions_count": len(directions),
            "message": f"Направления для {country_name} успешно обновлены",
            "directions": directions[:3]  # Показываем первые 3 для примера
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка обновления страны {country_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при обновлении: {str(e)}"
        )