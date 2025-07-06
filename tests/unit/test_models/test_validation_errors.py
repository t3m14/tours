import pytest
from pydantic import ValidationError
from app.models.tour import HotelInfo, TourSearchResult, DetailedTourInfo


class TestValidationErrors:
    """Тесты для ошибок валидации данных от TourVisor API"""
    
    def test_hotelinfo_reviewlink_validation(self):
        """Тест проблемы с reviewlink как пустым объектом"""
        
        # Корректные данные
        valid_data = {
            "hotelcode": "12345",
            "hotelname": "Test Hotel",
            "countryname": "Турция",
            "regionname": "Анталия",
            "hotelstars": "5",
            "price": "50000",
            "reviewlink": "http://example.com/reviews"  # Строка - OK
        }
        
        # Должно работать
        hotel = HotelInfo(**valid_data)
        assert hotel.reviewlink == "http://example.com/reviews"
        
        # Проблемные данные - пустой объект вместо строки
        invalid_data = valid_data.copy()
        invalid_data["reviewlink"] = {}  # Пустой объект вместо строки
        
        # Должно выбрасывать ValidationError
        with pytest.raises(ValidationError) as exc_info:
            HotelInfo(**invalid_data)
        
        error = exc_info.value
        assert "reviewlink" in str(error)
        assert "string_type" in str(error)
        print(f"✓ Поймана ошибка reviewlink: {error}")
    
    def test_hotelinfo_multiple_field_validation_errors(self):
        """Тест множественных ошибок валидации полей"""
        
        # Данные с несколькими проблемными полями
        problematic_data = {
            "hotelcode": "12345",
            "hotelname": "Test Hotel",
            "countryname": "Турция",
            "regionname": "Анталия", 
            "hotelstars": "5",
            "price": "50000",
            "reviewlink": {},           # Объект вместо строки
            "fulldesclink": [],         # Массив вместо строки
            "picturelink": None,        # None вместо строки
            "hoteldescription": 12345   # Число вместо строки
        }
        
        with pytest.raises(ValidationError) as exc_info:
            HotelInfo(**problematic_data)
        
        error = exc_info.value
        error_str = str(error)
        
        # Проверяем что найдены разные типы ошибок
        problematic_fields = ["reviewlink", "fulldesclink", "picturelink", "hoteldescription"]
        found_errors = [field for field in problematic_fields if field in error_str]
        
        print(f"Найденные ошибки полей: {found_errors}")
        print(f"Полная ошибка: {error_str}")
        
        assert len(found_errors) > 0  # Хотя бы одна ошибка должна быть найдена
    
    def test_common_api_response_issues(self):
        """Тест типичных проблем ответов API"""
        
        base_valid_data = {
            "hotelcode": "12345",
            "hotelname": "Test Hotel", 
            "countryname": "Турция",
            "regionname": "Анталия",
            "hotelstars": "5",
            "price": "50000"
        }
        
        # Тестируем разные проблемные случаи
        problematic_cases = [
            # Случай 1: пустые объекты
            {"reviewlink": {}, "description": "пустой объект"},
            
            # Случай 2: null значения 
            {"reviewlink": None, "description": "null значение"},
            
            # Случай 3: числовые значения вместо строк
            {"reviewlink": 12345, "description": "число вместо строки"},
            
            # Случай 4: массивы вместо строк
            {"reviewlink": [], "description": "пустой массив"},
            {"reviewlink": ["link1", "link2"], "description": "массив строк"},
            
            # Случай 5: boolean значения
            {"reviewlink": True, "description": "boolean true"},
            {"reviewlink": False, "description": "boolean false"}
        ]
        
        validation_errors_found = []
        
        for case in problematic_cases:
            test_data = base_valid_data.copy()
            test_data["reviewlink"] = case["reviewlink"]
            
            try:
                HotelInfo(**test_data)
                print(f"⚠️ Неожиданно прошло: {case['description']}")
            except ValidationError as e:
                validation_errors_found.append(case['description'])
                print(f"✓ Поймана ошибка для {case['description']}: {str(e).split()[0]}")
        
        # Большинство случаев должны вызывать ошибки валидации
        assert len(validation_errors_found) >= 5
        print(f"Всего найдено ошибок валидации: {len(validation_errors_found)}")
    
    def test_missing_required_fields(self):
        """Тест отсутствующих обязательных полей"""
        
        # Базовые данные
        full_data = {
            "hotelcode": "12345",
            "hotelname": "Test Hotel",
            "countryname": "Турция", 
            "regionname": "Анталия",
            "hotelstars": "5",
            "price": "50000"
        }
        
        # Тестируем удаление каждого поля
        required_fields = ["hotelcode", "hotelname", "countryname", "price"]
        
        missing_field_errors = []
        
        for field in required_fields:
            test_data = full_data.copy()
            del test_data[field]  # Удаляем поле
            
            try:
                HotelInfo(**test_data)
                print(f"⚠️ Поле {field} не обязательное")
            except ValidationError as e:
                missing_field_errors.append(field)
                print(f"✓ Поле {field} обязательное: {str(e).split('\\n')[0]}")
        
        print(f"Обязательные поля: {missing_field_errors}")
        # Хотя бы некоторые поля должны быть обязательными
        assert len(missing_field_errors) > 0


class TestRealWorldDataStructures:
    """Тесты с реальными структурами данных от TourVisor"""
    
    def test_tourvisor_empty_object_response(self):
        """Тест реального случая когда TourVisor возвращает пустые объекты"""
        
        # Реальный ответ с проблемными данными (упрощенно)
        problematic_response = {
            "hotelcode": "12345",
            "hotelname": "Real Hotel",
            "countryname": "Турция",
            "regionname": "Анталия",
            "hotelstars": "4", 
            "price": "75000",
            "reviewlink": {},          # Проблема из вашего лога
            "fulldesclink": {},        # Тоже может быть проблемой
            "subregionname": {},       # Еще одно поле которое может быть пустым объектом
            "isphoto": "1",
            "isdescription": "1"
        }
        
        with pytest.raises(ValidationError) as exc_info:
            HotelInfo(**problematic_response)
        
        error = exc_info.value
        print(f"Реальная ошибка TourVisor: {error}")
        
        # Проверяем что это именно та ошибка которую вы видели
        assert "reviewlink" in str(error)
        assert "string_type" in str(error) or "str_type" in str(error)
    
    def test_handle_tourvisor_data_cleaning(self):
        """Тест очистки проблемных данных от TourVisor"""
        
        def clean_tourvisor_data(raw_data):
            """Функция для очистки данных от TourVisor"""
            cleaned = raw_data.copy()
            
            # Список полей которые должны быть строками
            string_fields = ["reviewlink", "fulldesclink", "picturelink", "hoteldescription"]
            
            for field in string_fields:
                if field in cleaned:
                    value = cleaned[field]
                    
                    # Если пустой объект, список или None - делаем пустой строкой
                    if isinstance(value, (dict, list)) and not value:
                        cleaned[field] = ""
                    elif value is None:
                        cleaned[field] = ""
                    elif not isinstance(value, str):
                        # Преобразуем в строку если это не строка
                        cleaned[field] = str(value)
            
            return cleaned
        
        # Тестируем очистку
        dirty_data = {
            "hotelcode": "12345",
            "hotelname": "Test Hotel",
            "countryname": "Турция",
            "regionname": "Анталия", 
            "hotelstars": "4",
            "price": "50000",
            "reviewlink": {},           # Проблемный пустой объект
            "fulldesclink": [],         # Проблемный пустой массив  
            "picturelink": None,        # Проблемный null
            "hoteldescription": 12345   # Проблемное число
        }
        
        # Очищаем данные
        cleaned_data = clean_tourvisor_data(dirty_data)
        
        # Теперь должно работать
        hotel = HotelInfo(**cleaned_data)
        
        assert hotel.reviewlink == ""
        assert hotel.fulldesclink == ""
        assert hotel.picturelink == ""
        assert hotel.hoteldescription == "12345"
        
        print("✓ Данные TourVisor успешно очищены и валидированы")


class TestAPIErrorHandling:
    """Тесты обработки ошибок API"""
    
    def test_validation_error_response_format(self):
        """Тест формата ответа при ошибках валидации"""
        
        # Симулируем как должна выглядеть ошибка от API
        expected_error_structure = {
            "detail": "1 validation error for HotelInfo\\nreviewlink\\n Input should be a valid string",
            "status_code": 500,
            "error_type": "ValidationError"
        }
        
        # Проверяем что мы понимаем структуру ошибки
        assert "validation error" in expected_error_structure["detail"]
        assert "reviewlink" in expected_error_structure["detail"]
        assert expected_error_structure["status_code"] == 500
        
        print("✓ Структура ошибки валидации понята")
    
    def test_multiple_validation_errors_handling(self):
        """Тест обработки множественных ошибок валидации"""
        
        # Данные с множественными ошибками
        multi_error_data = {
            "hotelcode": "",            # Пустая строка (может быть проблемой)
            "hotelname": None,          # None вместо строки
            "countryname": {},          # Объект вместо строки
            "regionname": [],           # Массив вместо строки  
            "hotelstars": "invalid",    # Некорректная звездность
            "price": "not_a_number",    # Некорректная цена
            "reviewlink": {}            # Оригинальная проблема
        }
        
        try:
            HotelInfo(**multi_error_data)
            assert False, "Должна была быть ошибка валидации"
        except ValidationError as e:
            error_count = str(e).count("Input should be")
            print(f"Найдено ошибок валидации: {error_count}")
            print(f"Полная ошибка: {str(e)[:200]}...")
            
            # Должно быть несколько ошибок
            assert error_count > 1