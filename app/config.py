import os
from typing import List
from pathlib import Path

# ИСПРАВЛЕНИЕ: Явная загрузка .env файла
try:
    from dotenv import load_dotenv
    # Ищем .env файл в корне проекта
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ Загружен .env из: {env_path}")
    else:
        print(f"⚠️ .env не найден в: {env_path}")
except ImportError:
    print("⚠️ python-dotenv не установлен, используем os.environ")

class Settings:
    # TourVisor API настройки
    TOURVISOR_AUTH_LOGIN = os.getenv("TOURVISOR_AUTH_LOGIN", "alexandratur@yandex.ru")
    TOURVISOR_AUTH_PASS = os.getenv("TOURVISOR_AUTH_PASS", "BqgYFUGKesS6")
    TOURVISOR_BASE_URL = os.getenv("TOURVISOR_BASE_URL", "http://tourvisor.ru/xml")
    
    # Redis настройки для кэша
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))
    POPULAR_TOURS_CACHE_TTL = int(os.getenv("POPULAR_TOURS_CACHE_TTL", "86400"))
    
    # Email настройки
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    EMAIL_FROM = os.getenv("EMAIL_FROM", "")
    EMAIL_TO = os.getenv("EMAIL_TO", "alexandratur@yandex.ru")
    
    # Отладочная информация
    def __init__(self):
        print(f"🔧 EMAIL НАСТРОЙКИ ИЗ CONFIG:")
        print(f"  SMTP_HOST: {self.SMTP_HOST}")
        print(f"  SMTP_USERNAME: {self.SMTP_USERNAME}")
        print(f"  SMTP_PASSWORD: {'*' * len(self.SMTP_PASSWORD) if self.SMTP_PASSWORD else 'ПУСТОЙ'}")
        print(f"  EMAIL_FROM: {self.EMAIL_FROM}")
        print(f"  EMAIL_TO: {self.EMAIL_TO}")
    
    # Общие настройки
    ALLOWED_HOSTS = ["*"]
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    
    # Настройки популярных стран для направлений (жестко заданные)
    POPULAR_COUNTRIES = [1, 4, 22]  # Египет, Турция, Таиланд
    
    # Все доступные страны в TourVisor
    ALL_COUNTRIES = [
        1, 4, 8, 15, 22, 35, 9, 11, 16, 17, 19, 20, 
        23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34
    ]
    
    # Все доступные города вылета
    ALL_DEPARTURE_CITIES = [
        1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15
    ]
    
    # Ограниченные списки для стандартных функций
    DEPARTURE_CITIES = [1, 2, 3]    # Москва, Пермь, Екатеринбург
    
    # Количество случайных туров для обновления
    RANDOM_TOURS_COUNT = int(os.getenv("RANDOM_TOURS_COUNT", "6"))
    
    # Настройки типов отелей
    HOTEL_TYPES = ["active", "relax", "family", "health", "city", "beach", "deluxe"]
    
    # Настройки кэширования случайных туров
    RANDOM_TOURS_CACHE_TTL = int(os.getenv("RANDOM_TOURS_CACHE_TTL", "3600"))

settings = Settings()