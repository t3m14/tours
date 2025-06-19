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
    
    # Настройки популярных стран для направлений (ограниченный список)
    POPULAR_COUNTRIES: List[int] = [1, 4, 22]  # Египет, Турция, Таиланд
    
    # Настройки для случайных туров (расширенные списки)
    # Все доступные страны в TourVisor (можно дополнить по мере необходимости)
    ALL_COUNTRIES: List[int] = [
        1,   # Египет
        4,   # Турция  
        8,   # Греция
        15,  # ОАЭ
        22,  # Таиланд
        35,  # Мальдивы
        9,   # Кипр
        11,  # Болгария
        16,  # Тунис
        17,  # Черногория
        19,  # Испания
        20,  # Италия
        23,  # Индия
        24,  # Шри-Ланка
        25,  # Вьетнам
        26,  # Китай
        27,  # Индонезия
        28,  # Малайзия
        29,  # Сингапур
        30,  # Филиппины
        31,  # Маврикий
        32,  # Сейшелы
        33,  # Танзания
        34,  # Кения
    ]
    
    # Все доступные города вылета
    ALL_DEPARTURE_CITIES: List[int] = [
        1,   # Москва
        2,   # Пермь  
        3,   # Екатеринбург
        4,   # Уфа
        5,   # Санкт-Петербург
        6,   # Казань
        7,   # Нижний Новгород
        8,   # Самара
        9,   # Ростов-на-Дону
        10,  # Краснодар
        11,  # Волгоград
        12,  # Воронеж
        13,  # Саратов
        14,  # Тольятти
        15,  # Ижевск
    ]
    
    # Ограниченные списки для стандартных функций (прогрев кэша, направления)
    DEPARTURE_CITIES: List[int] = [1, 2, 3]    # Москва, Пермь, Екатеринбург
    
    # Количество случайных туров для обновления
    RANDOM_TOURS_COUNT: int = 6
    
    # Настройки типов отелей
    HOTEL_TYPES: List[str] = ["active", "relax", "family", "health", "city", "beach", "deluxe"]
    
    # Настройки кэширования случайных туров
    RANDOM_TOURS_CACHE_TTL: int = 3600  # 1 час (чаще обновляется чем популярные туры)
    
    class Config:
        env_file = ".env"

settings = Settings()