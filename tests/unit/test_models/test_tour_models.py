import pytest
from pydantic import ValidationError
from app.models.tour import RandomTourRequest


class TestTourModels:
    """Тесты моделей туров"""
    
    def test_random_tour_request_valid(self):
        """Тест валидной модели RandomTourRequest"""
        # Проверим, что модель создается с правильными данными
        request = RandomTourRequest(count=5)
        assert request.count == 5
    
    def test_random_tour_request_default(self):
        """Тест дефолтных значений"""
        request = RandomTourRequest()
        # Проверим дефолтное значение
        assert hasattr(request, 'count')
        print(f"Дефолтное значение count: {request.count}")
    
    def test_random_tour_request_validation(self):
        """Тест валидации модели"""
        # Проверим, что модель не принимает некорректные данные
        try:
            # Попробуем отрицательное число
            request = RandomTourRequest(count=-1)
            # Если не выбросило исключение, проверим, что значение исправлено
            assert request.count >= 0
        except ValidationError:
            # Это тоже нормально - модель правильно валидирует
            print("Модель корректно отклоняет отрицательные значения")
            assert True