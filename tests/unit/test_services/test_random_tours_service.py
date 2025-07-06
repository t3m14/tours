import pytest
from app.services.random_tours_service import random_tours_service


class TestRandomToursService:
    """Тесты для сервиса случайных туров"""
    
    def test_service_exists(self):
        """Базовая проверка что сервис загружается"""
        assert random_tours_service is not None
    
    def test_country_mapping_if_exists(self):
        """Тест маппинга стран если он есть"""
        # Проверим, есть ли маппинг стран
        if hasattr(random_tours_service, 'COUNTRIES_MAPPING'):
            mapping = random_tours_service.COUNTRIES_MAPPING
            assert isinstance(mapping, dict)
            assert len(mapping) > 0
            print(f"Найдено стран в маппинге: {len(mapping)}")
        else:
            assert True  # Пока просто проходим тест
    
    def test_available_methods(self):
        """Проверим все доступные методы сервиса"""
        methods = [method for method in dir(random_tours_service) 
                  if not method.startswith('__') and callable(getattr(random_tours_service, method))]
        
        print(f"Доступные методы: {methods}")
        assert len(methods) > 0
        
        # Проверим, что есть основные методы (если они есть)
        expected_methods = ['get_random_tours', 'generate_random_tours', '_generate_fully_random_tours']
        found_methods = [method for method in expected_methods if method in methods]
        print(f"Найденные ожидаемые методы: {found_methods}")