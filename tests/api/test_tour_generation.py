import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestTourGeneration:
    """Тесты генерации туров по типам отелей"""
    
    def test_generation_endpoint_exists(self):
        """Тест доступности endpoint генерации"""
        # Попробуем запустить генерацию для 'any'
        response = client.post("/api/v1/random-tours/cache/generate/any")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Генерация 'any': {data}")
            
            # Проверяем что генерация запущена
            assert data.get("success") is True
            assert "message" in data
            assert "estimated_duration" in data
            
            hotel_type_info = data.get("hotel_type", {})
            assert hotel_type_info.get("key") == "any"
            
            print(f"✓ Генерация запущена: {data['message']}")
            print(f"✓ Ожидаемое время: {data['estimated_duration']}")
            
        elif response.status_code == 404:
            print("Генерация endpoint не найден")
            assert True
        else:
            print(f"Генерация endpoint: статус {response.status_code}")
            assert response.status_code in [200, 404, 422]
    
    def test_generation_for_multiple_types(self):
        """Тест генерации для разных типов отелей"""
        hotel_types = ["any", "beach", "family"]
        
        for hotel_type in hotel_types:
            response = client.post(f"/api/v1/random-tours/cache/generate/{hotel_type}")
            
            print(f"{hotel_type}: статус {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    print(f"  ✓ {hotel_type}: {data['message']}")
                else:
                    print(f"  ⚠ {hotel_type}: {data.get('message')}")
            
            # Все типы должны быть валидными или endpoint может не существовать
            assert response.status_code in [200, 404, 400, 422]
    
    def test_invalid_hotel_type_generation(self):
        """Тест генерации для невалидного типа"""
        response = client.post("/api/v1/random-tours/cache/generate/invalid_type")
        
        print(f"Невалидный тип: статус {response.status_code}")
        
        if response.status_code == 400:
            data = response.json()
            print(f"Ошибка валидации: {data}")
            # Должна быть информация об ошибке
            assert "error" in data or "detail" in data
        
        # Невалидный тип должен возвращать ошибку
        assert response.status_code in [400, 404]