# app/api/v1/directions.py - ИСПРАВЛЕННАЯ ВЕРСИЯ

from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional
from app.services.directions_service import directions_service
from app.services.cache_service import cache_service
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

@router.get("/country/{country_id}")
async def get_directions_by_country_id(country_id: int) -> Dict[str, Any]:
    """
    ИСПРАВЛЕННОЕ получение направлений для конкретной страны по ID
    
    Исправления:
    1. Добавлена валидация входных данных
    2. Улучшена обработка ошибок
    3. Добавлена статистика результатов
    """
    try:
        # Валидация country_id
        if country_id <= 0:
            raise HTTPException(status_code=400, detail="country_id должен быть положительным числом")
        
        logger.info(f"🎯 API запрос направлений для country_id: {country_id}")
        
        # Находим название страны по ID
        country_name = None
        for name, info in directions_service.COUNTRIES_MAPPING.items():
            if info["country_id"] == country_id:
                country_name = name
                break
        
        if not country_name:
            # Возвращаем список доступных стран для удобства
            available_countries = [
                {"name": name, "id": info["country_id"]} 
                for name, info in directions_service.COUNTRIES_MAPPING.items() 
                if info["country_id"] is not None
            ]
            raise HTTPException(
                status_code=404, 
                detail={
                    "message": f"Страна с ID {country_id} не найдена",
                    "available_countries": available_countries
                }
            )
        
        directions = await directions_service.get_directions_by_country(country_name)
        
        # Статистика результатов
        with_prices = len([d for d in directions if d.get("min_price")])
        with_images = len([d for d in directions if d.get("image_link")])
        
        return {
            "country_name": country_name,
            "country_id": country_id,
            "total_directions": len(directions),
            "statistics": {
                "with_prices": with_prices,
                "with_images": with_images,
                "completion_rate": f"{(with_prices/len(directions)*100):.1f}%" if directions else "0%"
            },
            "directions": directions
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка API направлений для country_id {country_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")

@router.get("/country/{country_id}/flat")
async def get_directions_flat_by_id(
    country_id: int,
    force_refresh: Optional[bool] = Query(False, description="Принудительное обновление кэша")
) -> List[Dict[str, Any]]:
    """
    ИСПРАВЛЕННОЕ получение направлений в плоском формате по ID страны
    
    Исправления:
    1. Добавлен параметр force_refresh
    2. Валидация NULL значений
    3. Улучшенная обработка ошибок
    4. Фильтрация невалидных результатов
    """
    try:
        # Валидация входных данных
        if country_id <= 0:
            raise HTTPException(status_code=400, detail="country_id должен быть положительным числом")
        
        logger.info(f"📋 API плоский список с ценами для country_id: {country_id} (force_refresh: {force_refresh})")
        
        # Принудительное обновление кэша если запрошено
        if force_refresh:
            cache_key = f"directions_with_prices_country_{country_id}"
            await cache_service.delete(cache_key)
            logger.info(f"🔄 Принудительно очищен кэш для страны {country_id}")
        
        # Находим название страны по ID
        country_name = None
        for name, info in directions_service.COUNTRIES_MAPPING.items():
            if info["country_id"] == country_id:
                country_name = name
                break
        
        if not country_name:
            raise HTTPException(status_code=404, detail=f"Страна с ID {country_id} не найдена")
        
        directions = await directions_service.get_directions_by_country(country_name)
        
        # ИСПРАВЛЕНИЕ: Валидация и фильтрация результатов
        valid_directions = []
        invalid_count = 0
        
        for direction in directions:
            # Проверяем обязательные поля
            if not direction.get("city_name"):
                invalid_count += 1
                continue
            
            # Исправляем NULL значения если они остались
            fixed_direction = {
                "country_name": direction.get("country_name", country_name),
                "country_id": direction.get("country_id", country_id),
                "city_name": direction.get("city_name", ""),
                "min_price": direction.get("min_price"),  # Может быть None
                "image_link": direction.get("image_link")  # Может быть None
            }
            
            valid_directions.append(fixed_direction)
        
        if invalid_count > 0:
            logger.warning(f"⚠️ Отфильтровано {invalid_count} невалидных направлений")
        
        logger.info(f"✅ Возвращаем {len(valid_directions)} валидных направлений с минимальными ценами")
        return valid_directions
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка API плоского списка для country_id {country_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")

@router.get("/country/{country_id}/quick")
async def get_directions_quick(country_id: int) -> List[Dict[str, Any]]:
    """
    ИСПРАВЛЕННОЕ быстрое получение направлений без поиска цен
    
    Исправления:
    1. Добавлена валидация
    2. Лучшая обработка синтетических городов
    3. Более подробная информация
    """
    try:
        # Валидация
        if country_id <= 0:
            raise HTTPException(status_code=400, detail="country_id должен быть положительным числом")
        
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
        synthetic_count = 0
        
        for city in cities:
            city_name = city.get("name", "")
            is_synthetic = city.get("synthetic", False)
            
            if city_name:
                direction_item = {
                    "country_name": country_name,
                    "country_id": country_id,
                    "city_name": city_name,
                    "min_price": None,  # Без поиска цен
                    "image_link": None,  # Без поиска картинок
                    "is_synthetic": is_synthetic,  # Дополнительная информация
                    "region_id": city.get("id")  # ID региона для отладки
                }
                result.append(direction_item)
                
                if is_synthetic:
                    synthetic_count += 1
        
        logger.info(f"⚡ Быстро получено {len(result)} направлений (синтетических: {synthetic_count})")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка быстрого запроса для country_id {country_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")

@router.get("/")
async def get_directions_with_filter(
    country_id: Optional[int] = Query(None, description="ID страны для фильтрации"),
    limit: Optional[int] = Query(None, ge=1, le=100, description="Лимит результатов"),
    force_refresh: Optional[bool] = Query(False, description="Принудительное обновление")
) -> Dict[str, Any]:
    """
    ИСПРАВЛЕННОЕ получение направлений с фильтрацией
    
    Исправления:
    1. Добавлен force_refresh
    2. Лучшая валидация параметров
    3. Подробная статистика
    4. Обработка ошибок
    """
    try:
        logger.info(f"🔍 API фильтр направлений: country_id={country_id}, limit={limit}, force_refresh={force_refresh}")
        
        # Валидация параметров
        if country_id is not None and country_id <= 0:
            raise HTTPException(status_code=400, detail="country_id должен быть положительным числом")
        
        # Принудительное обновление если запрошено
        if force_refresh and country_id:
            cache_key = f"directions_with_prices_country_{country_id}"
            await cache_service.delete(cache_key)
            logger.info(f"🔄 Принудительно очищен кэш для страны {country_id}")
        
        # Получаем направления
        if country_id is not None:
            # Фильтрация по конкретной стране
            all_directions = await directions_service.filter_directions_by_country_id(country_id, limit)
            filter_info = {"country_id": country_id, "limit": limit}
        else:
            # Все направления
            all_directions = await directions_service.get_all_directions()
            if limit is not None:
                all_directions = all_directions[:limit]
            filter_info = {"country_id": None, "limit": limit}
        
        # Статистика
        countries_count = len(set(d["country_id"] for d in all_directions))
        with_prices = len([d for d in all_directions if d.get("min_price")])
        with_images = len([d for d in all_directions if d.get("image_link")])
        
        return {
            "filter_applied": filter_info,
            "total_results": len(all_directions),
            "statistics": {
                "countries_represented": countries_count,
                "directions_with_prices": with_prices,
                "directions_with_images": with_images,
                "data_completeness": f"{(with_prices/len(all_directions)*100):.1f}%" if all_directions else "0%"
            },
            "directions": all_directions
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка API фильтра направлений: {e}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")

@router.get("/debug/regions/{country_id}")
async def debug_regions_for_country(country_id: int):
    """
    ИСПРАВЛЕННЫЙ отладочный endpoint для проверки получения регионов
    """
    try:
        # Валидация
        if country_id <= 0:
            raise HTTPException(status_code=400, detail="country_id должен быть положительным числом")
        
        logger.info(f"🔍 Отладка регионов для страны {country_id}")
        
        # Прямой запрос к API
        from app.core.tourvisor_client import tourvisor_client
        
        regions_data = await tourvisor_client.get_references("region", regcountry=country_id)
        
        # Анализ ответа
        regions = regions_data.get("lists", {}).get("regions", {}).get("region", [])
        if not isinstance(regions, list):
            regions = [regions] if regions else []
        
        # Фильтрация валидных регионов
        valid_regions = []
        for region in regions:
            if region.get("country") == str(country_id) and region.get("name"):
                valid_regions.append({
                    "id": region.get("id"),
                    "name": region.get("name"),
                    "country": region.get("country")
                })
        
        return {
            "country_id": country_id,
            "raw_regions_count": len(regions),
            "valid_regions_count": len(valid_regions),
            "valid_regions": valid_regions[:10],  # Первые 10 для примера
            "raw_response_sample": regions[:3] if regions else []  # Первые 3 для отладки
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка отладки для страны {country_id}: {e}")
        return {
            "error": str(e),
            "country_id": country_id,
            "status": "error"
        }

@router.get("/test/{country_id}")
async def test_country_directions_by_id(country_id: int):
    """
    ИСПРАВЛЕННЫЙ тестовый endpoint для проверки работы с конкретной страной
    """
    try:
        # Валидация
        if country_id <= 0:
            return {"error": "country_id должен быть положительным числом"}
        
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
        start_time = __import__('time').time()
        directions = await directions_service.get_directions_by_country(country_name)
        end_time = __import__('time').time()
        
        # Анализ результатов
        with_prices = len([d for d in directions if d.get("min_price")])
        with_images = len([d for d in directions if d.get("image_link")])
        
        return {
            "success": True,
            "country_name": country_name,
            "country_id": country_id,
            "directions_count": len(directions),
            "performance": {
                "execution_time_seconds": round(end_time - start_time, 2),
                "with_prices": with_prices,
                "with_images": with_images,
                "success_rate": f"{(with_prices/len(directions)*100):.1f}%" if directions else "0%"
            },
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

# ИСПРАВЛЕННЫЕ административные endpoints

@router.delete("/cache/clear")
async def clear_directions_cache():
    """
    ИСПРАВЛЕННАЯ очистка кэша направлений
    
    Исправления:
    1. Более надежное получение ключей
    2. Лучшая обработка ошибок
    3. Подробная статистика
    """
    try:
        logger.info("🗑️ Запрос на очистку кэша направлений")
        
        # Получаем все ключи кэша связанные с направлениями
        cache_patterns = [
            "directions_with_prices_country_*",  # Кэш с ценами по странам
            "directions_country_*",              # Обычный кэш направлений
            "top_cities_country_*",              # Кэш городов
            "regions_*",                         # Кэш регионов
            "destinations_search_based",         # Кэш через поиск
        ]
        
        total_deleted = 0
        deleted_by_pattern = {}
        errors = []
        
        for pattern in cache_patterns:
            try:
                # Получаем все ключи по паттерну
                deleted_count = await cache_service.delete_pattern(pattern)
                
                deleted_by_pattern[pattern] = deleted_count
                total_deleted += deleted_count
                
                if deleted_count > 0:
                    logger.info(f"🗑️ Удалено {deleted_count} ключей по паттерну: {pattern}")
                else:
                    logger.info(f"🔍 Нет ключей для паттерна: {pattern}")
                    
            except Exception as e:
                error_msg = f"Ошибка очистки паттерна {pattern}: {str(e)}"
                logger.error(f"❌ {error_msg}")
                deleted_by_pattern[pattern] = f"error: {str(e)}"
                errors.append(error_msg)
        
        logger.info(f"✅ Всего удалено {total_deleted} ключей кэша направлений")
        
        result = {
            "success": True,
            "message": f"Кэш направлений очищен успешно",
            "total_deleted": total_deleted,
            "details": deleted_by_pattern,
            "next_actions": [
                "Следующие запросы к /directions будут генерировать новые данные",
                "Кэш будет постепенно заполняться при новых запросах"
            ]
        }
        
        if errors:
            result["warnings"] = errors
            result["success"] = len(errors) < len(cache_patterns)  # Частичный успех
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Ошибка очистки кэша направлений: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Ошибка при очистке кэша: {str(e)}"
        )

@router.get("/cache/status")
async def get_cache_status():
    """
    ИСПРАВЛЕННОЕ получение статуса кэша направлений
    
    Исправления:
    1. Более безопасное получение TTL
    2. Лучшая обработка ошибок
    3. Расширенная статистика
    """
    try:
        logger.info("📊 Запрос статуса кэша направлений")
        
        cache_patterns = [
            "directions_with_prices_country_*",
            "directions_country_*", 
            "top_cities_country_*",
            "regions_*",
            "destinations_search_based"
        ]
        
        cache_status = {}
        total_keys = 0
        total_memory_usage = 0
        
        for pattern in cache_patterns:
            try:
                # Используем безопасный метод получения ключей
                keys = await cache_service.get_keys_pattern(pattern) if hasattr(cache_service, 'get_keys_pattern') else []
                
                if keys:
                    pattern_info = {
                        "count": len(keys),
                        "keys_sample": keys[:5],  # Показываем первые 5 ключей
                        "has_more": len(keys) > 5
                    }
                    
                    # Пробуем получить TTL для первого ключа
                    if keys:
                        try:
                            ttl = await cache_service.get_ttl(keys[0]) if hasattr(cache_service, 'get_ttl') else None
                            if ttl and ttl > 0:
                                pattern_info["example_ttl_seconds"] = ttl
                                pattern_info["example_ttl_human"] = f"{ttl//3600}ч {(ttl%3600)//60}м"
                        except Exception as ttl_error:
                            logger.debug(f"Не удалось получить TTL для {keys[0]}: {ttl_error}")
                    
                    # Примерный размер (если доступно)
                    try:
                        sample_size = await cache_service.get_size(keys[0]) if hasattr(cache_service, 'get_size') else 0
                        if sample_size > 0:
                            estimated_total = sample_size * len(keys)
                            pattern_info["estimated_size_bytes"] = estimated_total
                            pattern_info["estimated_size_human"] = format_bytes(estimated_total)
                            total_memory_usage += estimated_total
                    except:
                        pass
                        
                else:
                    pattern_info = {
                        "count": 0,
                        "keys_sample": [],
                        "has_more": False
                    }
                
                cache_status[pattern] = pattern_info
                total_keys += pattern_info["count"]
                
            except Exception as e:
                cache_status[pattern] = {
                    "error": str(e),
                    "count": 0
                }
        
        # Общая статистика
        active_patterns = len([p for p in cache_status.values() if p.get("count", 0) > 0])
        
        return {
            "total_cached_keys": total_keys,
            "active_patterns": active_patterns,
            "total_patterns": len(cache_patterns),
            "estimated_memory_usage": format_bytes(total_memory_usage) if total_memory_usage > 0 else "Unknown",
            "cache_patterns": cache_status,
            "recommendations": {
                "clear_cache": "DELETE /api/v1/directions/cache/clear",
                "force_refresh": "Добавьте параметр ?force_refresh=true к любому запросу направлений",
                "refresh_country": "POST /api/v1/directions/refresh/{country_id}"
            },
            "cache_health": "Good" if total_keys > 0 else "Empty"
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
    ИСПРАВЛЕННОЕ принудительное обновление направлений для конкретной страны
    
    Исправления:
    1. Валидация входных данных
    2. Измерение производительности
    3. Подробная статистика результатов
    """
    try:
        # Валидация
        if country_id <= 0:
            raise HTTPException(status_code=400, detail="country_id должен быть положительным числом")
        
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
                detail=f"Страна с ID {country_id} не найдена в списке поддерживаемых стран"
            )
        
        # Измеряем время выполнения
        import time
        start_time = time.time()
        
        # Очищаем все связанные кэши для этой страны
        cache_keys_to_clear = [
            f"directions_with_prices_country_{country_id}",
            f"directions_country_{country_id}",
            f"top_cities_country_{country_id}"
        ]
        
        cleared_count = 0
        for cache_key in cache_keys_to_clear:
            try:
                await cache_service.delete(cache_key)
                cleared_count += 1
            except Exception as e:
                logger.warning(f"⚠️ Не удалось очистить ключ {cache_key}: {e}")
        
        logger.info(f"🗑️ Очищено {cleared_count} ключей кэша для страны {country_name}")
        
        # Генерируем новые данные
        directions = await directions_service.get_directions_by_country(country_name)
        
        end_time = time.time()
        execution_time = round(end_time - start_time, 2)
        
        # Анализ результатов
        with_prices = len([d for d in directions if d.get("min_price")])
        with_images = len([d for d in directions if d.get("image_link")])
        avg_price = sum(d.get("min_price", 0) for d in directions if d.get("min_price")) / with_prices if with_prices > 0 else 0
        
        return {
            "success": True,
            "country_name": country_name,
            "country_id": country_id,
            "directions_count": len(directions),
            "performance": {
                "execution_time_seconds": execution_time,
                "cache_keys_cleared": cleared_count
            },
            "statistics": {
                "directions_with_prices": with_prices,
                "directions_with_images": with_images,
                "success_rate": f"{(with_prices/len(directions)*100):.1f}%" if directions else "0%",
                "average_price": round(avg_price) if avg_price > 0 else None
            },
            "message": f"Направления для {country_name} успешно обновлены",
            "sample_directions": directions[:3] if directions else []  # Показываем первые 3 для примера
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка обновления страны {country_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при обновлении: {str(e)}"
        )

@router.post("/refresh/all")
async def force_refresh_all_directions():
    """
    НОВЫЙ endpoint: Принудительное обновление всех направлений
    
    Внимание: Может занять много времени!
    """
    try:
        logger.info("🔄 Принудительное обновление ВСЕХ направлений")
        
        import time
        start_time = time.time()
        
        # Очищаем весь кэш направлений
        await clear_directions_cache()
        
        # Получаем все направления (это вызовет полную регенерацию)
        all_directions = await directions_service.get_all_directions()
        
        end_time = time.time()
        execution_time = round(end_time - start_time, 2)
        
        # Статистика по странам
        countries_stats = {}
        for direction in all_directions:
            country_name = direction.get("country_name", "Unknown")
            if country_name not in countries_stats:
                countries_stats[country_name] = {
                    "count": 0,
                    "with_prices": 0,
                    "with_images": 0
                }
            
            countries_stats[country_name]["count"] += 1
            if direction.get("min_price"):
                countries_stats[country_name]["with_prices"] += 1
            if direction.get("image_link"):
                countries_stats[country_name]["with_images"] += 1
        
        # Общая статистика
        total_with_prices = len([d for d in all_directions if d.get("min_price")])
        total_with_images = len([d for d in all_directions if d.get("image_link")])
        
        return {
            "success": True,
            "message": "Все направления успешно обновлены",
            "performance": {
                "execution_time_seconds": execution_time,
                "countries_processed": len(countries_stats)
            },
            "statistics": {
                "total_directions": len(all_directions),
                "total_with_prices": total_with_prices,
                "total_with_images": total_with_images,
                "overall_success_rate": f"{(total_with_prices/len(all_directions)*100):.1f}%" if all_directions else "0%"
            },
            "countries_breakdown": countries_stats,
            "warning": "Полное обновление может занять значительное время и ресурсы"
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка обновления всех направлений: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при обновлении всех направлений: {str(e)}"
        )

def format_bytes(bytes_count: int) -> str:
    """Утилита для форматирования размера в байтах"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_count < 1024.0:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024.0
    return f"{bytes_count:.1f} TB"

@router.get("/cache/preview/{country_id}")
async def preview_cached_directions(country_id: int, limit: int = 10) -> Dict[str, Any]:
    """
    Предварительный просмотр закешированных направлений
    МОМЕНТАЛЬНО возвращает данные из кеша без перегенерации
    """
    try:
        # Находим название страны
        country_name = None
        for name, info in directions_service.COUNTRIES_MAPPING.items():
            if info["country_id"] == country_id:
                country_name = name
                break
        
        if not country_name:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": f"Неподдерживаемая страна: {country_id}",
                    "available_countries": {
                        name: info["country_id"] 
                        for name, info in directions_service.COUNTRIES_MAPPING.items() 
                        if info["country_id"] is not None
                    }
                }
            )
        
        # Получаем из кеша - МОМЕНТАЛЬНАЯ ОТДАЧА
        cache_key = f"directions_with_prices_country_{country_id}"
        cached_directions = await cache_service.get(cache_key)
        
        if not cached_directions:
            return {
                "success": False,
                "message": f"Нет закешированных направлений для страны '{country_name}'",
                "country": {
                    "id": country_id,
                    "name": country_name
                },
                "recommendation": f"Используйте GET /country/{country_id} для генерации данных"
            }
        
        # Анализируем качество
        with_prices = len([d for d in cached_directions if d.get("min_price")])
        with_images = len([d for d in cached_directions if d.get("image_link")])
        preview_directions = cached_directions[:limit]
        
        return {
            "success": True,
            "country": {"id": country_id, "name": country_name},
            "total_cached": len(cached_directions),
            "showing": len(preview_directions),
            "quality_stats": {
                "with_prices": with_prices,
                "with_images": with_images,
                "price_coverage": f"{(with_prices/len(cached_directions)*100):.1f}%" if cached_directions else "0%"
            },
            "preview_directions": preview_directions
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка предварительного просмотра для country_id {country_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка при получении превью: {str(e)}")