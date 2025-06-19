import os
from typing import List

class Settings:
    # TourVisor API настройки
    TOURVISOR_AUTH_LOGIN = os.getenv("TOURVISOR_AUTH_LOGIN", "")
    TOURVISOR_AUTH_PASS = os.getenv("TOURVISOR_AUTH_PASS", "")
    TOURVISOR_BASE_URL = os.getenv("TOURVISOR_BASE_URL", "http://tourvisor.ru/xml")
    
    # Redis настройки для кэша
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))
    POPULAR_TOURS_CACHE_TTL = int(os.getenv("POPULAR_TOURS_CACHE_TTL", "86400"))
    
    # Email настройки
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.yandex.ru")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    EMAIL_FROM = os.getenv("EMAIL_FROM", "")
    EMAIL_TO = os.getenv("EMAIL_TO", "alexandratur@yandex.ru")
    
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