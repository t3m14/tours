import smtplib
import asyncio
import os
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
        # ИСПРАВЛЕНИЕ: Принудительная загрузка Gmail настроек
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME", "advice.notifications@gmail.com")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "tven oyop yxgf tltf")
        self.email_from = os.getenv("EMAIL_FROM", "advice.notifications@gmail.com")
        self.email_to = os.getenv("EMAIL_TO", "temi4174@mail.ru")
        
        # Очистка от кавычек и пробелов
        self.smtp_password = self.smtp_password.strip().strip("'\"").replace(" ", "")
        self.smtp_username = self.smtp_username.strip().strip("'\"")
        self.email_from = self.email_from.strip().strip("'\"")
        
        self.executor = ThreadPoolExecutor(max_workers=2)
        
        # ОТЛАДКА: Логируем загруженные настройки
        logger.info(f"🔧 EMAIL SERVICE INIT:")
        logger.info(f"  SMTP_HOST: {self.smtp_host}")
        logger.info(f"  SMTP_PORT: {self.smtp_port}")
        logger.info(f"  SMTP_USERNAME: {self.smtp_username}")
        logger.info(f"  SMTP_PASSWORD: {'*' * len(self.smtp_password)} (len={len(self.smtp_password)})")
        logger.info(f"  EMAIL_FROM: {self.email_from}")
        logger.info(f"  EMAIL_TO: {self.email_to}")

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
            logger.info(f"📤 Попытка отправки email:")
            logger.info(f"  Host: {self.smtp_host}:{self.smtp_port}")
            logger.info(f"  Login: {self.smtp_username}")
            logger.info(f"  Password length: {len(self.smtp_password)}")
            logger.info(f"  From: {self.email_from}")
            logger.info(f"  To: {self.email_to}")
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                
                text = msg.as_string()
                server.sendmail(self.email_from, self.email_to, text)
            
            logger.info("✅ Email отправлен успешно!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке email: {e}")
            logger.error(f"🔍 Настройки: host={self.smtp_host}, port={self.smtp_port}")
            logger.error(f"🔍 Username: {self.smtp_username}")
            logger.error(f"🔍 Password: {self.smtp_password[:4]}...{self.smtp_password[-4:]} (len={len(self.smtp_password)})")
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
                logger.info(f"✅ Email с заявкой {application.id} успешно отправлен")
            else:
                logger.error(f"❌ Не удалось отправить email с заявкой {application.id}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке email с заявкой {application.id}: {e}")
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