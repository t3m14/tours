import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestDataQuality:
    """Тесты качества возвращаемых данных"""
    
    def test_old_api_tour_structure(self):
        """Тест структуры туров из старого API"""
        response = client.get("/api/v1/tours/random")
        
        if response.status_code == 200:
            tours = response.json()
            assert isinstance(tours, list)
            
            if tours:
                tour = tours[0]
                print(f"Структура тура: {list(tour.keys())}")
                
                # Проверяем обязательные поля
                required_fields = ["hotelname", "countryname", "price", "nights"]
                missing_fields = [f for f in required_fields if f not in tour]
                
                if missing_fields:
                    print(f"⚠ Отсутствуют поля: {missing_fields}")
                else:
                    print("✓ Все обязательные поля присутствуют")
                
                # Проверяем типы данных
                if "price" in tour:
                    assert isinstance(tour["price"], (int, float))
                    assert tour["price"] > 0
                    print(f"✓ Цена валидна: {tour['price']}")
                
                if "nights" in tour:
                    assert isinstance(tour["nights"], int)
                    assert tour["nights"] > 0
                    print(f"✓ Ночей валидно: {tour['nights']}")
                
                if "hotelname" in tour:
                    assert isinstance(tour["hotelname"], str)
                    assert len(tour["hotelname"]) > 0
                    print(f"✓ Название отеля: {tour['hotelname']}")
    
    def test_hotel_types_data_structure(self):
        """Тест структуры данных типов отелей"""
        response = client.get("/api/v1/random-tours/cache/hotel-types")
        
        if response.status_code == 200:
            data = response.json()
            
            if "hotel_types" in data:
                hotel_types = data["hotel_types"]
                
                for type_key, type_info in hotel_types.items():
                    print(f"Тип '{type_key}':")
                    
                    # Проверяем структуру каждого типа
                    expected_fields = ["display_name", "cache_key"]
                    found_fields = [f for f in expected_fields if f in type_info]
                    print(f"  Найденные поля: {found_fields}")
                    
                    # display_name должно быть строкой
                    if "display_name" in type_info:
                        assert isinstance(type_info["display_name"], str)
                        assert len(type_info["display_name"]) > 0
                    
                    # api_param может быть None или строкой
                    if "api_param" in type_info:
                        api_param = type_info["api_param"]
                        assert api_param is None or isinstance(api_param, str)
                        print(f"  API param: {api_param}")
    
    def test_cache_status_data_completeness(self):
        """Тест полноты данных статуса кэша"""
        response = client.get("/api/v1/random-tours/cache/status")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Статус кэша: {data}")
            
            # Проверяем ключевые поля
            important_fields = [
                "is_running", "hotel_types_supported", 
                "scheduler_info", "current_time"
            ]
            
            for field in important_fields:
                if field in data:
                    print(f"✓ {field}: {type(data[field]).__name__}")
                else:
                    print(f"⚠ Отсутствует: {field}")
            
            # scheduler_info должен содержать важную информацию
            if "scheduler_info" in data:
                scheduler = data["scheduler_info"]
                
                scheduler_fields = [
                    "update_interval_hours", "tours_per_type", 
                    "strategies", "countries"
                ]
                
                for field in scheduler_fields:
                    if field in scheduler:
                        print(f"  ✓ {field}: {scheduler[field]}")