from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    # TourVisor API настройки
    TOURVISOR_AUTH_LOGIN: str
    TOURVISOR_AUTH_PASS: str
    TOURVISOR_BASE_URL: str = "http://tourvisor.ru/xml"
    
    # Redis настройки для кэша
    REDIS_URL: str = "redis://localhost:6379"
    CACHE_TTL: int = 3600  # 1 час
    POPULAR_TOURS_CACHE_TTL: int = 86400  # 24 часа
    
    # Email настройки
    SMTP_HOST: str
    SMTP_PORT: int = 587
    SMTP_USERNAME: str
    SMTP_PASSWORD: str
    EMAIL_FROM: str
    EMAIL_TO: str = "alexandratur@yandex.ru"
    
    # Общие настройки
    ALLOWED_HOSTS: List[str] = ["*"]
    DEBUG: bool = False
    
    # Настройки кэширования популярных туров
    POPULAR_COUNTRIES: List[int] = [1, 4, 22]  # Египет, Турция, Таиланд
    DEPARTURE_CITIES: List[int] = [1, 2, 3]    # Москва, Питер, Екатеринбург
    
    # Количество случайных туров для обновления
    RANDOM_TOURS_COUNT: int = 6
    
    class Config:
        env_file = ".env"

settings = Settings()