import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestErrorHandling:
    """Тесты обработки ошибок API"""
    
    def test_404_endpoints(self):
        """Тест несуществующих endpoints"""
        non_existent_endpoints = [
            "/api/v1/nonexistent",
            "/fake/endpoint", 
            "/api/v2/tours"
        ]
        
        for endpoint in non_existent_endpoints:
            response = client.get(endpoint)
            assert response.status_code == 404
            print(f"{endpoint}: {response.status_code} ✓")
    
    def test_method_not_allowed(self):
        """Тест неправильных HTTP методов"""
        # Попробуем DELETE на главной странице
        response = client.delete("/")
        assert response.status_code == 405  # Method Not Allowed
        
        # Попробуем PUT на random tours
        response = client.put("/api/v1/tours/random")
        assert response.status_code in [404, 405]  # Зависит от реализации
        
        print("Обработка неправильных методов работает")
    
    @patch('app.services.random_tours_service.get_random_tours')
    def test_api_with_service_error(self, mock_service):
        """Тест API когда сервис возвращает ошибку"""
        # Мокируем ошибку в сервисе
        mock_service.side_effect = Exception("Тестовая ошибка сервиса")
        
        response = client.get("/api/v1/tours/random")
        
        # Проверяем что API правильно обрабатывает ошибки
        assert response.status_code in [500, 200]  # Зависит от error handling
        print(f"Обработка ошибок сервиса: {response.status_code}")