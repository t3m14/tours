# app/models/direction.py
from pydantic import BaseModel, Field
from typing import List, Optional

class CityDirectionInfo(BaseModel):
    """Информация о направлении (городе/курорте) с фотографией"""
    city_name: str = Field(..., description="Название города/курорта")
    city_id: int = Field(..., description="ID города/курорта")
    country_name: str = Field(..., description="Название страны")
    country_id: int = Field(..., description="ID страны")
    image_link: str = Field(..., description="Ссылка на фотографию")
    min_price: float = Field(..., description="Минимальная цена")

class CountryDirectionsResponse(BaseModel):
    """Ответ с направлениями по стране"""
    country_name: str
    country_id: int
    cities: List[CityDirectionInfo]
    total_cities: int

class DirectionsResponse(BaseModel):
    """Полный ответ направлений"""
    countries: List[CountryDirectionsResponse]
    total_countries: int
    total_cities: int