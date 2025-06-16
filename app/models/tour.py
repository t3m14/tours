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
    
    class Config:
        schema_extra = {
            "example": {
                "count": 6
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