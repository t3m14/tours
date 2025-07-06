# tests/api/test_tours_api.py

import pytest

def test_main_page(client):
    """Тест главной страницы"""
    response = client.get("/")
    assert response.status_code == 200
    
    # Проверим, что ответ содержит ожидаемую информацию
    data = response.json()
    assert "message" in data