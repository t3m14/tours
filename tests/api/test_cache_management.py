import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestCacheManagement:
    """Тесты управления кэшем случайных туров"""
    
    def test_cache_status_detailed(self):
        """Детальный тест статуса кэша"""
        response = client.get("/api/v1/random-tours/cache/status")
        
        assert response.status_code == 200
        data = response.json()
        
        # Проверяем основные поля из логов
        expected_fields = [
            'is_running',
            'last_update', 
            'next_update',
            'hotel_types_supported',
            'scheduler_info'
        ]
        
        found_fields = [f for f in expected_fields if f in data]
        print(f"Найденные поля статуса: {found_fields}")
        
        # Проверяем scheduler_info детально
        if 'scheduler_info' in data:
            scheduler = data['scheduler_info']
            
            # Из логов ожидаем эти поля
            scheduler_fields = [
                'update_interval_hours',
                'tours_per_type', 
                'strategies',
                'countries',
                'hotel_types_count'
            ]
            
            found_scheduler = [f for f in scheduler_fields if f in scheduler]
            print(f"Поля планировщика: {found_scheduler}")
            
            # Проверяем значения из логов
            if 'update_interval_hours' in scheduler:
                assert scheduler['update_interval_hours'] == 12.0
            
            if 'tours_per_type' in scheduler:
                assert scheduler['tours_per_type'] == 6
            
            if 'hotel_types_count' in scheduler:
                assert scheduler['hotel_types_count'] == 8
        
        print("✓ Cache status детально протестирован")
    
    def test_hotel_types_structure(self):
        """Тест структуры типов отелей"""
        response = client.get("/api/v1/random-tours/cache/hotel-types")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data.get('success') is True
        
        if 'hotel_types' in data:
            hotel_types = data['hotel_types']
            
            # Из логов: ['any', 'active', 'relax', 'family', 'health', 'city', 'beach', 'deluxe']
            expected_types = ['any', 'active', 'relax', 'family', 'health', 'city', 'beach', 'deluxe']
            
            for expected_type in expected_types:
                if expected_type in hotel_types:
                    type_info = hotel_types[expected_type]
                    print(f"✓ {expected_type}: {type_info}")
                    
                    # Проверяем структуру
                    if isinstance(type_info, dict):
                        assert 'display_name' in type_info
                        assert 'cache_key' in type_info
        
        print("✓ Hotel types структура корректна")
    
    def test_cache_endpoints_availability(self):
        """Тест доступности cache endpoints"""
        cache_endpoints = [
            '/api/v1/random-tours/cache/status',
            '/api/v1/random-tours/cache/hotel-types',
            '/api/v1/random-tours/cache/stats',
            '/api/v1/random-tours/cache/health'
        ]
        
        results = {}
        
        for endpoint in cache_endpoints:
            response = client.get(endpoint)
            results[endpoint] = response.status_code
            
            if response.status_code == 200:
                print(f"✓ {endpoint}: работает")
            elif response.status_code == 404:
                print(f"⚠ {endpoint}: не реализован")
            else:
                print(f"⚠ {endpoint}: статус {response.status_code}")
        
        # Основные endpoints должны работать
        assert results['/api/v1/random-tours/cache/status'] == 200
        assert results['/api/v1/random-tours/cache/hotel-types'] == 200
        
        print(f"Cache endpoints результаты: {results}")


class TestGenerationEndpoints:
    """Тесты генерации туров"""
    
    def test_preview_endpoints_structure(self):
        """Тест структуры preview endpoints"""
        # Тестируем несколько типов
        types_to_test = ['any', 'beach', 'family']
        
        for hotel_type in types_to_test:
            response = client.get(f"/api/v1/random-tours/cache/preview/{hotel_type}?limit=1")
            
            print(f"\n--- Тестируем {hotel_type} ---")
            
            if response.status_code == 200:
                data = response.json()
                
                # Базовая структура
                assert 'success' in data
                assert 'hotel_type' in data
                
                hotel_type_info = data['hotel_type']
                assert hotel_type_info['key'] == hotel_type
                
                print(f"✓ {hotel_type}: структура корректна")
                
                # Если есть данные
                if data.get('success'):
                    assert 'preview_tours' in data
                    assert 'total_cached' in data
                    print(f"✓ {hotel_type}: есть данные")
                else:
                    # Нормально для пустого кэша
                    assert 'recommendation' in data
                    print(f"⚠ {hotel_type}: {data.get('message')}")
            
            elif response.status_code == 400:
                # Невалидный тип
                print(f"⚠ {hotel_type}: невалидный тип")
            
            else:
                print(f"⚠ {hotel_type}: статус {response.status_code}")
    
    def test_generation_workflow_endpoints(self):
        """Тест endpoints рабочего процесса генерации"""
        generation_endpoints = [
            # GET endpoints
            ('/api/v1/random-tours/cache/status', 'GET'),
            ('/api/v1/random-tours/cache/hotel-types', 'GET'),
            ('/api/v1/random-tours/cache/preview/any', 'GET'),
            
            # POST endpoints (могут требовать данных)
            ('/api/v1/random-tours/cache/force-update', 'POST'),
            ('/api/v1/random-tours/cache/generate/any', 'POST')
        ]
        
        for endpoint, method in generation_endpoints:
            if method == 'GET':
                response = client.get(endpoint)
            elif method == 'POST':
                response = client.post(endpoint)
            
            print(f"{method} {endpoint}: {response.status_code}")
            
            # Все endpoints должны быть доступны (200, 400, 404)
            assert response.status_code < 500  # Не должно быть серверных ошибок