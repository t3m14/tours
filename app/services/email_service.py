import smtplib
import asyncio
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor
import html
import ssl

from app.config import settings
from app.models.application import Application
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class EmailService:
    def __init__(self):
        # ИСПРАВЛЕНИЕ: Правильные настройки для Yandex SMTP
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.yandex.ru")  # НЕ imap!
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))  # 587 для STARTTLS или 465 для SSL
        self.smtp_username = os.getenv("SMTP_USERNAME", "alexandratur@yandex.ru")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "mizgfrbblvrdbtrv")
        self.email_from = os.getenv("EMAIL_FROM", "alexandratur@yandex.ru")
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
        msg = MIMEMultipart('alternative')
        msg['From'] = self.email_from
        msg['To'] = self.email_to
        msg['Subject'] = f"Новая заявка {application.type.lower()} - {application.name}"
        
        # Создаем текстовую версию письма (для совместимости)
        text_body = f"""
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
        
        # Создаем HTML-версию письма
        html_body = self._create_html_body(application)
        
        # Добавляем обе версии в письмо
        text_part = MIMEText(text_body, 'plain', 'utf-8')
        html_part = MIMEText(html_body, 'html', 'utf-8')
        
        msg.attach(text_part)
        msg.attach(html_part)
        
        return msg
    
    def _create_html_body(self, application: Application) -> str:
        """Создание HTML-версии письма с поддержкой custom body"""
        
        # Основная HTML-структура
        html_template = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Новая заявка</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background-color: #007bff;
            color: white;
            padding: 20px;
            border-radius: 8px 8px 0 0;
            text-align: center;
        }}
        .content {{
            background-color: #f8f9fa;
            padding: 20px;
            border: 1px solid #dee2e6;
        }}
        .section {{
            margin-bottom: 20px;
            padding: 15px;
            background-color: white;
            border-radius: 5px;
            border-left: 4px solid #007bff;
        }}
        .section h3 {{
            margin-top: 0;
            color: #007bff;
        }}
        .info-row {{
            margin-bottom: 10px;
        }}
        .info-row strong {{
            color: #495057;
        }}
        .custom-body {{
            margin-top: 20px;
            padding: 15px;
            background-color: #fff;
            border-radius: 5px;
            border: 1px solid #dee2e6;
        }}
        .footer {{
            background-color: #6c757d;
            color: white;
            padding: 15px;
            text-align: center;
            border-radius: 0 0 8px 8px;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Новая заявка с сайта</h1>
        <p>Тип заявки: <strong>{application.type}</strong></p>
        <p>Дата: {application.created_at.strftime('%d.%m.%Y %H:%M:%S')}</p>
    </div>
    
    <div class="content">
        <div class="section">
            <h3>Информация о клиенте</h3>
            <div class="info-row"><strong>Имя:</strong> {html.escape(application.name)}</div>
            <div class="info-row"><strong>Телефон:</strong> {html.escape(application.phone)}</div>
            <div class="info-row"><strong>Email:</strong> {html.escape(application.email or 'Не указан')}</div>
            <div class="info-row"><strong>Ближайший офис:</strong> {html.escape(application.nearest_office or 'Не указан')}</div>
            <div class="info-row"><strong>Удобное время для связи:</strong> {html.escape(application.communication_time or 'Не указано')}</div>
        </div>
        
        {self._render_description_section(application)}
        
        {self._render_custom_body_section(application)}
        
        <div class="section">
            <h3>Системная информация</h3>
            <div class="info-row"><strong>ID заявки:</strong> {application.id}</div>
            <div class="info-row"><strong>Статус:</strong> {application.status}</div>
        </div>
    </div>
    
    <div class="footer">
        Письмо отправлено автоматически системой турагентства
    </div>
</body>
</html>
"""
        return html_template
    
    def _render_description_section(self, application: Application) -> str:
        """Рендерит секцию с обычным описанием"""
        if not application.description:
            return ""
        
        return f"""
        <div class="section">
            <h3>Дополнительная информация</h3>
            <div>{html.escape(application.description)}</div>
        </div>
        """
    
    def _render_custom_body_section(self, application: Application) -> str:
        """Рендерит секцию с custom HTML body"""
        if not application.body:
            return ""
        
        # Важно: Мы НЕ экранируем HTML в body, так как это должен быть валидный HTML
        # Но для безопасности стоит добавить базовую валидацию
        sanitized_body = self._sanitize_html(application.body)
        
        return f"""
        <div class="section">
            <h3>Детали заявки</h3>
            <div class="custom-body">
                {sanitized_body}
            </div>
        </div>
        """
    
    def _sanitize_html(self, html_content: str) -> str:
        """Базовая санитизация HTML контента"""
        # Простая санитизация - убираем потенциально опасные теги
        dangerous_tags = ['<script', '<iframe', '<object', '<embed', '<form']
        
        sanitized = html_content
        for tag in dangerous_tags:
            sanitized = sanitized.replace(tag, f'&lt;{tag[1:]}')
            sanitized = sanitized.replace(tag.upper(), f'&lt;{tag[1:].upper()}')
        
        return sanitized
    
    def _send_email_sync(self, msg: MIMEMultipart) -> bool:
        """Синхронная отправка email с поддержкой разных портов Yandex"""
        try:
            logger.info(f"📤 Попытка отправки email через Yandex:")
            logger.info(f"  Host: {self.smtp_host}:{self.smtp_port}")
            logger.info(f"  Login: {self.smtp_username}")
            logger.info(f"  Password length: {len(self.smtp_password)}")
            logger.info(f"  From: {self.email_from}")
            logger.info(f"  To: {self.email_to}")
            
            # Два варианта подключения к Yandex SMTP
            if self.smtp_port == 465:
                # SSL соединение для порта 465
                logger.info("🔐 Используем SSL соединение (порт 465)")
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, context=context) as server:
                    server.login(self.smtp_username, self.smtp_password)
                    text = msg.as_string()
                    server.sendmail(self.email_from, self.email_to, text)
            else:
                # STARTTLS соединение для порта 587 (по умолчанию)
                logger.info("🔐 Используем STARTTLS соединение (порт 587)")
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    server.ehlo()  # Добавляем EHLO для лучшей совместимости
                    server.starttls()
                    server.ehlo()  # Еще раз после STARTTLS
                    server.login(self.smtp_username, self.smtp_password)
                    
                    text = msg.as_string()
                    server.sendmail(self.email_from, self.email_to, text)
            
            logger.info("✅ Email отправлен успешно через Yandex!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке email через Yandex: {e}")
            logger.error(f"🔍 Настройки: host={self.smtp_host}, port={self.smtp_port}")
            logger.error(f"🔍 Username: {self.smtp_username}")
            logger.error(f"🔍 Password: {self.smtp_password[:4]}...{self.smtp_password[-4:]} (len={len(self.smtp_password)})")
            
            # Попробуем альтернативные настройки, если основные не работают
            if self.smtp_port == 587:
                logger.info("🔄 Пробуем порт 465 с SSL...")
                return self._try_alternative_smtp(msg, 465, use_ssl=True)
            elif self.smtp_port == 465:
                logger.info("🔄 Пробуем порт 587 с STARTTLS...")
                return self._try_alternative_smtp(msg, 587, use_ssl=False)
            
            return False
    
    def _try_alternative_smtp(self, msg: MIMEMultipart, alt_port: int, use_ssl: bool = False) -> bool:
        """Пробуем альтернативные настройки SMTP"""
        try:
            logger.info(f"🔄 Альтернативная попытка: порт {alt_port}, SSL={use_ssl}")
            
            if use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.smtp_host, alt_port, context=context) as server:
                    server.login(self.smtp_username, self.smtp_password)
                    text = msg.as_string()
                    server.sendmail(self.email_from, self.email_to, text)
            else:
                with smtplib.SMTP(self.smtp_host, alt_port) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(self.smtp_username, self.smtp_password)
                    
                    text = msg.as_string()
                    server.sendmail(self.email_from, self.email_to, text)
            
            logger.info(f"✅ Альтернативная отправка успешна! (порт {alt_port})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Альтернативная отправка не удалась: {e}")
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
        """Синхронная отправка уведомления - отправляет HTML как есть"""
        try:
            logger.info(f"📤 Отправка HTML уведомления: {subject}")
            logger.info(f"📧 Получатель: {to_email}")
            logger.info(f"📝 HTML длина: {len(body)} символов")
            
            msg = MIMEMultipart('alternative')
            msg['From'] = self.email_from
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # Создаем текстовую версию (убираем HTML теги для fallback)
            import re
            text_body = re.sub('<[^<]+?>', '', body)
            text_body = text_body.replace('&nbsp;', ' ').strip()
            
            # HTML версия - просто передаем body как есть, БЕЗ оберток
            html_body = body  # Вот и всё! Никаких украшений
            
            # Добавляем обе версии
            text_part = MIMEText(text_body, 'plain', 'utf-8')
            html_part = MIMEText(html_body, 'html', 'utf-8')
            
            msg.attach(text_part)
            msg.attach(html_part)
            
            # Используем тот же метод отправки с поддержкой разных портов
            return self._send_email_sync_base(msg)
            
        except Exception as e:
            logger.error(f"❌ Ошибка при отправке HTML уведомления: {e}")
            return False

    def _send_email_sync_base(self, msg: MIMEMultipart) -> bool:
        """Базовый метод отправки email (без дополнительного логирования)"""
        try:
            if self.smtp_port == 465:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, context=context) as server:
                    server.login(self.smtp_username, self.smtp_password)
                    text = msg.as_string()
                    server.sendmail(self.email_from, msg['To'], text)
            else:
                with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(self.smtp_username, self.smtp_password)
                    
                    text = msg.as_string()
                    server.sendmail(self.email_from, msg['To'], text)
            
            logger.info("✅ Email отправлен успешно!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Базовая отправка failed: {e}")
            # Пробуем альтернативный порт
            if self.smtp_port == 587:
                return self._try_alternative_smtp(msg, 465, use_ssl=True)
            elif self.smtp_port == 465:
                return self._try_alternative_smtp(msg, 587, use_ssl=False)
            return False

    def _fix_html_tags(self, html_content: str) -> str:
        """Исправляет распространенные ошибки в HTML"""
        try:
            # Исправляем неправильные теги
            html_content = html_content.replace('<ui>', '<ul>')
            html_content = html_content.replace('</ui>', '</ul>')
            
            # Убираем лишние <br/> внутри списков
            html_content = html_content.replace('<ul><br/>', '<ul>')
            html_content = html_content.replace('<br/></ul>', '</ul>')
            
            # Исправляем структуру списков
            import re
            # Ищем паттерн: список без закрытия
            if '<ul>' in html_content and html_content.count('<ul>') > html_content.count('</ul>'):
                html_content += '</ul>' * (html_content.count('<ul>') - html_content.count('</ul>'))
            
            # Добавляем базовую структуру если её нет
            if not html_content.strip().startswith('<'):
                html_content = f'<div>{html_content}</div>'
            
            # Убираем двойные пробелы и переносы
            html_content = re.sub(r'\s+', ' ', html_content)
            
            logger.info(f"HTML исправлен: {len(html_content)} символов")
            return html_content
            
        except Exception as e:
            logger.error(f"Ошибка при исправлении HTML: {e}")
            return html_content
            
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