import uuid
from datetime import datetime
from typing import List
from fastapi import APIRouter, HTTPException, BackgroundTasks

from app.models.application import ApplicationRequest, ApplicationResponse, Application
from app.services.email_service import email_service
from app.services.cache_service import cache_service
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()

@router.post("/submit", response_model=ApplicationResponse)
async def submit_application(
    application_request: ApplicationRequest,
    background_tasks: BackgroundTasks
):
    """
    Отправка заявки с сайта
    
    Сохраняет заявку и отправляет на email alexandratur@yandex.ru
    """
    try:
        # Создаем объект заявки
        application_id = str(uuid.uuid4())
        application = Application(
            id=application_id,
            type=application_request.type,
            name=application_request.name,
            phone=application_request.phone,
            email=application_request.email,
            nearest_office=application_request.nearest_office,
            communication_time=application_request.communication_time,
            description=application_request.description,
            created_at=datetime.now(),
            status="new"
        )
        
        # Сохраняем заявку в кэш (Redis)
        await cache_service.set(
            f"application:{application_id}",
            application.model_dump(),
            ttl=2592000  # 30 дней
        )
        
        # Добавляем ID в список всех заявок
        all_applications = await cache_service.get("all_applications") or []
        all_applications.append(application_id)
        await cache_service.set("all_applications", all_applications, ttl=2592000)
        
        # Отправляем email в фоновой задаче
        background_tasks.add_task(email_service.send_application_email, application)
        
        logger.info(f"Создана новая заявка {application_id} от {application.name}")
        
        return ApplicationResponse(
            success=True,
            message="Заявка успешно отправлена. Мы свяжемся с вами в ближайшее время.",
            application_id=application_id
        )
        
    except Exception as e:
        logger.error(f"Ошибка при создании заявки: {e}")
        raise HTTPException(
            status_code=500,
            detail="Произошла ошибка при обработке заявки. Попробуйте еще раз."
        )

@router.get("/{application_id}", response_model=Application)
async def get_application(application_id: str):
    """
    Получение информации о заявке по ID
    """
    try:
        application_data = await cache_service.get(f"application:{application_id}")
        
        if not application_data:
            raise HTTPException(status_code=404, detail="Заявка не найдена")
        
        return Application(**application_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении заявки {application_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при получении заявки")

@router.get("/", response_model=List[Application])
async def get_all_applications(limit: int = 50, offset: int = 0):
    """
    Получение списка всех заявок (для админки)
    """
    try:
        all_application_ids = await cache_service.get("all_applications") or []
        
        # Применяем пагинацию
        paginated_ids = all_application_ids[offset:offset + limit]
        
        applications = []
        for app_id in paginated_ids:
            app_data = await cache_service.get(f"application:{app_id}")
            if app_data:
                applications.append(Application(**app_data))
        
        # Сортируем по дате создания (новые сначала)
        applications.sort(key=lambda x: x.created_at, reverse=True)
        
        return applications
        
    except Exception as e:
        logger.error(f"Ошибка при получении списка заявок: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при получении заявок")

@router.patch("/{application_id}/status")
async def update_application_status(application_id: str, status: str):
    """
    Обновление статуса заявки
    """
    try:
        application_data = await cache_service.get(f"application:{application_id}")
        
        if not application_data:
            raise HTTPException(status_code=404, detail="Заявка не найдена")
        
        application_data["status"] = status
        
        await cache_service.set(
            f"application:{application_id}",
            application_data,
            ttl=2592000
        )
        
        logger.info(f"Статус заявки {application_id} изменен на {status}")
        
        return {"success": True, "message": f"Статус заявки изменен на {status}"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при обновлении статуса заявки {application_id}: {e}")
        raise HTTPException(status_code=500, detail="Ошибка при обновлении статуса")