import json
import pickle
from typing import Any, Optional, Union
import redis.asyncio as redis

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class CacheService:
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
    
    async def get_client(self) -> redis.Redis:
        """Получение клиента Redis с переподключением при необходимости"""
        if self.redis_client is None:
            self.redis_client = redis.from_url(
                settings.REDIS_URL,
                decode_responses=False,  # Оставляем False для работы с pickle
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
        
        try:
            await self.redis_client.ping()
            return self.redis_client
        except Exception as e:
            logger.warning(f"Redis переподключение: {e}")
            self.redis_client = redis.from_url(
                settings.REDIS_URL,
                decode_responses=False,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            return self.redis_client
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Сохранение значения в кэш
        
        Args:
            key: Ключ для сохранения
            value: Значение для сохранения
            ttl: Время жизни в секундах (по умолчанию из настроек)
        
        Returns:
            True если успешно сохранено
        """
        try:
            client = await self.get_client()
            
            # Сериализуем значение
            if isinstance(value, (dict, list, tuple)):
                serialized_value = json.dumps(value, ensure_ascii=False, default=str)
                key_type = "json"
            else:
                serialized_value = pickle.dumps(value)
                key_type = "pickle"
            
            # Добавляем префикс типа для правильной десериализации
            final_value = f"{key_type}:{serialized_value.decode('utf-8') if isinstance(serialized_value, bytes) else serialized_value}"
            
            ttl = ttl or settings.CACHE_TTL
            await client.setex(key, ttl, final_value)
            
            logger.debug(f"Значение сохранено в кэш: {key} (TTL: {ttl}s)")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении в кэш {key}: {e}")
            return False
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Получение значения из кэша
        
        Args:
            key: Ключ для получения
        
        Returns:
            Значение из кэша или None если не найдено
        """
        try:
            client = await self.get_client()
            cached_value = await client.get(key)
            
            if cached_value is None:
                return None
            
            # Декодируем если bytes
            if isinstance(cached_value, bytes):
                cached_value = cached_value.decode('utf-8')
            
            # Определяем тип и десериализуем
            if cached_value.startswith("json:"):
                value_str = cached_value[5:]  # Убираем префикс "json:"
                return json.loads(value_str)
            elif cached_value.startswith("pickle:"):
                value_str = cached_value[7:]  # Убираем префикс "pickle:"
                return pickle.loads(value_str.encode('utf-8'))
            else:
                # Обратная совместимость - пытаемся как JSON
                try:
                    return json.loads(cached_value)
                except:
                    return cached_value
            
        except Exception as e:
            logger.error(f"Ошибка при получении из кэша {key}: {e}")
            return None
    
    async def delete(self, key: str) -> bool:
        """
        Удаление значения из кэша
        
        Args:
            key: Ключ для удаления
        
        Returns:
            True если успешно удалено
        """
        try:
            client = await self.get_client()
            result = await client.delete(key)
            
            logger.debug(f"Ключ удален из кэша: {key}")
            return bool(result)
            
        except Exception as e:
            logger.error(f"Ошибка при удалении из кэша {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """
        Проверка существования ключа в кэше
        
        Args:
            key: Ключ для проверки
        
        Returns:
            True если ключ существует
        """
        try:
            client = await self.get_client()
            result = await client.exists(key)
            return bool(result)
            
        except Exception as e:
            logger.error(f"Ошибка при проверке существования ключа {key}: {e}")
            return False
    
    async def get_keys_pattern(self, pattern: str) -> list[str]:
        """
        Получение списка ключей по паттерну
        
        Args:
            pattern: Паттерн для поиска (например, "search:*")
        
        Returns:
            Список найденных ключей
        """
        try:
            client = await self.get_client()
            keys = await client.keys(pattern)
            
            # Декодируем ключи если они в bytes
            if keys and isinstance(keys[0], bytes):
                keys = [key.decode('utf-8') for key in keys]
            
            return keys
            
        except Exception as e:
            logger.error(f"Ошибка при поиске ключей по паттерну {pattern}: {e}")
            return []
    
    async def set_multiple(self, data: dict[str, Any], ttl: Optional[int] = None) -> bool:
        """
        Сохранение нескольких значений одновременно
        
        Args:
            data: Словарь ключ-значение для сохранения
            ttl: Время жизни в секундах
        
        Returns:
            True если все значения сохранены успешно
        """
        try:
            success_count = 0
            for key, value in data.items():
                if await self.set(key, value, ttl):
                    success_count += 1
            
            return success_count == len(data)
            
        except Exception as e:
            logger.error(f"Ошибка при массовом сохранении в кэш: {e}")
            return False
    
    async def get_multiple(self, keys: list[str]) -> dict[str, Any]:
        """
        Получение нескольких значений одновременно
        
        Args:
            keys: Список ключей для получения
        
        Returns:
            Словарь ключ-значение с найденными данными
        """
        result = {}
        try:
            for key in keys:
                value = await self.get(key)
                if value is not None:
                    result[key] = value
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка при массовом получении из кэша: {e}")
            return result
    
    async def close(self):
        """Закрытие соединения с Redis"""
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None

# Создаем глобальный экземпляр сервиса
cache_service = CacheService()