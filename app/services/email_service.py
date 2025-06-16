import smtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from app.config import settings
from app.models.application import Application
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class EmailService:
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_username = settings.SMTP_USERNAME
        self.smtp_password = settings.SMTP_PASSWORD
        self.email_from = settings.EMAIL_FROM
        self.email_to = settings.EMAIL_TO
        self.executor = ThreadPoolExecutor(max_workers=2)
    
    def _create_application_email(self, application: Application) -> MIMEMultipart:
        """Создание email с информацией о заявке"""
        msg = MIMEMultipart()
        msg['From'] = self.email_from
        msg['To'] = self.email_to
        msg['Subject'] = f"Новая заявка {application.type} - {application.name}"
        
        # Создаем тело письма
        body = f"""
Получена новая заявка с сайта турагентства

Тип заявки: {application.type}
Дата и время: {application.created_at.strftime('%d.%m.%Y %H:%M:%S')}

=== ИНФОРМАЦИЯ О КЛИЕНТЕ ===
Имя: {application.name}
Телефон: {application.phone}
Email: {application.email or 'Не указан'}
Ближайший офис: {application.nearest_office or 'Не указан'}
Удобное время для связи: {application.communication_time or 'Не указано'}

=== ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ ===
{application.description or 'Отсутствует'}

=== СИСТЕМНАЯ ИНФОРМАЦИЯ ===
ID заявки: {application.id}
Статус: {application.status}

---
Письмо отправлено автоматически системой турагентства
"""
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        return msg
    
    def _send_email_sync(self, msg: MIMEMultipart) -> bool:
        """Синхронная отправка email"""
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                
                text = msg.as_string()
                server.sendmail(self.email_from, self.email_to, text)
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при отправке email: {e}")
            return False
    
    async def send_application_email(self, application: Application) -> bool:
        """Отправка email с заявкой (асинхронная обертка)"""
        try:
            msg = self._create_application_email(application)
            
            # Выполняем отправку в thread pool чтобы не блокировать event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor, 
                self._send_email_sync, 
                msg
            )
            
            if result:
                logger.info(f"Email с заявкой {application.id} успешно отправлен")
            else:
                logger.error(f"Не удалось отправить email с заявкой {application.id}")
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при отправке email с заявкой {application.id}: {e}")
            return False
    
    def _send_notification_sync(self, subject: str, body: str, to_email: str) -> bool:
        """Синхронная отправка уведомления"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_from
            msg['To'] = to_email
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                
                text = msg.as_string()
                server.sendmail(self.email_from, to_email, text)
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления '{subject}': {e}")
            return False
    
    async def send_notification_email(self, subject: str, body: str, to_email: Optional[str] = None) -> bool:
        """Отправка уведомления на email (асинхронная обертка)"""
        try:
            target_email = to_email or self.email_to
            
            # Выполняем отправку в thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor,
                self._send_notification_sync,
                subject,
                body,
                target_email
            )
            
            if result:
                logger.info(f"Уведомление '{subject}' успешно отправлено")
            else:
                logger.error(f"Не удалось отправить уведомление '{subject}'")
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления '{subject}': {e}")
            return False

# Создаем экземпляр сервиса
email_service = EmailService()