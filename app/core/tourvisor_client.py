import aiohttp
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET
import json
import re

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
        self.request_timeout = 30  # Увеличиваем таймаут запросов
    
    async def get_session(self):
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.request_timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session
    
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def _make_request_with_retry(self, endpoint: str, params: Dict[str, Any], max_retries: int = 3) -> Dict[str, Any]:
        """Выполнение запроса с повторными попытками"""
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return await self._make_request(endpoint, params)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Экспоненциальная задержка
                    logger.warning(f"⚠️ Попытка {attempt + 1} неудачна, ждем {wait_time}с: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"❌ Все {max_retries} попыток исчерпаны")
        
        raise last_error
    
    async def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Базовый метод для выполнения запросов к TourVisor API"""
        session = await self.get_session()
        full_params = {**self.auth_params, **params}
        
        try:
            url = f"{self.base_url}/{endpoint}"
            
            # Логируем параметры без пароля
            safe_params = {k: v for k, v in full_params.items() if k != "authpass"}
            logger.debug(f"🌐 Запрос к TourVisor: {url}")
            logger.debug(f"📋 Параметры: {safe_params}")
            
            async with session.get(url, params=full_params) as response:
                response_text = await response.text()
                
                # Проверяем статус ответа
                if response.status != 200:
                    logger.error(f"❌ HTTP {response.status}: {response_text[:200]}")
                    response.raise_for_status()
                
                logger.debug(f"✅ Ответ получен (длина: {len(response_text)} символов)")
                
                # Проверяем на ошибки в тексте ответа
                if "error" in response_text.lower() or "ошибка" in response_text.lower():
                    logger.warning(f"⚠️ Возможная ошибка в ответе: {response_text[:200]}")
                
                if params.get("format") == "json":
                    try:
                        return await response.json()
                    except Exception as e:
                        logger.error(f"❌ Ошибка парсинга JSON: {e}")
                        logger.error(f"📄 Ответ: {response_text[:500]}")
                        raise
                else:
                    # Парсинг XML
                    return self._parse_xml(response_text)
                    
        except aiohttp.ClientTimeout:
            logger.error(f"⏰ Таймаут запроса к {endpoint} ({self.request_timeout}с)")
            raise
        except aiohttp.ClientError as e:
            logger.error(f"🌐 Сетевая ошибка при запросе к {endpoint}: {e}")
            raise
        except Exception as e:
            logger.error(f"💥 Неожиданная ошибка при запросе к {endpoint}: {e}")
            if hasattr(e, 'status') and e.status == 403:
                logger.error("🔐 Ошибка авторизации! Проверьте TOURVISOR_AUTH_LOGIN и TOURVISOR_AUTH_PASS")
            raise
    
    def _parse_xml(self, xml_content: str) -> Dict[str, Any]:
        """Парсинг XML ответа в словарь"""
        try:
            # Очищаем XML от возможных проблемных символов
            xml_content = xml_content.strip()
            if not xml_content:
                logger.warning("⚠️ Пустой XML ответ")
                return {}
            
            root = ET.fromstring(xml_content)
            result = self._xml_to_dict(root)
            
            logger.debug(f"📊 XML парсинг успешен, ключи верхнего уровня: {list(result.keys())}")
            return result
            
        except ET.ParseError as e:
            logger.error(f"❌ Ошибка парсинга XML: {e}")
            logger.error(f"📄 XML содержимое: {xml_content[:500]}")
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
        """Запуск поиска туров с детальной диагностикой. Возвращает request_id"""
        
        # Проверяем обязательные параметры
        required_params = ["departure", "country"]
        for param in required_params:
            if param not in search_params:
                raise ValueError(f"Отсутствует обязательный параметр: {param}")
        
        # Добавляем дефолтные параметры если не указаны
        default_params = {
            "format": "xml",
            "adults": 2,
            "child": 0,
            "nightsfrom": 7,
            "nightsto": 10
        }
        
        params = {**default_params, **search_params}
        
        # Валидируем и форматируем параметры
        params = self._validate_search_params(params)
        
        session = await self.get_session()
        full_params = {**self.auth_params, **params}
        
        try:
            url = f"{self.base_url}/search.php"
            
            # Безопасные параметры для логирования
            safe_params = {k: v for k, v in full_params.items() if k != "authpass"}
            logger.info(f"🔍 Запуск поиска туров: {safe_params}")
            
            async with session.get(url, params=full_params) as response:
                response_text = await response.text()
                
                logger.info(f"📡 HTTP статус: {response.status}")
                logger.info(f"📄 Длина ответа: {len(response_text)} символов")
                logger.debug(f"📄 Первые 500 символов ответа: {response_text[:500]}")
                
                if response.status != 200:
                    logger.error(f"❌ HTTP {response.status} при поиске")
                    logger.error(f"📄 Полный ответ: {response_text}")
                    raise ValueError(f"HTTP {response.status}: {response_text}")
                
                # Детальный анализ ответа
                analysis_result = self._analyze_search_response(response_text)
                
                if analysis_result["request_id"]:
                    logger.info(f"✅ Получен request_id: {analysis_result['request_id']}")
                    return analysis_result["request_id"]
                else:
                    logger.error(f"❌ Не удалось извлечь request_id")
                    logger.error(f"📊 Анализ ответа: {analysis_result}")
                    raise ValueError(f"Не удалось получить request_id: {analysis_result['error']}")
                    
        except Exception as e:
            logger.error(f"💥 Ошибка запуска поиска туров: {e}")
            # Дополнительная диагностика
            await self._diagnose_search_failure(params, str(e))
            raise
    
    def _validate_search_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Валидация и нормализация параметров поиска"""
        validated_params = params.copy()
        
        # Проверяем и форматируем даты
        if not validated_params.get("datefrom"):
            tomorrow = datetime.now() + timedelta(days=7)
            validated_params["datefrom"] = tomorrow.strftime("%d.%m.%Y")
            
        if not validated_params.get("dateto"):
            date_to = datetime.now() + timedelta(days=14)
            validated_params["dateto"] = date_to.strftime("%d.%m.%Y")
        
        # Проверяем корректность дат
        try:
            date_from = datetime.strptime(validated_params["datefrom"], "%d.%m.%Y")
            date_to = datetime.strptime(validated_params["dateto"], "%d.%m.%Y")
            
            if date_from >= date_to:
                logger.warning("⚠️ Дата от >= даты до, корректируем")
                validated_params["dateto"] = (date_from + timedelta(days=7)).strftime("%d.%m.%Y")
                
        except ValueError as e:
            logger.warning(f"⚠️ Некорректный формат даты: {e}")
            # Устанавливаем дефолтные даты
            validated_params["datefrom"] = (datetime.now() + timedelta(days=7)).strftime("%d.%m.%Y")
            validated_params["dateto"] = (datetime.now() + timedelta(days=14)).strftime("%d.%m.%Y")
        
        # Валидируем числовые параметры
        int_params = ["departure", "country", "adults", "child", "nightsfrom", "nightsto"]
        for param in int_params:
            if param in validated_params:
                try:
                    value = validated_params[param]
                    # Безопасное преобразование в int
                    if isinstance(value, str):
                        if value.strip():  # Проверяем, что строка не пустая
                            validated_params[param] = int(value.strip())
                        else:
                            logger.warning(f"⚠️ Пустое значение для {param}, удаляем")
                            del validated_params[param]
                    elif isinstance(value, (int, float)):
                        validated_params[param] = int(value)
                    else:
                        logger.warning(f"⚠️ Неподдерживаемый тип для {param}: {type(value)}")
                        del validated_params[param]
                except (ValueError, TypeError) as e:
                    logger.warning(f"⚠️ Некорректное значение {param}: {validated_params[param]} -> {e}")
                    # Удаляем некорректные значения
                    del validated_params[param]
        
        logger.debug(f"✅ Валидированные параметры: {validated_params}")
        return validated_params
    
    def _analyze_search_response(self, response_text: str) -> Dict[str, Any]:
        """Детальный анализ ответа поиска для извлечения request_id"""
        
        analysis = {
            "request_id": None,
            "response_type": "unknown",
            "error": None,
            "raw_length": len(response_text),
            "contains_error": False
        }
        
        try:
            # Очищаем ответ
            response_text = response_text.strip()
            
            if not response_text:
                analysis["error"] = "Пустой ответ от сервера"
                return analysis
            
            # Проверяем на ошибки в тексте
            error_indicators = ["error", "ошибка", "exception", "invalid", "forbidden", "unauthorized"]
            response_lower = response_text.lower()
            
            for indicator in error_indicators:
                if indicator in response_lower:
                    analysis["contains_error"] = True
                    analysis["error"] = f"Обнаружен индикатор ошибки: {indicator}"
                    logger.warning(f"⚠️ {analysis['error']} в ответе: {response_text[:200]}")
            
            # Случай 1: Простое число (традиционный request_id)
            if response_text.isdigit():
                analysis["request_id"] = response_text
                analysis["response_type"] = "simple_number"
                return analysis
            
            # Случай 2: XML ответ
            if response_text.startswith('<'):
                analysis["response_type"] = "xml"
                try:
                    parsed_xml = self._parse_xml(response_text)
                    analysis["request_id"] = self._find_request_id_recursive(parsed_xml)
                    
                    if not analysis["request_id"]:
                        analysis["error"] = "request_id не найден в XML"
                        analysis["xml_structure"] = self._describe_xml_structure(parsed_xml)
                    
                except Exception as xml_error:
                    analysis["error"] = f"Ошибка парсинга XML: {xml_error}"
                    analysis["xml_preview"] = response_text[:200]
                
                return analysis
            
            # Случай 3: JSON ответ
            if response_text.startswith('{') or response_text.startswith('['):
                analysis["response_type"] = "json"
                try:
                    parsed_json = json.loads(response_text)
                    analysis["request_id"] = self._find_request_id_in_json(parsed_json)
                    
                    if not analysis["request_id"]:
                        analysis["error"] = "request_id не найден в JSON"
                        analysis["json_keys"] = list(parsed_json.keys()) if isinstance(parsed_json, dict) else "not_dict"
                    
                except Exception as json_error:
                    analysis["error"] = f"Ошибка парсинга JSON: {json_error}"
                    analysis["json_preview"] = response_text[:200]
                
                return analysis
            
            # Случай 4: Текстовый ответ с request_id
            # Ищем числа в тексте
            numbers = re.findall(r'\d{8,}', response_text)  # Ищем длинные числа (8+ цифр)
            
            if numbers:
                analysis["request_id"] = numbers[0]
                analysis["response_type"] = "text_with_numbers"
                return analysis
            
            # Случай 5: Неизвестный формат
            analysis["response_type"] = "unknown_format"
            analysis["error"] = f"Неизвестный формат ответа: {response_text[:100]}"
            
        except Exception as e:
            analysis["error"] = f"Ошибка анализа ответа: {e}"
        
        return analysis
    
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
    
    def _find_request_id_in_json(self, json_data: Any) -> Optional[str]:
        """Поиск request_id в JSON данных"""
        if isinstance(json_data, dict):
            # Прямой поиск
            for key in ["requestid", "request_id", "id", "searchId"]:
                if key in json_data:
                    return str(json_data[key])
            
            # Рекурсивный поиск
            for value in json_data.values():
                result = self._find_request_id_in_json(value)
                if result:
                    return result
        
        elif isinstance(json_data, list):
            for item in json_data:
                result = self._find_request_id_in_json(item)
                if result:
                    return result
        
        return None
    
    def _describe_xml_structure(self, parsed_xml: Dict[str, Any]) -> Dict[str, Any]:
        """Описание структуры XML для диагностики"""
        try:
            return {
                "top_level_keys": list(parsed_xml.keys()) if isinstance(parsed_xml, dict) else "not_dict",
                "type": type(parsed_xml).__name__,
                "sample_content": str(parsed_xml)[:200] if parsed_xml else "empty"
            }
        except:
            return {"error": "cannot_describe"}
    
    async def _diagnose_search_failure(self, params: Dict[str, Any], error_message: str):
        """Диагностика неудачного поиска"""
        logger.error("🔍 ДИАГНОСТИКА НЕУДАЧНОГО ПОИСКА:")
        logger.error(f"  📋 Параметры: {params}")
        logger.error(f"  💥 Ошибка: {error_message}")
        
        # Проверяем базовое подключение
        try:
            test_result = await self.test_connection()
            logger.error(f"  🌐 Тест подключения: {test_result}")
        except Exception as conn_error:
            logger.error(f"  🌐 Ошибка подключения: {conn_error}")
        
        # Проверяем простейший справочник
        try:
            simple_ref = await self.get_references("departure")
            ref_status = "OK" if simple_ref else "Empty"
            logger.error(f"  📚 Тест справочника: {ref_status}")
        except Exception as ref_error:
            logger.error(f"  📚 Ошибка справочника: {ref_error}")
    
    async def get_search_status(self, request_id: str) -> Dict[str, Any]:
        """Получение статуса поиска с улучшенной обработкой разных форматов ответов"""
        try:
            params = {
                "requestid": request_id,
                "type": "status",
                "format": "xml"
            }
            
            logger.debug(f"📊 Запрос статуса поиска {request_id}")
            result = await self._make_request("result.php", params)
            
            # Логируем сырой ответ для диагностики
            logger.debug(f"🔍 Сырой ответ статуса: {result}")
            
            # Нормализуем структуру ответа
            normalized_result = self._normalize_status_response(result, request_id)
            
            # Диагностика структуры ответа
            self._diagnose_status_response(normalized_result, request_id)
            
            return normalized_result
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статуса {request_id}: {e.with_traceback}")
            raise
    
    def _normalize_status_response(self, result: Dict[str, Any], request_id: str) -> Dict[str, Any]:
        """Нормализация ответа статуса в ожидаемый формат"""
        
        # Если уже есть правильная структура
        if "data" in result and "status" in result["data"]:
            return result
        
        # Вариант 1: статус находится в корне
        if "status" in result:
            logger.info(f"🔧 Нормализация: статус в корне для {request_id}")
            return {
                "data": {
                    "status": result["status"]
                }
            }
        
        # Вариант 2: данные статуса прямо в корне (без обертки)
        status_fields = ["state", "hotelsfound", "toursfound", "minprice", "progress", "timepassed"]
        if any(field in result for field in status_fields):
            logger.info(f"🔧 Нормализация: статус прямо в корне для {request_id}")
            
            # Собираем данные статуса с безопасным преобразованием типов
            status_data = {}
            for field in status_fields:
                if field in result:
                    value = result[field]
                    try:
                        # Безопасное преобразование значений
                        if field in ["hotelsfound", "toursfound", "progress", "timepassed"]:
                            # Целые числа
                            if isinstance(value, str):
                                status_data[field] = int(value) if value.strip() else 0
                            elif isinstance(value, (int, float)):
                                status_data[field] = int(value)
                            else:
                                status_data[field] = 0
                        elif field == "minprice":
                            # Дробные числа
                            if isinstance(value, str):
                                status_data[field] = float(value) if value.strip() else None
                            elif isinstance(value, (int, float)):
                                status_data[field] = float(value)
                            else:
                                status_data[field] = None
                        else:  # state
                            status_data[field] = str(value) if value is not None else ""
                    except (ValueError, TypeError) as e:
                        logger.warning(f"⚠️ Ошибка преобразования {field}: {value} -> {e}")
                        # Значения по умолчанию
                        if field in ["hotelsfound", "toursfound", "progress", "timepassed"]:
                            status_data[field] = 0
                        elif field == "minprice":
                            status_data[field] = None
                        else:
                            status_data[field] = ""
            
            return {
                "data": {
                    "status": status_data
                }
            }
        
        # Вариант 3: XML структура с другими тегами
        # Ищем поля статуса в любом месте структуры
        status_data = self._extract_status_from_structure(result)
        
        if status_data:
            logger.info(f"🔧 Нормализация: извлечен статус из структуры для {request_id}")
            return {
                "data": {
                    "status": status_data
                }
            }
        
        # Вариант 4: создаем дефолтный статус
        logger.warning(f"⚠️ Не удалось найти статус, создаем дефолтный для {request_id}")
        logger.warning(f"🔍 Ключи ответа: {list(result.keys())}")
        
        return {
            "data": {
                "status": {
                    "state": "searching",
                    "hotelsfound": 0,
                    "toursfound": 0,
                    "minprice": None,
                    "progress": 0,
                    "timepassed": 0
                }
            }
        }
    
    def _extract_status_from_structure(self, data: Any, path: str = "") -> Dict[str, Any]:
        """Рекурсивное извлечение данных статуса из любой структуры"""
        status_fields = {
            "state": str,
            "hotelsfound": int,
            "toursfound": int, 
            "minprice": float,
            "progress": int,
            "timepassed": int
        }
        
        found_data = {}
        
        if isinstance(data, dict):
            # Прямая проверка ключей
            for field, field_type in status_fields.items():
                if field in data:
                    try:
                        value = data[field]
                        if field_type == int:
                            # Проверяем, является ли значение строкой или числом
                            if isinstance(value, str):
                                # Если строка пустая или содержит только пробелы, используем 0
                                if not value.strip():
                                    found_data[field] = 0
                                else:
                                    found_data[field] = int(value)
                            elif isinstance(value, (int, float)):
                                found_data[field] = int(value)
                            else:
                                found_data[field] = 0
                        elif field_type == float:
                            # Аналогично для float
                            if isinstance(value, str):
                                if not value.strip():
                                    found_data[field] = None
                                else:
                                    found_data[field] = float(value)
                            elif isinstance(value, (int, float)):
                                found_data[field] = float(value)
                            else:
                                found_data[field] = None
                        else:  # str
                            found_data[field] = str(value) if value is not None else ""
                    except (ValueError, TypeError) as e:
                        logger.warning(f"⚠️ Не удалось преобразовать {field}: {data[field]} -> {e}")
                        # Устанавливаем значения по умолчанию в случае ошибки
                        if field_type == int:
                            found_data[field] = 0
                        elif field_type == float:
                            found_data[field] = None
                        else:
                            found_data[field] = ""
                        continue
            
            # Если нашли хотя бы несколько полей, возвращаем
            if len(found_data) >= 2:
                logger.debug(f"🔍 Найдены поля статуса в {path}: {list(found_data.keys())}")
                return found_data
            
            # Рекурсивный поиск в дочерних элементах
            for key, value in data.items():
                child_result = self._extract_status_from_structure(value, f"{path}.{key}")
                if child_result and len(child_result) >= 2:
                    return child_result
        
        elif isinstance(data, list):
            # Поиск в списке
            for i, item in enumerate(data):
                child_result = self._extract_status_from_structure(item, f"{path}[{i}]")
                if child_result and len(child_result) >= 2:
                    return child_result
        
        return {}
    
    def _diagnose_status_response(self, result: Dict[str, Any], request_id: str):
        """Диагностика ответа статуса"""
        logger.debug(f"🔍 Диагностика статуса {request_id}:")
        logger.debug(f"  📋 Ключи верхнего уровня: {list(result.keys())}")
        
        if "data" in result:
            data = result["data"]
            logger.debug(f"  📊 Ключи data: {list(data.keys()) if isinstance(data, dict) else type(data)}")
            
            if isinstance(data, dict) and "status" in data:
                status = data["status"]
                logger.debug(f"  ⭐ Статус: {status}")
                
                if isinstance(status, dict):
                    state = status.get("state", "unknown")
                    progress = status.get("progress", 0)
                    hotels = status.get("hotelsfound", 0)
                    tours = status.get("toursfound", 0)
                    
                    logger.info(f"📈 Поиск {request_id}: {state}, {progress}%, отелей: {hotels}, туров: {tours}")
                else:
                    logger.warning(f"⚠️ Статус не является словарем: {type(status)}")
            else:
                logger.warning(f"⚠️ Нет блока 'status' в data для {request_id}")
        else:
            logger.warning(f"⚠️ Нет блока 'data' в ответе статуса для {request_id}")
    
    async def get_search_results(self, request_id: str, page: int = 1, onpage: int = 25) -> Dict[str, Any]:
        """Получение результатов поиска с улучшенной обработкой"""
        try:
            params = {
                "requestid": request_id,
                "type": "result",
                "page": page,
                "onpage": onpage,
                "format": "xml"
            }
            
            logger.debug(f"📥 Запрос результатов поиска {request_id} (страница {page})")
            result = await self._make_request("result.php", params)
            
            # Логируем структуру для диагностики
            logger.debug(f"🔍 Ключи результатов: {list(result.keys())}")
            
            # Нормализуем структуру результатов
            normalized_result = self._normalize_results_response(result, request_id)
            
            # Диагностика результатов
            self._diagnose_results_response(normalized_result, request_id)
            
            return normalized_result
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения результатов {request_id}: {e}")
            raise
    
    def _normalize_results_response(self, result: Dict[str, Any], request_id: str) -> Dict[str, Any]:
        """Нормализация ответа с результатами"""
        
        # Если уже правильная структура
        if "data" in result:
            return result
        
        # Создаем правильную структуру
        normalized = {"data": {}}
        
        # Ищем статус
        status_data = self._extract_status_from_structure(result)
        if status_data:
            normalized["data"]["status"] = status_data
        
        # Ищем результаты
        result_data = self._extract_results_from_structure(result)
        if result_data:
            normalized["data"]["result"] = result_data
        
        logger.debug(f"🔧 Нормализованы результаты для {request_id}")
        return normalized
    
    def _extract_results_from_structure(self, data: Any) -> Dict[str, Any]:
        """Извлечение результатов поиска из структуры"""
        
        if isinstance(data, dict):
            # Прямая проверка на наличие отелей
            if "hotel" in data:
                return {"hotel": data["hotel"]}
            
            # Поиск в результатах
            if "result" in data:
                return data["result"]
            
            # Рекурсивный поиск
            for key, value in data.items():
                if isinstance(value, dict):
                    child_result = self._extract_results_from_structure(value)
                    if child_result:
                        return child_result
        
        return {}
    
    def _diagnose_results_response(self, result: Dict[str, Any], request_id: str):
        """Диагностика ответа с результатами"""
        logger.debug(f"🔍 Диагностика результатов {request_id}:")
        
        if "data" in result:
            data = result["data"]
            
            # Проверяем статус
            if "status" in data:
                status = data["status"]
                if isinstance(status, dict):
                    state = status.get("state", "unknown")
                    hotels_found = status.get("hotelsfound", 0)
                    logger.info(f"📊 Результаты {request_id}: {state}, отелей найдено: {hotels_found}")
            
            # Проверяем результаты
            if "result" in data:
                result_data = data["result"]
                if isinstance(result_data, dict) and "hotel" in result_data:
                    hotels = result_data["hotel"]
                    hotels_count = len(hotels) if isinstance(hotels, list) else (1 if hotels else 0)
                    logger.info(f"🏨 Отелей в результатах: {hotels_count}")
                    
                    if hotels_count > 0:
                        # Показываем пример отеля
                        sample_hotel = hotels[0] if isinstance(hotels, list) else hotels
                        if isinstance(sample_hotel, dict):
                            logger.debug(f"🏨 Пример отеля: {sample_hotel.get('hotelname', 'No name')} - {sample_hotel.get('price', 'No price')}")
                else:
                    logger.warning(f"⚠️ Нет отелей в результатах для {request_id}")
            else:
                logger.warning(f"⚠️ Нет блока 'result' в ответе для {request_id}")
        else:
            logger.warning(f"⚠️ Нет блока 'data' в ответе результатов для {request_id}")
    
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
        
        try:
            result = await self._make_request_with_retry("hottours.php", params)
            
            # Логируем результат горящих туров
            hot_count = result.get("hotcount", 0)
            logger.debug(f"🔥 Горящие туры для города {city}: найдено {hot_count}")
            
            return result
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка получения горящих туров для города {city}: {e}")
            # Возвращаем пустой результат вместо ошибки
            return {"hotcount": 0, "hottours": []}
    
    async def get_references(self, ref_type: str, **filters) -> Dict[str, Any]:
        """Получение справочников"""
        params = {
            "type": ref_type,
            "format": "json",
            **filters
        }
        
        return await self._make_request_with_retry("list.php", params)
    
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
        
        # Добавляем детальное логирование
        logger.info(f"🔍 Актуализация тура {tour_id} с параметрами: {params}")
        
        try:
            result = await self._make_request("actualize.php", params)
            
            # Логируем результат запроса
            logger.info(f"📊 Результат актуализации для {tour_id}:")
            logger.info(f"   - Размер ответа: {len(str(result))} символов")
            logger.info(f"   - Ключи в ответе: {list(result.keys()) if isinstance(result, dict) else 'не словарь'}")
            
            if isinstance(result, dict):
                if "tour" in result:
                    tour_data = result["tour"]
                    logger.info(f"   - Данные тура: {len(str(tour_data))} символов")
                    if isinstance(tour_data, dict):
                        logger.info(f"   - Ключи тура: {list(tour_data.keys())}")
                    else:
                        logger.info(f"   - Тип данных тура: {type(tour_data)}")
                
                if "error" in result:
                    logger.warning(f"⚠️ Ошибка в ответе TourVisor: {result['error']}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Ошибка при актуализации тура {tour_id}: {e}")
            raise

    async def get_detailed_actualization(self, tour_id: str) -> Dict[str, Any]:
        """Детальная актуализация тура с информацией о рейсах"""
        params = {
            "tourid": tour_id,
            "format": "json"
        }
        
        return await self._make_request("actdetail.php", params)
    
    async def test_connection(self) -> Dict[str, Any]:
        """Тестирование подключения к API"""
        try:
            logger.info("🧪 Тестирование подключения к TourVisor API...")
            
            # Простой запрос справочника
            result = await self.get_references("departure")
            
            if result:
                departures_count = 0
                if "departure" in result:
                    departures = result["departure"]
                    departures_count = len(departures) if isinstance(departures, list) else 1
                
                logger.info(f"✅ Подключение успешно, городов вылета: {departures_count}")
                return {
                    "success": True,
                    "message": "Подключение к TourVisor API работает",
                    "departures_count": departures_count
                }
            else:
                logger.warning("⚠️ Подключение работает, но данные пустые")
                return {
                    "success": False,
                    "message": "API отвечает, но возвращает пустые данные"
                }
                
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к TourVisor API: {e}")
            return {
                "success": False,
                "message": f"Ошибка подключения: {str(e)}"
            }
    
    async def debug_raw_status_response(self, request_id: str) -> Dict[str, Any]:
        """Отладочный метод для получения сырого ответа статуса"""
        try:
            params = {
                "requestid": request_id,
                "type": "status",
                "format": "xml"
            }
            
            session = await self.get_session()
            full_params = {**self.auth_params, **params}
            url = f"{self.base_url}/result.php"
            
            async with session.get(url, params=full_params) as response:
                response_text = await response.text()
                
                logger.info(f"🔍 Сырой XML ответ для {request_id}:")
                logger.info(f"📄 Длина: {len(response_text)} символов")
                logger.info(f"📄 Содержимое: {response_text[:500]}...")
                
                # Пробуем распарсить
                try:
                    parsed = self._parse_xml(response_text)
                    logger.info(f"📊 Парсированная структура: {parsed}")
                    return {
                        "raw_text": response_text,
                        "parsed": parsed,
                        "length": len(response_text)
                    }
                except Exception as parse_error:
                    logger.error(f"❌ Ошибка парсинга: {parse_error}")
                    return {
                        "raw_text": response_text,
                        "parse_error": str(parse_error),
                        "length": len(response_text)
                    }
                    
        except Exception as e:
            logger.error(f"❌ Ошибка получения сырого ответа: {e}")
            raise
    
    async def debug_search_step_by_step(self, search_params: Dict[str, Any]) -> Dict[str, Any]:
        """Пошаговая диагностика поиска"""
        
        debug_info = {
            "original_params": search_params.copy(),
            "steps": [],
            "final_result": None,
            "error": None
        }
        
        try:
            # Шаг 1: Валидация параметров
            try:
                validated_params = self._validate_search_params(search_params.copy())
                debug_info["steps"].append({
                    "step": "validation",
                    "success": True,
                    "validated_params": validated_params
                })
            except Exception as val_error:
                debug_info["steps"].append({
                    "step": "validation",
                    "success": False,
                    "error": str(val_error)
                })
                raise
            
            # Шаг 2: Подготовка запроса
            session = await self.get_session()
            full_params = {**self.auth_params, **validated_params}
            url = f"{self.base_url}/search.php"
            
            debug_info["steps"].append({
                "step": "request_preparation",
                "success": True,
                "url": url,
                "param_count": len(full_params)
            })
            
            # Шаг 3: Выполнение запроса
            async with session.get(url, params=full_params) as response:
                response_text = await response.text()
                
                debug_info["steps"].append({
                    "step": "http_request",
                    "success": True,
                    "status_code": response.status,
                    "response_length": len(response_text),
                    "response_preview": response_text[:200]
                })
                
                # Шаг 4: Анализ ответа
                analysis = self._analyze_search_response(response_text)
                debug_info["steps"].append({
                    "step": "response_analysis",
                    "success": bool(analysis["request_id"]),
                    "analysis": analysis
                })
                
                debug_info["final_result"] = analysis["request_id"]
                
        except Exception as e:
            debug_info["error"] = str(e)
            debug_info["steps"].append({
                "step": "error",
                "error": str(e)
            })
        
        return debug_info
    # Добавить в app/core/tourvisor_client.py

    async def get_hotel_info(self, hotel_code: str, include_reviews: bool = True, 
                           big_images: bool = True, remove_tags: bool = True) -> Dict[str, Any]:
        """
        Получение детальной информации об отеле
        
        Args:
            hotel_code: Код отеля
            include_reviews: Включать отзывы (по умолчанию True)
            big_images: Большие изображения 800px (по умолчанию True)
            remove_tags: Убирать HTML теги из списков (по умолчанию True)
        """
        try:
            params = {
                "format": "json",
                "hotelcode": hotel_code,
                "authlogin": self.login,
                "authpass": self.password
            }
            
            # Дополнительные параметры
            if include_reviews:
                params["reviews"] = 1
            
            if big_images:
                params["imgbig"] = 1
            
            if remove_tags:
                params["removetags"] = 1
            
            logger.info(f"🏨 Запрос информации об отеле {hotel_code}")
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(
                    f"{self.base_url}/xml/hotel.php",
                    params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ Получена информация об отеле {hotel_code}")
                        return data
                    else:
                        error_text = await response.text()
                        logger.error(f"❌ Ошибка получения информации об отеле {hotel_code}: {response.status} - {error_text}")
                        raise Exception(f"HTTP {response.status}: {error_text}")
                        
        except Exception as e:
            logger.error(f"❌ Ошибка запроса информации об отеле {hotel_code}: {e}")
            raise
# Синглтон клиента
tourvisor_client = TourVisorClient()