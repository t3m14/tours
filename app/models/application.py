from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Literal
from datetime import datetime

class ApplicationRequest(BaseModel):
    type: str = Field(..., description="Тип заявки: 'на консультацию' или 'на рассрочку'")
    name: str = Field(..., min_length=1, max_length=100, description="Имя клиента")
    phone: str = Field(..., min_length=10, max_length=20, description="Телефон клиента")
    email: Optional[EmailStr] = Field(None, description="Email клиента")
    nearest_office: Optional[str] = Field(None, max_length=200, description="Ближайший офис")
    communication_time: Optional[str] = Field(None, max_length=100, description="Удобное время для связи")
    description: Optional[str] = Field(None, max_length=1000, description="Дополнительное описание")
    body: Optional[str] = Field(None, max_length=10000, description="HTML-контент заявки для рендеринга в письме")
    
    # НОВОЕ ПОЛЕ emailTo
    emailTo: Optional[EmailStr] = Field(None, description="Email адрес для отправки заявки")
    
    class Config:
        schema_extra = {
            "example": {
                "type": "на консультацию",
                "name": "Иван Иванов",
                "phone": "+7 (900) 123-45-67",
                "email": "ivan@example.com",
                "nearest_office": "Москва, Тверская 1",
                "communication_time": "с 10:00 до 18:00",
                "description": "Интересует отдых в Турции на 7 ночей",
                "body": "<div><h3>Детали заявки</h3><p>Клиент интересуется турами в <strong>Турцию</strong></p></div>",
                "emailTo": "manager@example.com"
            }
        }

        
class ApplicationRequestRaw(BaseModel):
    body: str = Field(..., description="HTML-контент заявки для рендеринга в письме")
    # НОВОЕ ПОЛЕ emailTo
    emailTo: Optional[EmailStr] = Field(None, description="Email адрес для отправки заявки")
    
    class Config:
        schema_extra = {
            "example": {
                "body": "<div><h3>Детали заявки</h3><p>Клиент интересуется турами в <strong>Турцию</strong></p></div>",
                "emailTo": "manager@example.com"
            }
        }

class ApplicationResponse(BaseModel):
    success: bool
    message: str
    application_id: Optional[str] = None

class Application(BaseModel):
    id: str
    type: str
    name: str
    phone: str
    email: Optional[str] = None
    nearest_office: Optional[str] = None
    communication_time: Optional[str] = None
    description: Optional[str] = None
    body: Optional[str] = None
    # НОВОЕ ПОЛЕ emailTo
    emailTo: Optional[str] = None
    created_at: datetime
    status: str = "new"
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

