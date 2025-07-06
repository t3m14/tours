from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

class TestHotelTypesAPI:
    def test_hotel_type_validation(self):
        """Тест валидации типов отелей"""
        # Валидный тип
        response = client.get("/api/v1/random-tours/cache/preview/any")
        valid_status = response.status_code
        
        # Невалидный тип  
        response = client.get("/api/v1/random-tours/cache/preview/invalid_type")
        invalid_status = response.status_code
        
        print(f"Валидный 'any': {valid_status}")
        print(f"Невалидный 'invalid_type': {invalid_status}")
        
        assert invalid_status in [400, 404]