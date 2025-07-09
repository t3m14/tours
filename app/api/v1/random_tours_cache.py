# app/api/v1/random_tours_cache.py - ОБНОВЛЕННАЯ ВЕРСИЯ С HOTELTYPES

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, Any, List
from datetime import datetime

from app.tasks.random_tours_cache_update import random_tours_cache_update_service
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/random-tours/cache", tags=["Random Tours Cache Management"])

@router.get("/hotel-types")
async def get_supported_hotel_types() -> Dict[str, Any]:
    """
    Получение списка поддерживаемых типов отелей
    
    Возвращает все доступные типы отелей с их маппингом на API TourVisor.
    """
    try:
        logger.info("🏨 Запрос списка поддерживаемых типов отелей")
        
        hotel_types_info = random_tours_cache_update_service.get_supported_hotel_types()
        
        return {
            "success": True,
            "message": "Список поддерживаемых типов отелей",
            **hotel_types_info
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения типов отелей: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при получении типов отелей: {str(e)}"
        )

@router.get("/status")
async def get_random_tours_cache_status() -> Dict[str, Any]:
    """
    Получение статуса автоматического обновления кэша случайных туров
    
    Возвращает информацию о:
    - Текущем статусе планировщика
    - Времени последнего обновления
    - Поддерживаемых типах отелей
    - API интеграции с TourVisor
    """
    try:
        logger.info("📊 Запрос статуса обновления кэша случайных туров")
        
        status = await random_tours_cache_update_service.get_update_status()
        
        # Добавляем дополнительную информацию
        current_time = datetime.now()
        status["current_time"] = current_time
        status["scheduler_info"] = {
            "update_interval_hours": random_tours_cache_update_service.update_interval / 3600,
            "tours_per_type": random_tours_cache_update_service.tours_per_type,
            "strategies": random_tours_cache_update_service.generation_strategies,
            "countries": random_tours_cache_update_service.countries_to_update,
            "hotel_types_count": len(random_tours_cache_update_service.hotel_types_mapping)
        }
        
        return status
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения статуса кэша случайных туров: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при получении статуса: {str(e)}"
        )

@router.post("/force-update")
async def force_random_tours_cache_update(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Принудительное обновление кэша случайных туров
    
    Запускает полное обновление всех типов отелей в фоновом режиме.
    Использует API фильтрацию по hoteltypes для качественных результатов.
    """
    try:
        logger.info("🚀 API запрос принудительного обновления кэша случайных туров")
        
        # Проверяем, не запущено ли уже обновление
        status = await random_tours_cache_update_service.get_update_status()
        
        if status.get("is_running") and status.get("current_hotel_type"):
            return {
                "success": False,
                "message": "Обновление уже выполняется",
                "current_hotel_type": status.get("current_hotel_type"),
                "supported_hotel_types": status.get("hotel_types_supported", []),
                "current_status": status
            }
        
        # Запускаем принудительное обновление в фоне
        background_tasks.add_task(random_tours_cache_update_service.force_update_now)
        
        return {
            "success": True,
            "message": "Принудительное обновление кэша случайных туров запущено в фоновом режиме",
            "hotel_types_to_update": list(random_tours_cache_update_service.hotel_types_mapping.keys()),
            "api_integration": "Используется фильтрация hoteltypes API TourVisor",
            "estimated_duration": "10-20 минут",
            "note": "Используйте GET /status для отслеживания прогресса",
            "started_at": datetime.now()
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска принудительного обновления случайных туров: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при запуске обновления: {str(e)}"
        )

@router.get("/stats")
async def get_random_tours_cache_stats() -> Dict[str, Any]:
    """
    Подробная статистика кэша случайных туров
    
    Возвращает детальную информацию о последнем обновлении,
    включая статистику по каждому типу отеля и API вызовам.
    """
    try:
        logger.info("📈 Запрос детальной статистики кэша случайных туров")
        
        status = await random_tours_cache_update_service.get_update_status()
        update_stats = status.get("update_stats")
        
        if not update_stats:
            return {
                "message": "Статистика недоступна - обновлений еще не было",
                "recommendation": "Запустите принудительное обновление: POST /force-update",
                "supported_hotel_types": list(random_tours_cache_update_service.hotel_types_mapping.keys())
            }
        
        # Анализируем статистику по типам отелей
        hotel_types_details = update_stats.get("hotel_types_details", {})
        
        # Топ типы отелей по количеству туров
        top_hotel_types = sorted(
            [(hotel_type, data) for hotel_type, data in hotel_types_details.items() if data.get("success")],
            key=lambda x: x[1].get("tours_count", 0),
            reverse=True
        )
        
        # Типы отелей с проблемами
        failed_hotel_types = [
            hotel_type for hotel_type, data in hotel_types_details.items() 
            if not data.get("success")
        ]
        
        # Статистика по стратегиям
        strategies_used = update_stats.get("strategies_used", {})
        
        # API статистика
        api_calls_total = update_stats.get("api_calls_made", 0)
        real_api_tours = update_stats.get("real_api_tours", 0)
        mock_tours = update_stats.get("mock_tours", 0)
        
        return {
            "last_update": update_stats.get("end_time"),
            "execution_summary": {
                "total_hotel_types": update_stats.get("total_hotel_types", 0),
                "successful_hotel_types": update_stats.get("successful_types", 0),
                "failed_hotel_types": update_stats.get("failed_types", 0),
                "success_rate": f"{update_stats.get('success_rate', 0):.1f}%",
                "total_tours_generated": update_stats.get("total_tours_generated", 0),
                "execution_time": f"{update_stats.get('execution_time_seconds', 0):.1f} сек"
            },
            "api_integration_stats": {
                "total_api_calls": api_calls_total,
                "real_api_tours": real_api_tours,
                "mock_tours": mock_tours,
                "api_success_rate": f"{(real_api_tours/(real_api_tours+mock_tours)*100):.1f}%" if (real_api_tours+mock_tours) > 0 else "0%",
                "hoteltypes_filter_used": True
            },
            "quality_summary": {
                "real_tours_percentage": f"{update_stats.get('real_tours_percentage', 0):.1f}%",
                "total_real_tours": real_api_tours,
                "total_mock_tours": mock_tours
            },
            "strategies_breakdown": {
                "strategies_used": strategies_used,
                "most_successful_strategy": max(strategies_used.items(), key=lambda x: x[1])[0] if strategies_used else None
            },
            "top_hotel_types": [
                {
                    "hotel_type": hotel_type,
                    "tours_count": data.get("tours_count", 0),
                    "execution_time": f"{data.get('execution_time_seconds', 0):.1f}s",
                    "quality": data.get("quality_stats", {}).get("real_tours_percentage", "0%"),
                    "api_param": data.get("hotel_type_api_param"),
                    "api_calls": data.get("api_calls_made", 0)
                }
                for hotel_type, data in top_hotel_types
            ],
            "failed_hotel_types": failed_hotel_types,
            "hotel_types_details": hotel_types_details
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения детальной статистики случайных туров: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при получении статистики: {str(e)}"
        )

@router.get("/health")
async def get_random_tours_cache_health() -> Dict[str, Any]:
    """
    Проверка здоровья кэша случайных туров
    
    Проверяет актуальность кэша и покрытие всех типов отелей,
    включая информацию об API интеграции.
    """
    try:
        logger.info("🏥 Проверка здоровья кэша случайных туров")
        
        health_info = await random_tours_cache_update_service.get_cache_health()
        
        return health_info
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки здоровья кэша случайных туров: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при проверке здоровья: {str(e)}"
        )

@router.delete("/clear")
async def clear_random_tours_cache() -> Dict[str, Any]:
    """
    Очистка всего кэша случайных туров
    
    Удаляет все закэшированные случайные туры для всех типов отелей.
    """
    try:
        logger.info("🗑️ Запрос на очистку кэша случайных туров")
        
        result = await random_tours_cache_update_service.clear_all_cache()
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Ошибка очистки кэша случайных туров: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при очистке кэша: {str(e)}"
        )

@router.post("/scheduler/start")
async def start_random_tours_scheduler(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Запуск планировщика автоматического обновления кэша случайных туров
    
    Планировщик будет обновлять кэш каждые 12 часов автоматически,
    используя API фильтрацию по типам отелей.
    """
    try:
        logger.info("▶️ API запрос запуска планировщика случайных туров")
        
        if random_tours_cache_update_service.is_running:
            return {
                "success": False,
                "message": "Планировщик случайных туров уже запущен",
                "status": "running",
                "supported_hotel_types": list(random_tours_cache_update_service.hotel_types_mapping.keys())
            }
        
        # Запускаем планировщик в фоне
        background_tasks.add_task(random_tours_cache_update_service.start_scheduler)
        
        return {
            "success": True,
            "message": "Планировщик автоматического обновления кэша случайных туров запущен",
            "schedule": "каждые 12 часов",
            "hotel_types_supported": list(random_tours_cache_update_service.hotel_types_mapping.keys()),
            "api_integration": "Используется TourVisor hoteltypes фильтрация",
            "started_at": datetime.now()
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска планировщика случайных туров: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при запуске планировщика: {str(e)}"
        )

@router.post("/scheduler/stop")
async def stop_random_tours_scheduler() -> Dict[str, Any]:
    """
    Остановка планировщика автоматического обновления кэша случайных туров
    """
    try:
        logger.info("⏹️ API запрос остановки планировщика случайных туров")
        
        if not random_tours_cache_update_service.is_running:
            return {
                "success": False,
                "message": "Планировщик случайных туров уже остановлен",
                "status": "stopped"
            }
        
        await random_tours_cache_update_service.stop_scheduler()
        
        return {
            "success": True,
            "message": "Планировщик автоматического обновления кэша случайных туров остановлен",
            "stopped_at": datetime.now()
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка остановки планировщика случайных туров: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при остановке планировщика: {str(e)}"
        )

@router.post("/generate/{hotel_type}")
async def generate_tours_for_hotel_type(
    hotel_type: str,
    background_tasks: BackgroundTasks,
    count: int = 8
) -> Dict[str, Any]:
    """
    Принудительная генерация туров для конкретного типа отеля
    
    Args:
        hotel_type: Тип отеля из поддерживаемых
        count: Количество туров для генерации (по умолчанию 8)
    
    Поддерживаемые типы отелей:
    - любой: любые отели (без фильтрации)
    - активный: active отели (hoteltypes=active)
    - релакс: relax отели (hoteltypes=relax)
    - семейный: family отели (hoteltypes=family)
    - оздоровительный: health отели (hoteltypes=health)
    - городской: city отели (hoteltypes=city)
    - пляжный: beach отели (hoteltypes=beach)
    - делюкс: deluxe отели (hoteltypes=deluxe)
    """
    try:
        # Проверяем поддерживаемые типы отелей
        supported_types = random_tours_cache_update_service.hotel_types_mapping
        
        if hotel_type not in supported_types:
            available_types = list(supported_types.keys())
            raise HTTPException(
                status_code=400,
                detail={
                    "error": f"Неподдерживаемый тип отеля: {hotel_type}",
                    "available_types": available_types,
                    "api_mapping": {
                        key: {
                            "display_name": info["display_name"],
                            "api_param": info["api_param"]
                        }
                        for key, info in supported_types.items()
                    }
                }
            )
        
        hotel_type_info = supported_types[hotel_type]
        display_name = hotel_type_info["display_name"]
        api_param = hotel_type_info["api_param"]
        
        logger.info(f"🎲 API запрос генерации {count} туров для типа: {display_name} (API: {api_param})")
        
        # Запускаем генерацию в фоне
        async def generate_specific_tours():
            try:
                result = await random_tours_cache_update_service._update_tours_for_hotel_type(hotel_type, hotel_type_info)
                logger.info(f"✅ Генерация для {display_name} завершена: {result}")
            except Exception as e:
                logger.error(f"❌ Ошибка генерации для {display_name}: {e}")
        
        background_tasks.add_task(generate_specific_tours)
        
        return {
            "success": True,
            "message": f"Генерация туров для типа '{display_name}' запущена в фоновом режиме",
            "hotel_type": {
                "key": hotel_type,
                "display_name": display_name,
                "api_param": api_param,
                "api_integration": f"Используется фильтр hoteltypes={api_param}" if api_param else "Без фильтрации API"
            },
            "count": count,
            "estimated_duration": "3-8 минут",
            "api_calls_expected": "2-5 вызовов TourVisor API",
            "started_at": datetime.now()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка запуска генерации туров для {hotel_type}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при запуске генерации: {str(e)}"
        )

@router.get("/preview/{hotel_type}")
async def preview_cached_tours(hotel_type: str, limit: int = 3) -> Dict[str, Any]:
    """
    Предварительный просмотр закэшированных туров для типа отеля
    
    Args:
        hotel_type: Тип отеля из поддерживаемых
        limit: Количество туров для показа (по умолчанию 3)
    """
    try:
        # Проверяем поддерживаемые типы отелей
        supported_types = random_tours_cache_update_service.hotel_types_mapping
        
        if hotel_type not in supported_types:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": f"Неподдерживаемый тип отеля: {hotel_type}",
                    "available_types": list(supported_types.keys())
                }
            )
        
        hotel_type_info = supported_types[hotel_type]
        display_name = hotel_type_info["display_name"]
        cache_key_suffix = hotel_type_info["cache_key"]
        api_param = hotel_type_info["api_param"]
        
        # Получаем из кэша
        from app.services.cache_service import cache_service
        cache_key = f"random_tours_{cache_key_suffix.replace(' ', '_')}"
        cached_tours = await cache_service.get(cache_key)
        
        if not cached_tours:
            return {
                "success": False,
                "message": f"Нет закэшированных туров для типа '{display_name}'",
                "hotel_type": {
                    "key": hotel_type,
                    "display_name": display_name,
                    "api_param": api_param
                },
                "recommendation": f"Запустите генерацию: POST /generate/{hotel_type}",
                "cache_key": cache_key
            }
        
        # Анализируем качество
        real_tours = len([t for t in cached_tours if t.get("generation_strategy") in ["search", "hot_tours"]])
        mock_tours = len(cached_tours) - real_tours
        
        # Статистика по источникам
        source_stats = {}
        for tour in cached_tours:
            source = tour.get("search_source", "unknown")
            source_stats[source] = source_stats.get(source, 0) + 1
        
        # Показываем первые limit туров
        preview_tours = cached_tours[:limit]
        
        # Обогащаем информацию о турах
        enriched_tours = []
        for tour in preview_tours:
            enriched_tour = {
                **tour,
                "api_filter_used": api_param,
                "hotel_type_display": display_name
            }
            enriched_tours.append(enriched_tour)
        
        return {
            "success": True,
            "hotel_type": {
                "key": hotel_type,
                "display_name": display_name,
                "api_param": api_param,
                "api_integration": f"Фильтр hoteltypes={api_param}" if api_param else "Без API фильтрации"
            },
            "total_cached": len(cached_tours),
            "showing": len(preview_tours),
            "quality_stats": {
                "real_tours": real_tours,
                "mock_tours": mock_tours,
                "real_percentage": f"{(real_tours/len(cached_tours)*100):.1f}%"
            },
            "source_breakdown": source_stats,
            "preview_tours": enriched_tours,
            "cache_info": {
                "cache_key": cache_key,
                "last_updated": cached_tours[0].get("cached_at") if cached_tours else None
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка предварительного просмотра для {hotel_type}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при получении превью: {str(e)}"
        )

@router.get("/compare-strategies/{hotel_type}")
async def compare_generation_strategies(hotel_type: str) -> Dict[str, Any]:
    """
    Сравнение стратегий генерации туров для конкретного типа отеля
    
    Показывает эффективность разных стратегий (search, hot_tours, mock)
    для данного типа отеля.
    """
    try:
        # Проверяем поддерживаемые типы отелей
        supported_types = random_tours_cache_update_service.hotel_types_mapping
        
        if hotel_type not in supported_types:
            raise HTTPException(
                status_code=400,
                detail=f"Неподдерживаемый тип отеля: {hotel_type}"
            )
        
        hotel_type_info = supported_types[hotel_type]
        display_name = hotel_type_info["display_name"]
        cache_key_suffix = hotel_type_info["cache_key"]
        api_param = hotel_type_info["api_param"]
        
        # Получаем закэшированные туры
        from app.services.cache_service import cache_service
        cache_key = f"random_tours_{cache_key_suffix.replace(' ', '_')}"
        cached_tours = await cache_service.get(cache_key)
        
        if not cached_tours:
            return {
                "success": False,
                "message": f"Нет данных для анализа типа '{display_name}'",
                "recommendation": f"Запустите генерацию: POST /generate/{hotel_type}"
            }
        
        # Анализируем стратегии
        strategy_analysis = {}
        
        for tour in cached_tours:
            strategy = tour.get("generation_strategy", "unknown")
            source = tour.get("search_source", "unknown")
            
            if strategy not in strategy_analysis:
                strategy_analysis[strategy] = {
                    "count": 0,
                    "avg_price": 0,
                    "sources": {},
                    "sample_tour": None
                }
            
            strategy_analysis[strategy]["count"] += 1
            strategy_analysis[strategy]["avg_price"] += tour.get("price", 0)
            
            # Источники для стратегии
            if source not in strategy_analysis[strategy]["sources"]:
                strategy_analysis[strategy]["sources"][source] = 0
            strategy_analysis[strategy]["sources"][source] += 1
            
            # Пример тура
            if not strategy_analysis[strategy]["sample_tour"]:
                strategy_analysis[strategy]["sample_tour"] = {
                    "hotel_name": tour.get("hotel_name"),
                    "price": tour.get("price"),
                    "region_name": tour.get("region_name")
                }
        
        # Вычисляем средние цены
        for strategy in strategy_analysis:
            if strategy_analysis[strategy]["count"] > 0:
                strategy_analysis[strategy]["avg_price"] = int(
                    strategy_analysis[strategy]["avg_price"] / strategy_analysis[strategy]["count"]
                )
        
        # Рекомендации по улучшению
        recommendations = []
        
        search_count = strategy_analysis.get("search", {}).get("count", 0)
        hot_tours_count = strategy_analysis.get("hot_tours", {}).get("count", 0)
        mock_count = strategy_analysis.get("mock", {}).get("count", 0)
        
        total = search_count + hot_tours_count + mock_count
        
        if total > 0:
            real_percentage = ((search_count + hot_tours_count) / total) * 100
            
            if real_percentage < 50:
                recommendations.append("Низкий процент реальных туров - рассмотрите увеличение таймаутов поиска")
            
            if search_count == 0 and api_param:
                recommendations.append(f"API фильтр hoteltypes={api_param} не дал результатов - возможно, мало отелей этого типа")
            
            if hot_tours_count == 0:
                recommendations.append("Горящие туры не найдены - возможно, нет предложений для данной страны")
        
        return {
            "success": True,
            "hotel_type": {
                "key": hotel_type,
                "display_name": display_name,
                "api_param": api_param
            },
            "total_tours_analyzed": len(cached_tours),
            "strategy_breakdown": strategy_analysis,
            "effectiveness_summary": {
                "real_tours_percentage": f"{((search_count + hot_tours_count) / total * 100):.1f}%" if total > 0 else "0%",
                "most_effective_strategy": max(strategy_analysis.items(), key=lambda x: x[1]["count"])[0] if strategy_analysis else None,
                "api_filter_effectiveness": f"hoteltypes={api_param} дал {search_count} результатов" if api_param else "API фильтр не используется"
            },
            "recommendations": recommendations
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка анализа стратегий для {hotel_type}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при анализе стратегий: {str(e)}"
        )# app/api/v1/random_tours_cache.py - ОПТИМИЗИРОВАННАЯ ВЕРСИЯ PREVIEW ENDPOINT

@router.get("/preview/{hotel_type}")
async def preview_cached_tours(hotel_type: str, limit: int = 3) -> Dict[str, Any]:
    """
    Предварительный просмотр закэшированных туров для типа отеля
    
    ОБНОВЛЕНО: Теперь включает поля hoteldescriptions и tours как в обычном поиске
    
    Args:
        hotel_type: Тип отеля (any, active, relax, family, health, city, beach, deluxe)
        limit: Количество туров для предварительного просмотра (по умолчанию 3)
        
    Returns:
        Dict с информацией о типе отеля и preview туров с полными данными
    """
    try:
        # Получаем поддерживаемые типы отелей
        supported_types = random_tours_cache_update_service.get_supported_hotel_types()["hotel_types"]
        
        if hotel_type not in supported_types:
            raise HTTPException(
                status_code=400,
                detail=f"Неподдерживаемый тип отеля: {hotel_type}. Доступные типы: {list(supported_types.keys())}"
            )
        
        hotel_type_info = supported_types[hotel_type]
        display_name = hotel_type_info["display_name"]
        cache_key_suffix = hotel_type_info["cache_key"]
        
        logger.info(f"🎭 Preview запрос для типа отеля: {display_name} (лимит: {limit})")
        
        # Получаем туры из кэша
        cache_key = f"random_tours_{cache_key_suffix}"
        cached_tours = await cache_service.get(cache_key)
        
        if not cached_tours:
            return {
                "success": False,
                "message": f"Нет закэшированных туров для типа '{display_name}'",
                "hotel_type": {
                    "key": hotel_type,
                    "display_name": display_name,
                    "api_param": hotel_type_info["api_param"]
                },
                "preview_tours": [],
                "total_cached": 0,
                "recommendation": "Запустите генерацию туров: POST /api/v1/random-tours/cache/generate/{hotel_type}",
                "cache_key": cache_key,
                "enhanced_features": {
                    "includes_descriptions": False,
                    "includes_tours_data": False
                }
            }
        
        # Ограничиваем количество туров для preview
        preview_tours = cached_tours[:limit]
        
        # Обогащаем туры данными если они еще не обогащены
        enriched_tours = []
        for tour in preview_tours:
            enriched_tour = await _enrich_preview_tour(tour)
            enriched_tours.append(enriched_tour)
        
        # Анализируем качество кэша
        total_tours = len(cached_tours)
        real_tours_count = len([t for t in cached_tours if t.get("generation_strategy") in ["search", "hot_tours"]])
        mock_tours_count = total_tours - real_tours_count
        
        # Проверяем наличие расширенных данных
        has_descriptions = any(t.get("hoteldescriptions") for t in cached_tours)
        has_tours_data = any(t.get("tours") for t in cached_tours)
        
        return {
            "success": True,
            "message": f"Найдено {total_tours} туров для типа '{display_name}'",
            "hotel_type": {
                "key": hotel_type,
                "display_name": display_name,
                "api_param": hotel_type_info["api_param"],
                "cache_key": cache_key_suffix
            },
            "preview_tours": enriched_tours,
            "total_cached": total_tours,
            "cache_stats": {
                "real_tours": real_tours_count,
                "mock_tours": mock_tours_count,
                "quality_percentage": f"{(real_tours_count/total_tours*100):.1f}%" if total_tours > 0 else "0%"
            },
            "enhanced_features": {
                "includes_descriptions": has_descriptions,
                "includes_tours_data": has_tours_data,
                "tourvisor_api_integration": hotel_type_info["api_param"] is not None
            },
            "api_integration": {
                "uses_hoteltypes_filter": hotel_type_info["api_param"] is not None,
                "api_parameter": hotel_type_info["api_param"]
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка preview туров для {hotel_type}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при получении preview: {str(e)}"
        )


async def _enrich_preview_tour(tour: Dict[str, Any]) -> Dict[str, Any]:
    """
    Обогащение тура для preview с добавлением hoteldescriptions и tours
    
    Создает структуру данных аналогичную обычному поиску туров
    """
    try:
        from app.core.tourvisor_client import tourvisor_client
        
        # Создаем копию тура для обогащения
        enriched_tour = tour.copy()
        
        # БЛОК 1: ОСНОВНАЯ ИНФОРМАЦИЯ ОБ ОТЕЛЕ
        hotel_info = {
            "hotelcode": tour.get("hotelcode", ""),
            "hotelname": tour.get("hotel_name", ""),
            "hotelstars": tour.get("hotel_stars", 0),
            "hotelrating": tour.get("hotel_rating", 0.0),
            "countryname": tour.get("country_name", ""),
            "regionname": tour.get("region_name", ""),
            "seadistance": tour.get("seadistance", 0),
            "picturelink": tour.get("picture_link", ""),
            "fulldesclink": tour.get("fulldesclink", ""),
            "reviewlink": tour.get("reviewlink", "")
        }
        
        # БЛОК 2: ПОЛУЧЕНИЕ HOTELDESCRIPTIONS
        hotel_description = ""
        
        # Если уже есть описание в кэше
        if tour.get("hoteldescriptions"):
            hotel_description = tour["hoteldescriptions"]
        else:
            # Пытаемся получить описание через API
            hotel_code = tour.get("hotelcode")
            if hotel_code and not hotel_code.startswith("MOCK_"):
                try:
                    hotel_details = await tourvisor_client.get_hotel_info(hotel_code)
                    if hotel_details and isinstance(hotel_details, dict):
                        hotel_description = (
                            hotel_details.get("hoteldescription", "") or
                            hotel_details.get("description", "") or
                            f"Отель {tour.get('hotel_name', 'Unknown Hotel')}"
                        )
                except Exception as api_error:
                    logger.debug(f"Не удалось получить описание отеля {hotel_code}: {api_error}")
            
            # Fallback описание
            if not hotel_description:
                stars_text = "⭐" * tour.get("hotel_stars", 0)
                hotel_description = f"Отель {tour.get('hotel_name', 'Unknown Hotel')} {stars_text} расположен в {tour.get('region_name', 'курортной зоне')}."
        
        enriched_tour["hoteldescriptions"] = hotel_description
        
        # БЛОК 3: ФОРМИРОВАНИЕ СТРУКТУРЫ TOURS
        tours_data = []
        
        # Если уже есть tours в кэше
        if tour.get("tours"):
            tours_data = tour["tours"]
        else:
            # Создаем tours структуру из основных данных тура
            tour_data = {
                "operatorcode": tour.get("operator_code", ""),
                "operatorname": tour.get("operator_name", ""),
                "flydate": tour.get("fly_date", ""),
                "nights": tour.get("nights", 7),
                "price": tour.get("price", 0),
                "currency": tour.get("currency", "RUB"),
                "placement": tour.get("placement", "DBL"),
                "adults": tour.get("adults", 2),
                "children": tour.get("children", 0),
                "meal": tour.get("meal", ""),
                "mealrussian": tour.get("meal", ""),
                "tourname": tour.get("tour_name", ""),
                "tourid": tour.get("tour_id", f"preview_tour_{random.randint(1000, 9999)}")
            }
            tours_data = [tour_data]
        
        enriched_tour["tours"] = tours_data
        
        # БЛОК 4: ДОПОЛНИТЕЛЬНЫЕ ПОЛЯ ДЛЯ СОВМЕСТИМОСТИ
        enriched_tour.update({
            # Совместимость с форматом поиска
            "price": tour.get("price", 0),  # Минимальная цена по отелю
            "countrycode": tour.get("countrycode", ""),
            "regioncode": tour.get("regioncode", ""),
            "subregioncode": tour.get("subregioncode", ""),
            
            # Флаги наличия дополнительной информации
            "isphoto": 1 if tour.get("picture_link") else 0,
            "iscoords": 0,  # Координаты пока не поддерживаются
            "isdescription": 1 if hotel_description else 0,
            "isreviews": 1 if tour.get("reviewlink") else 0,
            
            # Метаданные для отладки
            "preview_enhanced": True,
            "data_source": tour.get("generation_strategy", "unknown"),
            "enhanced_at": datetime.now().isoformat()
        })
        
        return enriched_tour
        
    except Exception as e:
        logger.warning(f"⚠️ Ошибка обогащения preview тура: {e}")
        
        # Возвращаем минимально обогащенный тур
        fallback_tour = tour.copy()
        fallback_tour.update({
            "hoteldescriptions": f"Отель {tour.get('hotel_name', 'Unknown Hotel')}",
            "tours": [{
                "price": tour.get("price", 0),
                "nights": tour.get("nights", 7),
                "meal": tour.get("meal", ""),
                "placement": tour.get("placement", "DBL"),
                "tourid": f"fallback_tour_{random.randint(1000, 9999)}"
            }],
            "preview_enhanced": False,
            "fallback_used": True
        })
        
        return fallback_tour


# ДОПОЛНИТЕЛЬНЫЙ ENDPOINT ДЛЯ ПОЛУЧЕНИЯ ПОЛНОЙ СТРУКТУРЫ ТУРА
@router.get("/preview/{hotel_type}/detailed")
async def get_detailed_preview_tour(
    hotel_type: str, 
    tour_index: int = 0,
    include_api_data: bool = True
) -> Dict[str, Any]:
    """
    Получение детальной информации о конкретном туре из preview
    
    Args:
        hotel_type: Тип отеля
        tour_index: Индекс тура в кэше (по умолчанию 0 - первый тур)
        include_api_data: Включать данные из TourVisor API
        
    Returns:
        Полная информация о туре в формате аналогичном результатам поиска
    """
    try:
        # Получаем поддерживаемые типы отелей
        supported_types = random_tours_cache_update_service.get_supported_hotel_types()["hotel_types"]
        
        if hotel_type not in supported_types:
            raise HTTPException(
                status_code=400,
                detail=f"Неподдерживаемый тип отеля: {hotel_type}"
            )
        
        hotel_type_info = supported_types[hotel_type]
        cache_key_suffix = hotel_type_info["cache_key"]
        
        # Получаем туры из кэша
        cache_key = f"random_tours_{cache_key_suffix}"
        cached_tours = await cache_service.get(cache_key)
        
        if not cached_tours:
            raise HTTPException(
                status_code=404,
                detail=f"Нет туров в кэше для типа {hotel_type}"
            )
        
        if tour_index >= len(cached_tours):
            raise HTTPException(
                status_code=404,
                detail=f"Тур с индексом {tour_index} не найден. Доступно туров: {len(cached_tours)}"
            )
        
        tour = cached_tours[tour_index]
        
        # Полное обогащение тура
        detailed_tour = await _enrich_preview_tour(tour)
        
        # Дополнительные API данные если запрошены
        if include_api_data:
            hotel_code = tour.get("hotelcode")
            if hotel_code and not hotel_code.startswith("MOCK_"):
                try:
                    from app.core.tourvisor_client import tourvisor_client
                    hotel_details = await tourvisor_client.get_hotel_info(
                        hotel_code, 
                        include_reviews=True, 
                        big_images=True
                    )
                    if hotel_details:
                        detailed_tour["api_hotel_details"] = hotel_details
                except Exception as api_error:
                    logger.debug(f"Не удалось получить API данные: {api_error}")
        
        return {
            "success": True,
            "hotel_type": hotel_type_info,
            "tour_index": tour_index,
            "detailed_tour": detailed_tour,
            "structure_info": {
                "hotel_fields": ["hotelcode", "hotelname", "hotelstars", "hotelrating", "countryname", "regionname"],
                "tour_fields": ["operatorname", "flydate", "nights", "price", "meal", "placement"],
                "enhanced_fields": ["hoteldescriptions", "tours"],
                "compatibility": "Структура совместима с результатами обычного поиска TourVisor"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Ошибка получения детального preview: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка получения детальной информации: {str(e)}"
        )