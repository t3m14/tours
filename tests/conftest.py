"""
Настройки тестов с моками для скорости
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """Быстрый клиент для API тестов"""
    return TestClient(app)


@pytest.fixture 
def mock_redis():
    """Мок Redis для быстрых тестов"""
    mock = MagicMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.exists = AsyncMock(return_value=False)
    return mock


@pytest.fixture
def mock_tourvisor_client():
    """Мок TourVisor client"""
    mock = MagicMock()
    mock.search_tours = AsyncMock(return_value={"result": []})
    mock.get_hot_tours = AsyncMock(return_value=[])
    mock.get_references = AsyncMock(return_value={})
    return mock


@pytest.fixture(autouse=True)
def mock_external_services(mock_redis, mock_tourvisor_client):
    """Автоматически мокает внешние сервисы во всех тестах"""
    with pytest.MonkeyPatch.context() as mp:
        # Мокаем Redis
        mp.setattr("app.services.cache_service.redis", mock_redis)
        
        # Мокаем TourVisor
        mp.setattr("app.core.tourvisor_client", mock_tourvisor_client)
        
        yield