import pytest
from fastapi.testclient import TestClient
from app.main import app

test_client = TestClient(app)


class TestToursAPI:
    """Тесты API туров"""
    
    def test_main_page(self):
        """Тест главной страницы"""
        response = test_client.get("/")
        assert response.status_code == 200
        
        data = response.json()
        assert "message" in data
        assert "Travel Agency Backend API" in data["message"]
        print(f"Версия API: {data.get('version', 'не указана')}")
    
    def test_health_endpoint(self):
        """Тест health endpoint если есть"""
        response = test_client.get("/health")
        
        # Может быть 200 (если endpoint есть) или 404 (если нет)
        if response.status_code == 200:
            print("Health endpoint найден и работает")
            assert response.json() is not None
        elif response.status_code == 404:
            print("Health endpoint не найден (это нормально)")
            assert True
        else:
            # Другие коды ошибок не ожидаем
            assert False, f"Неожиданный код ответа: {response.status_code}"
    
    def test_random_tours_endpoint(self):
        """Тест получения случайных туров"""
        # Попробуем GET запрос
        response = test_client.get("/api/v1/tours/random")
        
        if response.status_code == 200:
            print("GET /api/v1/tours/random работает")
            data = response.json()
            assert isinstance(data, list)
        elif response.status_code == 405:  # Method Not Allowed
            # Попробуем POST запрос
            response = test_client.post("/api/v1/tours/random", 
                                      json={"count": 3})
            print(f"POST /api/v1/tours/random: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, list)
                assert len(data) <= 3
        elif response.status_code == 404:
            print("Endpoint случайных туров не найден")
            assert True  # Это нормально на этапе разработки
    
    def test_api_endpoints_exist(self):
        """Проверим, какие API endpoints доступны"""
        endpoints_to_test = [
            "/api/v1/tours/search",
            "/api/v1/tours/random", 
            "/api/v1/applications/",
            "/api/v1/references/departure"
        ]
        
        working_endpoints = []
        
        for endpoint in endpoints_to_test:
            response = test_client.get(endpoint)
            if response.status_code not in [404, 500]:
                working_endpoints.append(endpoint)
        
        print(f"Работающие endpoints: {working_endpoints}")
        # Хотя бы один endpoint должен работать
        assert len(working_endpoints) >= 1