from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class TourSearchRequest(BaseModel):
    departure: int = Field(..., description="Код города вылета")
    country: int = Field(..., description="Код страны")
    datefrom: Optional[str] = Field(None, description="Дата от в формате дд.мм.гггг")
    dateto: Optional[str] = Field(None, description="Дата до в формате дд.мм.гггг")
    nightsfrom: int = Field(7, description="Ночей от")
    nightsto: int = Field(10, description="Ночей до")
    adults: int = Field(2, description="Количество взрослых")
    child: int = Field(0, description="Количество детей")
    childage1: Optional[int] = Field(None, description="Возраст 1 ребенка")
    childage2: Optional[int] = Field(None, description="Возраст 2 ребенка")
    childage3: Optional[int] = Field(None, description="Возраст 3 ребенка")
    stars: Optional[int] = Field(None, description="Категория отеля")
    starsbetter: int = Field(1, description="Показывать категории лучше")
    meal: Optional[int] = Field(None, description="Тип питания")
    mealbetter: int = Field(1, description="Показывать питание лучше")
    rating: Optional[int] = Field(None, description="Рейтинг отеля")
    hotels: Optional[str] = Field(None, description="Коды отелей через запятую")
    hoteltypes: Optional[str] = Field(None, description="Типы отелей через запятую")
    pricetype: int = Field(0, description="Тип цены: 0 - за номер, 1 - за человека")
    regions: Optional[str] = Field(None, description="Коды курортов через запятую")
    subregions: Optional[str] = Field(None, description="Коды районов через запятую")
    operators: Optional[str] = Field(None, description="Коды операторов через запятую")
    pricefrom: Optional[int] = Field(None, description="Цена от")
    priceto: Optional[int] = Field(None, description="Цена до")
    currency: int = Field(0, description="Валюта: 0-рубли, 1-у.е., 2-бел.рубли, 3-тенге")
    hideregular: Optional[int] = Field(None, description="Скрыть туры на регулярных рейсах")
    services: Optional[str] = Field(None, description="Услуги в отеле через запятую")

class TourInfo(BaseModel):
    operatorcode: str
    operatorname: str
    flydate: str
    nights: int
    price: float
    fuelcharge: float
    priceue: Optional[float] = None
    placement: str
    adults: int
    child: int
    meal: str
    mealrussian: str
    room: str
    tourname: str
    tourlink: Optional[str] = None
    tourid: str
    currency: str
    regular: Optional[int] = None
    promo: Optional[int] = None
    onrequest: Optional[int] = None
    flightstatus: Optional[int] = None
    hotelstatus: Optional[int] = None
    nightflight: Optional[int] = None

class HotelInfo(BaseModel):
    hotelcode: str
    price: float
    countrycode: str
    countryname: str
    regioncode: str
    regionname: str
    subregioncode: Optional[str] = None
    hotelname: str
    hotelstars: int
    hotelrating: float
    hoteldescription: Optional[str] = None
    fulldesclink: Optional[str] = None
    reviewlink: Optional[str] = None
    picturelink: Optional[str] = None
    isphoto: Optional[int] = None
    iscoords: Optional[int] = None
    isdescription: Optional[int] = None
    isreviews: Optional[int] = None
    seadistance: Optional[int] = None
    tours: List[TourInfo]

class SearchStatus(BaseModel):
    state: str  # searching или finished
    hotelsfound: int
    toursfound: int
    minprice: Optional[float] = None
    progress: int
    timepassed: int

class SearchResult(BaseModel):
    status: SearchStatus
    result: Optional[List[HotelInfo]] = None

class SearchResponse(BaseModel):
    request_id: str

class RandomTourRequest(BaseModel):
    count: int = Field(6, ge=1, le=20, description="Количество случайных туров")
    hotel_types: Optional[List[str]] = Field(
        None, 
        description="Типы отелей для фильтрации: active, relax, family, health, city, beach, deluxe"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "count": 6,
                "hotel_types": ["beach", "relax"]
            }
        }

class DirectionInfo(BaseModel):
    name: str
    image_link: str
    min_price: float

class HotTourInfo(BaseModel):
    countrycode: str
    countryname: str
    departurecode: str
    departurename: str
    departurenamefrom: str
    operatorcode: str
    operatorname: str
    hotelcode: str
    hotelname: str
    hotelstars: int
    hotelregioncode: str
    hotelregionname: str
    hotelpicture: str
    fulldesclink: Optional[str] = None
    flydate: str
    nights: int
    meal: str
    price: float
    priceold: Optional[float] = None
    currency: str

class TourActualizationRequest(BaseModel):
    tour_id: str
    request_check: int = Field(0, description="0-авто, 1-принудительно, 2-из кэша")
    currency: int = Field(0, description="Валюта вывода")

class Flight(BaseModel):
    company: Dict[str, Any]
    number: str
    plane: Optional[str] = None
    departure: Dict[str, str]
    arrival: Dict[str, str]

class FlightInfo(BaseModel):
    forward: List[Flight]
    backward: List[Flight]
    dateforward: str
    datebackward: str
    price: Dict[str, Any]
    fuelcharge: Dict[str, Any]
    isdefault: bool

class TourContent(BaseModel):
    addpayments: Optional[List[Dict[str, Any]]] = None
    contents: Optional[List[str]] = None
    flags: Optional[Dict[str, bool]] = None

class DetailedTourInfo(BaseModel):
    tour: Dict[str, Any]
    flights: List[FlightInfo]
    tourinfo: Optional[TourContent] = None


# app/models/tour.py - добавить эти модели

class SpecificTourSearchRequest(BaseModel):
    """Запрос поиска конкретного тура"""
    departure: int = Field(..., description="Код города вылета")
    country: int = Field(..., description="Код страны")
    
    # Фильтры отеля
    hotel_stars: Optional[int] = Field(None, ge=1, le=5, description="Звездность отеля")
    hotel_name: Optional[str] = Field(None, min_length=3, description="Название отеля")
    hotel_id: Optional[str] = Field(None, description="ID отеля")
    region_code: Optional[int] = Field(None, description="Код курорта")
    
    # Фильтры тура
    nights: Optional[int] = Field(None, ge=1, le=30, description="Количество ночей")
    adults: int = Field(2, ge=1, le=8, description="Количество взрослых")
    children: int = Field(0, ge=0, le=4, description="Количество детей")
    meal_type: Optional[int] = Field(None, description="Тип питания (код)")
    
    # Фильтры цены
    max_price: Optional[int] = Field(None, gt=0, description="Максимальная цена")
    min_price: Optional[int] = Field(None, gt=0, description="Минимальная цена")
    
    # Фильтры дат
    date_from: Optional[str] = Field(None, description="Дата от (дд.мм.гггг)")
    date_to: Optional[str] = Field(None, description="Дата до (дд.мм.гггг)")
    
    # Дополнительные фильтры
    rating: Optional[float] = Field(None, ge=1.0, le=5.0, description="Минимальный рейтинг отеля")
    hotel_type: Optional[str] = Field(None, description="Тип отеля: beach,city,family,deluxe,etc")
    
    class Config:
        schema_extra = {
            "example": {
                "departure": 1,
                "country": 4,
                "hotel_stars": 4,
                "meal_type": 2,
                "nights": 7,
                "adults": 2,
                "max_price": 80000
            }
        }

class FoundTourInfo(BaseModel):
    """Информация о найденном туре"""
    
    # Информация об отеле
    hotel_id: Optional[str] = Field(None, description="ID отеля")
    hotel_name: str = Field(..., description="Название отеля")
    hotel_stars: int = Field(..., description="Звездность отеля")
    hotel_rating: Optional[float] = Field(None, description="Рейтинг отеля")
    hotel_description: Optional[str] = Field(None, description="Описание отеля")
    hotel_picture: Optional[str] = Field(None, description="Ссылка на фото отеля")
    hotel_review_link: Optional[str] = Field(None, description="Ссылка на отзывы")
    country_name: str = Field(..., description="Название страны")
    region_name: str = Field(..., description="Название курорта")
    sea_distance: Optional[int] = Field(None, description="Расстояние до моря в метрах")
    
    # Информация о туре
    tour_id: Optional[str] = Field(None, description="ID тура")
    operator_name: str = Field(..., description="Название туроператора")
    fly_date: str = Field(..., description="Дата вылета")
    nights: int = Field(..., description="Количество ночей")
    price: float = Field(..., description="Цена тура")
    fuel_charge: Optional[float] = Field(None, description="Топливный сбор")
    meal: str = Field(..., description="Тип питания")
    room_type: str = Field(..., description="Тип номера")
    adults: int = Field(..., description="Количество взрослых")
    children: int = Field(..., description="Количество детей")
    currency: str = Field(..., description="Валюта")
    tour_link: Optional[str] = Field(None, description="Ссылка на тур у оператора")
    
    # Дополнительная информация
    is_regular: bool = Field(False, description="Тур на регулярных рейсах")
    is_promo: bool = Field(False, description="Промо тур")
    is_on_request: bool = Field(False, description="Места под запрос")
    flight_status: Optional[int] = Field(None, description="Статус рейсов")
    hotel_status: Optional[int] = Field(None, description="Статус отеля")
    
    # Метаинформация о поиске
    search_results_count: Optional[int] = Field(None, description="Количество найденных туров")
    hotels_found: Optional[int] = Field(None, description="Количество найденных отелей")
    is_fallback: Optional[bool] = Field(False, description="Результат fallback поиска")
    fallback_strategy: Optional[int] = Field(None, description="Номер fallback стратегии")
    
    class Config:
        schema_extra = {
            "example": {
                "hotel_id": "123",
                "hotel_name": "CRYSTAL ADMIRAL RESORT SUITES & SPA",
                "hotel_stars": 5,
                "hotel_rating": 4.2,
                "hotel_description": "Роскошный отель на берегу моря",
                "hotel_picture": "https://example.com/hotel.jpg",
                "country_name": "Турция",
                "region_name": "Сиде",
                "sea_distance": 50,
                "tour_id": "16347248245",
                "operator_name": "Coral Travel",
                "fly_date": "15.07.2025",
                "nights": 7,
                "price": 75000,
                "fuel_charge": 0,
                "meal": "Всё включено",
                "room_type": "Standard Room",
                "adults": 2,
                "children": 0,
                "currency": "RUB",
                "is_regular": False,
                "is_promo": False,
                "is_on_request": False,
                "search_results_count": 45,
                "hotels_found": 12
            }
        }

class TourSearchError(BaseModel):
    """Ошибка поиска тура"""
    error: str = Field(..., description="Тип ошибки")
    message: str = Field(..., description="Описание ошибки")
    suggestions: List[str] = Field(default=[], description="Предложения по улучшению поиска")
    
    class Config:
        schema_extra = {
            "example": {
                "error": "Тур не найден",
                "message": "По заданным критериям туры не найдены",
                "suggestions": [
                    "Попробуйте отели 3* или без фильтра по звездности",
                    "Увеличьте максимальную цену до 90,000 руб.",
                    "Попробуйте 5-9 ночей вместо точно 7",
                    "Измените даты поездки на ±7 дней"
                ]
            }
        }

class QuickTourSearchRequest(BaseModel):
    """Упрощенный запрос поиска тура"""
    departure: int = Field(..., description="Код города вылета")
    country: int = Field(..., description="Код страны")
    hotel_stars: int = Field(..., ge=1, le=5, description="Звездность отеля")
    meal_type: int = Field(..., description="Тип питания")
    max_price: Optional[int] = Field(None, gt=0, description="Максимальная цена")
    nights: int = Field(7, ge=1, le=30, description="Количество ночей")
    adults: int = Field(2, ge=1, le=8, description="Количество взрослых")
    
    class Config:
        schema_extra = {
            "example": {
                "departure": 1,
                "country": 4,
                "hotel_stars": 4,
                "meal_type": 2,
                "max_price": 80000,
                "nights": 7,
                "adults": 2
            }
        }

class HotelSearchRequest(BaseModel):
    """Запрос поиска тура по отелю"""
    hotel_name: str = Field(..., min_length=3, description="Название отеля")
    departure: int = Field(..., description="Код города вылета")
    country: int = Field(..., description="Код страны")
    nights: int = Field(7, ge=1, le=30, description="Количество ночей")
    adults: int = Field(2, ge=1, le=8, description="Количество взрослых")
    children: int = Field(0, ge=0, le=4, description="Количество детей")
    
    class Config:
        schema_extra = {
            "example": {
                "hotel_name": "hilton",
                "departure": 1,
                "country": 4,
                "nights": 7,
                "adults": 2,
                "children": 0
            }
        }