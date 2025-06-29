# app/api/v1/directions_cache.py

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, Any
from datetime import datetime

from app.tasks.directions_cache_update import directions_cache_update_service
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/directions/cache", tags=["Directions Cache Management"])

@router.get("/status")
async def get_cache_update_status() -> Dict[str, Any]:
    """
    Получение статуса автоматического обновления кэша направлений
    
    Возвращает информацию о:
    - Текущем статусе планировщика
    - Времени последнего обновления
    - Времени следующего обновления
    - Статистике последнего обновления
    """
    try:
        logger.info("📊 Запрос статуса обновления кэша направлений")
        
        status = await directions_cache_update_service.get_update_status()
        
        # Добавляем дополнительную информацию
        current_time = datetime.now()
        status["current_time"] = current_time
        status["scheduler_info"] = {
            "update_interval_hours": directions_cache_update_service.update_interval / 3600,
            "batch_size": directions_cache_update_service.countries_batch_size,
            "total_countries": len(directions_cache_update_service.countries_mapping) if hasattr(directions_cache_update_service, 'countries_mapping') else 13
        }
        
        return status
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения статуса кэша: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при получении статуса: {str(e)}"
        )

@router.post("/force-update")
async def force_cache_update(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Принудительное обновление кэша направлений
    
    Запускает полное обновление всех направлений в фоновом режиме.
    Внимание: процесс может занять 2-4 часа!
    """
    try:
        logger.info("🚀 API запрос принудительного обновления кэша")
        
        # Проверяем, не запущено ли уже обновление
        status = await directions_cache_update_service.get_update_status()
        
        if status.get("is_running") and status.get("update_stats", {}).get("end_time") is None:
            return {
                "success": False,
                "message": "Обновление уже выполняется",
                "current_status": status
            }
        
        # Запускаем принудительное обновление в фоне
        background_tasks.add_task(directions_cache_update_service.force_update_now)
        
        return {
            "success": True,
            "message": "Принудительное обновление кэша запущено в фоновом режиме",
            "estimated_duration": "2-4 часа",
            "note": "Используйте GET /status для отслеживания прогресса",
            "started_at": datetime.now()
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска принудительного обновления: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при запуске обновления: {str(e)}"
        )

@router.get("/stats")
async def get_detailed_cache_stats() -> Dict[str, Any]:
    """
    Подробная статистика кэша направлений
    
    Возвращает детальную информацию о последнем обновлении,
    включая статистику по каждой стране.
    """
    try:
        logger.info("📈 Запрос детальной статистики кэша")
        
        status = await directions_cache_update_service.get_update_status()
        update_stats = status.get("update_stats")
        
        if not update_stats:
            return {
                "message": "Статистика недоступна - обновлений еще не было",
                "recommendation": "Запустите принудительное обновление: POST /force-update"
            }
        
        # Анализируем статистику по странам
        countries_details = update_stats.get("countries_details", {})
        
        # Топ стран по количеству направлений
        top_countries = sorted(
            [(name, data) for name, data in countries_details.items() if data.get("success")],
            key=lambda x: x[1].get("directions_count", 0),
            reverse=True
        )[:5]
        
        # Страны с проблемами
        failed_countries = [
            name for name, data in countries_details.items() 
            if not data.get("success")
        ]
        
        # Статистика качества данных
        total_directions = sum(
            data.get("directions_count", 0) 
            for data in countries_details.values() 
            if data.get("success")
        )
        
        # Средние показатели качества
        quality_stats = []
        for name, data in countries_details.items():
            if data.get("success") and data.get("quality_stats"):
                quality_stats.append(data["quality_stats"])
        
        avg_price_coverage = 0
        avg_image_coverage = 0
        if quality_stats:
            avg_price_coverage = sum(
                float(qs.get("price_coverage", "0%").replace("%", "")) 
                for qs in quality_stats
            ) / len(quality_stats)
            
            avg_image_coverage = sum(
                float(qs.get("image_coverage", "0%").replace("%", "")) 
                for qs in quality_stats
            ) / len(quality_stats)
        
        return {
            "last_update": update_stats.get("end_time"),
            "execution_summary": {
                "total_countries": update_stats.get("total_countries", 0),
                "successful_countries": update_stats.get("successful_countries", 0),
                "failed_countries": update_stats.get("failed_countries", 0),
                "success_rate": f"{update_stats.get('success_rate', 0):.1f}%",
                "total_directions": total_directions,
                "execution_time": f"{update_stats.get('execution_time_seconds', 0):.1f} сек"
            },
            "data_quality": {
                "average_price_coverage": f"{avg_price_coverage:.1f}%",
                "average_image_coverage": f"{avg_image_coverage:.1f}%"
            },
            "top_countries_by_directions": [
                {
                    "country": name,
                    "directions_count": data.get("directions_count", 0),
                    "execution_time": f"{data.get('execution_time_seconds', 0):.1f}s"
                }
                for name, data in top_countries
            ],
            "failed_countries": failed_countries,
            "countries_details": countries_details
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка получения детальной статистики: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при получении статистики: {str(e)}"
        )

@router.post("/scheduler/start")
async def start_cache_scheduler(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Запуск планировщика автоматического обновления кэша
    
    Планировщик будет обновлять кэш каждые 24 часа автоматически.
    """
    try:
        logger.info("▶️ API запрос запуска планировщика")
        
        if directions_cache_update_service.is_running:
            return {
                "success": False,
                "message": "Планировщик уже запущен",
                "status": "running"
            }
        
        # Запускаем планировщик в фоне
        background_tasks.add_task(directions_cache_update_service.start_scheduler)
        
        return {
            "success": True,
            "message": "Планировщик автоматического обновления кэша запущен",
            "schedule": "каждые 24 часа",
            "started_at": datetime.now()
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка запуска планировщика: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при запуске планировщика: {str(e)}"
        )

@router.post("/scheduler/stop")
async def stop_cache_scheduler() -> Dict[str, Any]:
    """
    Остановка планировщика автоматического обновления кэша
    """
    try:
        logger.info("⏹️ API запрос остановки планировщика")
        
        if not directions_cache_update_service.is_running:
            return {
                "success": False,
                "message": "Планировщик уже остановлен",
                "status": "stopped"
            }
        
        await directions_cache_update_service.stop_scheduler()
        
        return {
            "success": True,
            "message": "Планировщик автоматического обновления кэша остановлен",
            "stopped_at": datetime.now()
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка остановки планировщика: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при остановке планировщика: {str(e)}"
        )

@router.get("/health")
async def cache_health_check() -> Dict[str, Any]:
    """
    Проверка здоровья системы кэширования направлений
    
    Проверяет актуальность кэша и работоспособность системы.
    """
    try:
        from app.services.cache_service import cache_service
        from app.services.directions_service import directions_service
        
        # Проверяем кэш
        cache_keys_count = 0
        try:
            # Пытаемся подсчитать количество ключей
            for country_name, country_info in directions_service.COUNTRIES_MAPPING.items():
                country_id = country_info.get("country_id")
                if country_id:
                    cache_key = f"directions_with_prices_country_{country_id}"
                    cached_data = await cache_service.get(cache_key)
                    if cached_data:
                        cache_keys_count += 1
        except:
            pass
        
        # Получаем статус обновления
        status = await directions_cache_update_service.get_update_status()
        
        # Определяем состояние здоровья
        health_status = "unknown"
        issues = []
        
        if cache_keys_count == 0:
            health_status = "poor"
            issues.append("Нет кэшированных данных")
        elif cache_keys_count < 5:
            health_status = "warning"
            issues.append("Мало кэшированных данных")
        else:
            health_status = "good"
        
        if not status.get("is_running"):
            issues.append("Планировщик не запущен")
            if health_status == "good":
                health_status = "warning"
        
        last_update = status.get("last_update")
        if last_update:
            from datetime import datetime, timedelta
            if isinstance(last_update, str):
                last_update = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
            
            hours_since_update = (datetime.now() - last_update).total_seconds() / 3600
            if hours_since_update > 48:  # Более 48 часов
                issues.append("Давно не было обновлений")
                health_status = "warning"
        
        return {
            "health_status": health_status,
            "cache_keys_count": cache_keys_count,
            "total_countries": len(directions_service.COUNTRIES_MAPPING),
            "cache_coverage": f"{(cache_keys_count / len(directions_service.COUNTRIES_MAPPING) * 100):.1f}%",
            "scheduler_running": status.get("is_running", False),
            "last_update": last_update,
            "issues": issues,
            "recommendations": [
                "Запустите планировщик: POST /scheduler/start" if not status.get("is_running") else None,
                "Выполните обновление: POST /force-update" if cache_keys_count < 5 else None
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка проверки здоровья: {e}")
        return {
            "health_status": "error",
            "error": str(e),
            "cache_keys_count": 0,
            "issues": ["Ошибка при проверке здоровья системы"]
        }