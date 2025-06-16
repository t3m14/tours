import aiohttp
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import json

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class TourVisorClient:
    def __init__(self):
        self.base_url = settings.TOURVISOR_BASE_URL
        self.auth_params = {
            "authlogin": settings.TOURVISOR_AUTH_LOGIN,
            "authpass": settings.TOURVISOR_AUTH_PASS
        }
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Базовый метод для выполнения запросов к TourVisor API"""
        session = await self.get_session()
        full_params = {**self.auth_params, **params}
        
        try:
            url = f"{self.base_url}/{endpoint}"
            logger.debug(f"Запрос к TourVisor: {url} с параметрами: {full_params}")
            
            async with session.get(url, params=full_params) as response:
                response_text = await response.text()
                logger.debug(f"Ответ TourVisor (статус {response.status}): {response_text[:500]}...")
                
                response.raise_for_status()
                
                if params.get("format") == "json":
                    try:
                        return await response.json()
                    except Exception as e:
                        logger.error(f"Ошибка парсинга JSON: {e}, ответ: {response_text}")
                        raise
                else:
                    # Парсинг XML
                    return self._parse_xml(response_text)
                    
        except Exception as e:
            logger.error(f"Ошибка запроса к TourVisor {endpoint}: {e}")
            if hasattr(e, 'status') and e.status == 403:
                logger.error("Ошибка авторизации! Проверьте TOURVISOR_AUTH_LOGIN и TOURVISOR_AUTH_PASS")
            raise
    
    def _parse_xml(self, xml_content: str) -> Dict[str, Any]:
        """Парсинг XML ответа в словарь"""
        try:
            root = ET.fromstring(xml_content)
            return self._xml_to_dict(root)
        except ET.ParseError as e:
            logger.error(f"Ошибка парсинга XML: {e}")
            raise
    
    def _xml_to_dict(self, element) -> Dict[str, Any]:
        """Рекурсивное преобразование XML элемента в словарь"""
        result = {}
        
        # Атрибуты элемента
        if element.attrib:
            result.update(element.attrib)
        
        # Дочерние элементы
        children = list(element)
        if children:
            child_dict = {}
            for child in children:
                child_data = self._xml_to_dict(child)
                if child.tag in child_dict:
                    # Если элемент уже существует, создаем список
                    if not isinstance(child_dict[child.tag], list):
                        child_dict[child.tag] = [child_dict[child.tag]]
                    child_dict[child.tag].append(child_data)
                else:
                    child_dict[child.tag] = child_data
            result.update(child_dict)
        
        # Текстовое содержимое
        if element.text and element.text.strip():
            if children:
                result['text'] = element.text.strip()
            else:
                return element.text.strip()
        
        return result
    
    async def search_tours(self, search_params: Dict[str, Any]) -> str:
        """Запуск поиска туров. Возвращает request_id"""
        params = {
            "format": "xml",
            **search_params
        }
        
        session = await self.get_session()
        full_params = {**self.auth_params, **params}
        
        try:
            url = f"{self.base_url}/search.php"
            logger.debug(f"Запрос поиска туров: {url} с параметрами: {full_params}")
            
            async with session.get(url, params=full_params) as response:
                response_text = await response.text()
                logger.debug(f"Ответ поиска туров (статус {response.status}): {response_text}")
                
                response.raise_for_status()
                
                # Проверяем, является ли ответ простым числом (request_id)
                response_text = response_text.strip()
                if response_text.isdigit():
                    logger.info(f"✅ Получен request_id (число): {response_text}")
                    return response_text
                
                # Если не число, пытаемся парсить XML
                try:
                    result = self._parse_xml(response_text)
                    logger.debug(f"📄 Парсированный XML: {result}")
                    
                    # Ищем request_id в разных местах XML структуры
                    request_id = None
                    
                    # Вариант 1: прямо в корне
                    if isinstance(result, dict) and "requestid" in result:
                        request_id = result["requestid"]
                    
                    # Вариант 2: внутри тега result
                    elif isinstance(result, dict) and "result" in result:
                        result_data = result["result"]
                        if isinstance(result_data, dict) and "requestid" in result_data:
                            request_id = result_data["requestid"]
                    
                    # Вариант 3: поиск во всей структуре
                    if not request_id:
                        request_id = self._find_request_id_recursive(result)
                    
                    if request_id:
                        logger.info(f"✅ Получен request_id из XML: {request_id}")
                        return str(request_id)
                    else:
                        logger.error(f"❌ Не найден request_id в структуре: {result}")
                        raise ValueError("Не удалось получить request_id из XML")
                        
                except Exception as parse_error:
                    logger.error(f"❌ Ошибка парсинга XML: {parse_error}, ответ: {response_text}")
                    raise ValueError(f"Ошибка парсинга ответа: {parse_error}")
                    
        except Exception as e:
            logger.error(f"❌ Ошибка запроса поиска туров: {e}")
            raise
    
    def _find_request_id_recursive(self, data) -> Optional[str]:
        """Рекурсивный поиск request_id в структуре данных"""
        if isinstance(data, dict):
            # Прямой поиск ключа requestid
            if "requestid" in data:
                return str(data["requestid"])
            
            # Рекурсивный поиск во всех значениях
            for value in data.values():
                result = self._find_request_id_recursive(value)
                if result:
                    return result
        
        elif isinstance(data, list):
            # Поиск в списке
            for item in data:
                result = self._find_request_id_recursive(item)
                if result:
                    return result
        
        return None
    
    async def get_search_status(self, request_id: str) -> Dict[str, Any]:
        """Получение статуса поиска"""
        params = {
            "requestid": request_id,
            "type": "status",
            "format": "xml"
        }
        
        return await self._make_request("result.php", params)
    
    async def get_search_results(self, request_id: str, page: int = 1, onpage: int = 25) -> Dict[str, Any]:
        """Получение результатов поиска"""
        params = {
            "requestid": request_id,
            "type": "result",
            "page": page,
            "onpage": onpage,
            "format": "xml"
        }
        
        return await self._make_request("result.php", params)
    
    async def continue_search(self, request_id: str) -> Dict[str, Any]:
        """Продолжение поиска для получения больше результатов"""
        params = {
            "continue": request_id,
            "format": "xml"
        }
        
        return await self._make_request("search.php", params)
    
    async def get_hot_tours(self, city: int, items: int = 10, **filters) -> Dict[str, Any]:
        """Получение горящих туров"""
        params = {
            "city": city,
            "items": items,
            "format": "json",
            **filters
        }
        
        return await self._make_request("hottours.php", params)
    
    async def get_references(self, ref_type: str, **filters) -> Dict[str, Any]:
        """Получение справочников"""
        params = {
            "type": ref_type,
            "format": "json",
            **filters
        }
        
        return await self._make_request("list.php", params)
    
    async def get_hotel_info(self, hotel_code: str) -> Dict[str, Any]:
        """Получение информации об отеле"""
        params = {
            "hotelcode": hotel_code,
            "format": "json",
            "imgbig": 1,
            "reviews": 1
        }
        
        return await self._make_request("hotel.php", params)
    
    async def actualize_tour(self, tour_id: str, request_check: int = 0) -> Dict[str, Any]:
        """Актуализация тура"""
        params = {
            "tourid": tour_id,
            "request": request_check,
            "format": "json"
        }
        
        return await self._make_request("actualize.php", params)
    
    async def get_detailed_actualization(self, tour_id: str) -> Dict[str, Any]:
        """Детальная актуализация тура с информацией о рейсах"""
        params = {
            "tourid": tour_id,
            "format": "json"
        }
        
        return await self._make_request("actdetail.php", params)

# Синглтон клиента
tourvisor_client = TourVisorClient()