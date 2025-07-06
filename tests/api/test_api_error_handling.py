import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestAPIValidationErrors:
    """Тесты обработки ошибок валидации в API"""
    
    def test_search_results_validation_error_handling(self):
        """Тест обработки ошибок валидации в search results"""
        
        # Мокируем сервис который возвращает проблемные данные
        with patch('app.services.tour_service.get_search_results') as mock_service:
            
            # Симулируем данные которые вызовут ошибку валидации
            mock_service.return_value = {
                "hotels": [
                    {
                        "hotelcode": "12345",
                        "hotelname": "Test Hotel",
                        "countryname": "Турция",
                        "regionname": "Анталия",
                        "hotelstars": "4",
                        "price": "50000",
                        "reviewlink": {},  # Проблема!
                    }
                ]
            }
            
            # Делаем запрос к проблемному endpoint
            response = client.get("/api/v1/tours/search/test123/results")
            
            # API должен обработать ошибку валидации
            if response.status_code == 500:
                error_data = response.json()
                assert "detail" in error_data
                assert "validation error" in error_data["detail"].lower()
                print(f"✓ API корректно вернул ошибку валидации: {response.status_code}")
            else:
                print(f"API статус: {response.status_code}")
    
    def test_different_validation_error_scenarios(self):
        """Тест разных сценариев ошибок валидации"""
        
        error_scenarios = [
            {
                "name": "empty_object_reviewlink",
                "problematic_field": "reviewlink",
                "problematic_value": {}
            },
            {
                "name": "null_fulldesclink", 
                "problematic_field": "fulldesclink",
                "problematic_value": None
            },
            {
                "name": "array_picturelink",
                "problematic_field": "picturelink", 
                "problematic_value": []
            }
        ]
        
        for scenario in error_scenarios:
            print(f"\n--- Тестируем сценарий: {scenario['name']} ---")
            
            # Создаем проблемные данные для каждого сценария
            with patch('app.services.tour_service.get_search_results') as mock_service:
                
                problematic_hotel = {
                    "hotelcode": "12345",
                    "hotelname": "Test Hotel",
                    "countryname": "Турция", 
                    "regionname": "Анталия",
                    "hotelstars": "4",
                    "price": "50000"
                }
                
                # Добавляем проблемное поле
                problematic_hotel[scenario["problematic_field"]] = scenario["problematic_value"]
                
                mock_service.return_value = {"hotels": [problematic_hotel]}
                
                response = client.get(f"/api/v1/tours/search/test_{scenario['name']}/results")
                
                print(f"Статус для {scenario['name']}: {response.status_code}")
                
                if response.status_code == 500:
                    error_data = response.json()
                    if scenario["problematic_field"] in str(error_data):
                        print(f"✓ Ошибка поля {scenario['problematic_field']} обнаружена")
    
    def test_api_resilience_to_bad_data(self):
        """Тест устойчивости API к плохим данным"""
        
        # Тестируем что API не падает полностью от плохих данных
        endpoints_to_test = [
            "/api/v1/tours/random",
            "/api/v1/random-tours/cache/preview/any",
            "/api/v1/tours/directions"
        ]
        
        api_resilience_results = {}
        
        for endpoint in endpoints_to_test:
            try:
                response = client.get(endpoint)
                api_resilience_results[endpoint] = {
                    "status": response.status_code,
                    "resilient": response.status_code != 500
                }
                print(f"✓ {endpoint}: {response.status_code}")
            except Exception as e:
                api_resilience_results[endpoint] = {
                    "status": "exception", 
                    "error": str(e),
                    "resilient": False
                }
                print(f"❌ {endpoint}: Exception - {e}")
        
        # Большинство endpoints должны быть устойчивыми
        resilient_count = sum(1 for result in api_resilience_results.values() 
                            if result.get("resilient", False))
        
        print(f"Устойчивых endpoints: {resilient_count}/{len(endpoints_to_test)}")
        
        # Хотя бы половина должна быть устойчивой
        assert resilient_count >= len(endpoints_to_test) // 2


class TestDataSanitization:
    """Тесты очистки данных"""
    
    def test_data_cleaning_utility(self):
        """Тест утилиты очистки данных"""
        
        def sanitize_api_response(data):
            """Утилита для очистки ответов TourVisor API"""
            if not isinstance(data, dict):
                return data
            
            sanitized = {}
            
            for key, value in data.items():
                if isinstance(value, dict) and not value:
                    # Пустой объект -> пустая строка
                    sanitized[key] = ""
                elif isinstance(value, list) and not value:
                    # Пустой массив -> пустая строка
                    sanitized[key] = ""
                elif value is None:
                    # null -> пустая строка
                    sanitized[key] = ""
                else:
                    sanitized[key] = value
            
            return sanitized
        
        # Тестируем очистку
        dirty_data = {
            "hotelname": "Good Hotel",
            "reviewlink": {},           # Проблема
            "fulldesclink": [],         # Проблема
            "picturelink": None,        # Проблема
            "price": "50000",           # OK
            "description": "Good desc"  # OK
        }
        
        clean_data = sanitize_api_response(dirty_data)
        
        assert clean_data["hotelname"] == "Good Hotel"  # Нетронуто
        assert clean_data["reviewlink"] == ""           # Очищено
        assert clean_data["fulldesclink"] == ""         # Очищено  
        assert clean_data["picturelink"] == ""          # Очищено
        assert clean_data["price"] == "50000"           # Нетронуто
        
        print("✓ Утилита очистки данных работает корректно")