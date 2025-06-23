import asyncio
import json
from typing import Dict, Set, Any, List
from fastapi import WebSocket, WebSocketDisconnect

from app.services.tour_service import tour_service
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class WebSocketManager:
    def __init__(self):
        # Хранилище активных соединений: request_id -> set of websockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # Хранилище задач мониторинга: request_id -> task
        self.monitoring_tasks: Dict[str, asyncio.Task] = {}
        # Хранилище состояния поиска: request_id -> search_state
        self.search_states: Dict[str, Dict[str, Any]] = {}
    
    async def connect(self, websocket: WebSocket, request_id: str):
        """Подключение WebSocket клиента"""
        await websocket.accept()
        
        # Добавляем соединение в группу по request_id
        if request_id not in self.active_connections:
            self.active_connections[request_id] = set()
        
        self.active_connections[request_id].add(websocket)
        
        # Инициализируем состояние поиска
        if request_id not in self.search_states:
            self.search_states[request_id] = {
                "current_page": 1,
                "per_page": 25,
                "is_finished": False,
                "total_hotels": 0,
                "total_pages": 0
            }
        
        # Запускаем мониторинг поиска, если еще не запущен
        if request_id not in self.monitoring_tasks:
            task = asyncio.create_task(self._monitor_search(request_id))
            self.monitoring_tasks[request_id] = task
        
        logger.info(f"WebSocket подключен для поиска {request_id}")
        
        try:
            # Отправляем текущий статус сразу после подключения
            await self._send_current_status(request_id)
            
            # Если поиск уже завершен, отправляем текущую страницу
            if self.search_states[request_id]["is_finished"]:
                await self._send_page_results(request_id, self.search_states[request_id]["current_page"])
            
            # Обрабатываем входящие сообщения
            while True:
                message_text = await websocket.receive_text()
                await self._handle_client_message(websocket, request_id, message_text)
                
        except WebSocketDisconnect:
            await self._disconnect(websocket, request_id)
        except Exception as e:
            logger.error(f"Ошибка WebSocket соединения: {e}")
            await self._disconnect(websocket, request_id)
    
    async def _handle_client_message(self, websocket: WebSocket, request_id: str, message_text: str):
        """Обработка сообщений от клиента"""
        try:
            message = json.loads(message_text)
            action = message.get("action")
            
            logger.info(f"Получено сообщение от клиента для поиска {request_id}: {message}")
            
            if action == "change_page":
                page = message.get("page", 1)
                await self._handle_page_change(request_id, page)
                
            elif action == "change_per_page":
                per_page = message.get("per_page", 25)
                await self._handle_per_page_change(request_id, per_page)
                
            elif action == "get_status":
                await self._send_current_status(request_id)
                
            elif action == "get_results":
                page = message.get("page", self.search_states[request_id]["current_page"])
                await self._send_page_results(request_id, page)
                
            elif action == "close_connection":
                await self._handle_close_connection(websocket, request_id)
                
            else:
                # Неизвестное действие
                await self._send_error_to_client(websocket, f"Неизвестное действие: {action}")
                
        except json.JSONDecodeError:
            logger.warning(f"Некорректный JSON от клиента: {message_text}")
            await self._send_error_to_client(websocket, "Некорректный формат сообщения")
        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения клиента: {e}")
            await self._send_error_to_client(websocket, f"Ошибка обработки: {str(e)}")
    
    async def _handle_page_change(self, request_id: str, page: int):
        """Обработка смены страницы"""
        try:
            search_state = self.search_states.get(request_id, {})
            
            # Валидация страницы
            if page < 1:
                page = 1
            
            # Если поиск завершен, проверяем максимальную страницу
            if search_state.get("is_finished") and search_state.get("total_pages"):
                if page > search_state["total_pages"]:
                    page = search_state["total_pages"]
            
            # Обновляем текущую страницу
            self.search_states[request_id]["current_page"] = page
            
            logger.info(f"Смена страницы для поиска {request_id}: страница {page}")
            
            # Отправляем результаты для новой страницы
            await self._send_page_results(request_id, page)
            
        except Exception as e:
            logger.error(f"Ошибка при смене страницы: {e}")
    
    async def _handle_close_connection(self, websocket: WebSocket, request_id: str):
        """Обработка запроса на закрытие соединения от клиента"""
        try:
            logger.info(f"Получен запрос на закрытие соединения от клиента для поиска {request_id}")
            
            # Отправляем подтверждение перед закрытием
            await self._send_response_to_client(websocket, "connection_closing", {
                "message": "Соединение закрывается по запросу клиента",
                "request_id": request_id
            })
            
            # Даем время доставить сообщение
            await asyncio.sleep(0.1)
            
            # Закрываем конкретное соединение
            await websocket.close(code=1000, reason="Закрыто по запросу клиента")
            
            # Убираем соединение из активных
            if request_id in self.active_connections:
                self.active_connections[request_id].discard(websocket)
                
                # Если это было последнее соединение для данного поиска
                if not self.active_connections[request_id]:
                    logger.info(f"Последнее соединение закрыто для поиска {request_id}, очищаем ресурсы")
                    
                    # Удаляем пустой набор соединений
                    del self.active_connections[request_id]
                    
                    # Останавливаем мониторинг
                    if request_id in self.monitoring_tasks:
                        self.monitoring_tasks[request_id].cancel()
                        del self.monitoring_tasks[request_id]
                        logger.info(f"Мониторинг поиска {request_id} остановлен")
                    
                    # Очищаем состояние поиска
                    if request_id in self.search_states:
                        del self.search_states[request_id]
                        logger.info(f"Состояние поиска {request_id} очищено")
                else:
                    logger.info(f"Соединение закрыто для поиска {request_id}, остается {len(self.active_connections[request_id])} активных соединений")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке закрытия соединения: {e}")
    
    async def _send_response_to_client(self, websocket: WebSocket, response_type: str, data: dict):
        """Отправка ответа конкретному клиенту"""
        try:
            await websocket.send_text(json.dumps({
                "type": response_type,
                "data": data
            }, ensure_ascii=False))
        except Exception as e:
            logger.error(f"Ошибка при отправке ответа клиенту: {e}")
    
    async def _handle_per_page_change(self, request_id: str, per_page: int):
        """Обработка изменения количества результатов на странице"""
        try:
            # Валидация per_page
            if per_page < 1:
                per_page = 25
            elif per_page > 100:
                per_page = 100
            
            self.search_states[request_id]["per_page"] = per_page
            
            # Пересчитываем общее количество страниц
            if self.search_states[request_id].get("total_hotels"):
                total_hotels = self.search_states[request_id]["total_hotels"]
                total_pages = (total_hotels + per_page - 1) // per_page
                self.search_states[request_id]["total_pages"] = total_pages
                
                # Проверяем текущую страницу
                current_page = self.search_states[request_id]["current_page"]
                if current_page > total_pages:
                    self.search_states[request_id]["current_page"] = total_pages
            
            logger.info(f"Изменение per_page для поиска {request_id}: {per_page} результатов на странице")
            
            # Отправляем обновленные результаты
            await self._send_page_results(request_id, self.search_states[request_id]["current_page"])
            
        except Exception as e:
            logger.error(f"Ошибка при изменении per_page: {e}")
    
    async def _send_page_results(self, request_id: str, page: int):
        """Отправка результатов конкретной страницы"""
        try:
            search_state = self.search_states.get(request_id, {})
            per_page = search_state.get("per_page", 25)
            
            logger.info(f"Отправка результатов страницы {page} для поиска {request_id} (по {per_page} на странице)")
            
            # Получаем результаты для конкретной страницы
            results = await self._get_search_results_safe(request_id, page, per_page)
            
            # Обновляем состояние поиска
            if results["status"]["state"] == "finished":
                total_hotels = results["status"]["hotelsfound"]
                total_pages = (total_hotels + per_page - 1) // per_page if total_hotels > 0 else 0
                
                self.search_states[request_id].update({
                    "is_finished": True,
                    "total_hotels": total_hotels,
                    "total_pages": total_pages
                })
            
            # Добавляем информацию о пагинации
            pagination_info = {
                "current_page": page,
                "per_page": per_page,
                "total_hotels": search_state.get("total_hotels", results["status"]["hotelsfound"]),
                "total_pages": search_state.get("total_pages", 0),
                "has_next_page": page < search_state.get("total_pages", 0),
                "has_prev_page": page > 1,
                "hotels_on_page": len(results["hotels"])
            }
            
            # Отправляем результаты с информацией о пагинации
            await self._broadcast_to_group(request_id, {
                "type": "page_results",
                "data": {
                    "status": results["status"],
                    "hotels": results["hotels"],
                    "pagination": pagination_info
                }
            })
            
            logger.info(f"Отправлено {len(results['hotels'])} отелей на странице {page}")
            
        except Exception as e:
            logger.error(f"Ошибка при отправке результатов страницы: {e}")
    
    async def _send_error_to_client(self, websocket: WebSocket, error_message: str):
        """Отправка сообщения об ошибке конкретному клиенту"""
        try:
            await websocket.send_text(json.dumps({
                "type": "error",
                "data": {
                    "message": error_message
                }
            }, ensure_ascii=False))
        except Exception as e:
            logger.error(f"Ошибка при отправке ошибки клиенту: {e}")
    
    async def _disconnect(self, websocket: WebSocket, request_id: str):
        """Отключение WebSocket клиента"""
        if request_id in self.active_connections:
            self.active_connections[request_id].discard(websocket)
            
            # Если больше нет подключений для этого поиска, останавливаем мониторинг
            if not self.active_connections[request_id]:
                del self.active_connections[request_id]
                
                if request_id in self.monitoring_tasks:
                    self.monitoring_tasks[request_id].cancel()
                    del self.monitoring_tasks[request_id]
                
                # Очищаем состояние поиска
                if request_id in self.search_states:
                    del self.search_states[request_id]
                
                logger.info(f"Остановлен мониторинг для поиска {request_id}")
        
        logger.info(f"WebSocket отключен для поиска {request_id}")
    
    async def _send_current_status(self, request_id: str):
        """Отправка текущего статуса поиска"""
        try:
            status = await tour_service.get_search_status(request_id)
            search_state = self.search_states.get(request_id, {})
            
            # Добавляем информацию о пагинации к статусу
            status_data = status.model_dump()
            status_data["pagination"] = {
                "current_page": search_state.get("current_page", 1),
                "per_page": search_state.get("per_page", 25),
                "total_pages": search_state.get("total_pages", 0),
                "is_finished": search_state.get("is_finished", False)
            }
            
            await self._broadcast_to_group(request_id, {
                "type": "status",
                "data": status_data
            })
        except Exception as e:
            logger.error(f"Ошибка при отправке статуса: {e}")
    
    def _clean_string_field(self, value: Any) -> str:
        """Очистка строкового поля от некорректных значений"""
        if value is None or isinstance(value, dict) or isinstance(value, list):
            return ""
        return str(value)
    
    def _clean_int_field(self, value: Any) -> int:
        """Очистка целочисленного поля"""
        if value is None or isinstance(value, dict) or isinstance(value, list):
            return 0
        try:
            return int(float(str(value)))
        except (ValueError, TypeError):
            return 0
    
    def _clean_float_field(self, value: Any) -> float:
        """Очистка поля с плавающей точкой"""
        if value is None or isinstance(value, dict) or isinstance(value, list):
            return 0.0
        try:
            return float(str(value))
        except (ValueError, TypeError):
            return 0.0
    
    def _clean_tour_data(self, tour_data: Dict[str, Any]) -> Dict[str, Any]:
        """Очистка данных тура от некорректных значений"""
        return {
            # Строковые поля
            "operatorcode": self._clean_string_field(tour_data.get("operatorcode")),
            "operatorname": self._clean_string_field(tour_data.get("operatorname")),
            "flydate": self._clean_string_field(tour_data.get("flydate")),
            "placement": self._clean_string_field(tour_data.get("placement")),
            "meal": self._clean_string_field(tour_data.get("meal")),
            "mealrussian": self._clean_string_field(tour_data.get("mealrussian")),
            "room": self._clean_string_field(tour_data.get("room")),
            "tourname": self._clean_string_field(tour_data.get("tourname")),
            "tourid": self._clean_string_field(tour_data.get("tourid")),
            "currency": self._clean_string_field(tour_data.get("currency", "RUB")),
            "tourlink": self._clean_string_field(tour_data.get("tourlink")) or None,
            
            # Целочисленные поля
            "nights": self._clean_int_field(tour_data.get("nights")),
            "adults": self._clean_int_field(tour_data.get("adults")),
            "child": self._clean_int_field(tour_data.get("child")),
            "regular": self._clean_int_field(tour_data.get("regular")) or None,
            "promo": self._clean_int_field(tour_data.get("promo")) or None,
            "onrequest": self._clean_int_field(tour_data.get("onrequest")) or None,
            "flightstatus": self._clean_int_field(tour_data.get("flightstatus")) or None,
            "hotelstatus": self._clean_int_field(tour_data.get("hotelstatus")) or None,
            "nightflight": self._clean_int_field(tour_data.get("nightflight")) or None,
            
            # Поля с плавающей точкой
            "price": self._clean_float_field(tour_data.get("price")),
            "fuelcharge": self._clean_float_field(tour_data.get("fuelcharge")),
            "priceue": self._clean_float_field(tour_data.get("priceue")) if tour_data.get("priceue") is not None else None,
        }
    
    def _clean_hotel_data(self, hotel_data: Dict[str, Any]) -> Dict[str, Any]:
        """Очистка данных отеля"""
        return {
            # Строковые поля
            "hotelcode": self._clean_string_field(hotel_data.get("hotelcode")),
            "countrycode": self._clean_string_field(hotel_data.get("countrycode")),
            "countryname": self._clean_string_field(hotel_data.get("countryname")),
            "regioncode": self._clean_string_field(hotel_data.get("regioncode")),
            "regionname": self._clean_string_field(hotel_data.get("regionname")),
            "hotelname": self._clean_string_field(hotel_data.get("hotelname")),
            "subregioncode": self._clean_string_field(hotel_data.get("subregioncode")) or None,
            "hoteldescription": self._clean_string_field(hotel_data.get("hoteldescription")) or None,
            "fulldesclink": self._clean_string_field(hotel_data.get("fulldesclink")) or None,
            "reviewlink": self._clean_string_field(hotel_data.get("reviewlink")) or None,
            "picturelink": self._clean_string_field(hotel_data.get("picturelink")) or None,
            
            # Числовые поля
            "price": self._clean_float_field(hotel_data.get("price")),
            "hotelstars": self._clean_int_field(hotel_data.get("hotelstars")),
            "hotelrating": self._clean_float_field(hotel_data.get("hotelrating")),
            "isphoto": self._clean_int_field(hotel_data.get("isphoto")) or None,
            "iscoords": self._clean_int_field(hotel_data.get("iscoords")) or None,
            "isdescription": self._clean_int_field(hotel_data.get("isdescription")) or None,
            "isreviews": self._clean_int_field(hotel_data.get("isreviews")) or None,
            "seadistance": self._clean_int_field(hotel_data.get("seadistance")) or None,
        }
    
    async def _get_search_results_safe(self, request_id: str, page: int = 1, per_page: int = 25) -> Dict[str, Any]:
        """Безопасное получение результатов поиска с очисткой данных и пагинацией"""
        try:
            # Получаем сырые данные напрямую от TourVisor клиента
            from app.core.tourvisor_client import tourvisor_client
            raw_results = await tourvisor_client.get_search_results(request_id, page, per_page)
            
            data = raw_results.get("data", {})
            
            # Обрабатываем статус
            status_data = data.get("status", {})
            cleaned_status = {
                "state": self._clean_string_field(status_data.get("state", "searching")),
                "hotelsfound": self._clean_int_field(status_data.get("hotelsfound")),
                "toursfound": self._clean_int_field(status_data.get("toursfound")),
                "minprice": self._clean_float_field(status_data.get("minprice")) if status_data.get("minprice") else None,
                "progress": self._clean_int_field(status_data.get("progress")),
                "timepassed": self._clean_int_field(status_data.get("timepassed"))
            }
            
            # Обрабатываем отели
            result_data = data.get("result", {})
            hotel_list = result_data.get("hotel", [])
            
            if not isinstance(hotel_list, list):
                hotel_list = [hotel_list] if hotel_list else []
            
            cleaned_hotels = []
            
            for hotel_data in hotel_list:
                try:
                    # Очищаем данные отеля
                    cleaned_hotel = self._clean_hotel_data(hotel_data)
                    
                    # Обрабатываем туры для отеля
                    tours_data = hotel_data.get("tours", {})
                    
                    # Извлекаем список туров
                    if isinstance(tours_data, dict) and "tour" in tours_data:
                        tour_list = tours_data["tour"]
                    else:
                        tour_list = tours_data
                    
                    if not isinstance(tour_list, list):
                        tour_list = [tour_list] if tour_list else []
                    
                    cleaned_tours = []
                    for tour_data in tour_list:
                        try:
                            if isinstance(tour_data, dict):
                                cleaned_tour = self._clean_tour_data(tour_data)
                                cleaned_tours.append(cleaned_tour)
                        except Exception as tour_error:
                            logger.warning(f"Ошибка при очистке тура: {tour_error}")
                            continue
                    
                    cleaned_hotel["tours"] = cleaned_tours
                    cleaned_hotels.append(cleaned_hotel)
                    
                except Exception as hotel_error:
                    logger.warning(f"Ошибка при очистке отеля: {hotel_error}")
                    continue
            
            return {
                "status": cleaned_status,
                "hotels": cleaned_hotels
            }
            
        except Exception as e:
            logger.error(f"Ошибка при безопасном получении результатов: {e}")
            return {
                "status": {
                    "state": "error",
                    "hotelsfound": 0,
                    "toursfound": 0,
                    "minprice": None,
                    "progress": 0,
                    "timepassed": 0
                },
                "hotels": []
            }
    
    async def _monitor_search(self, request_id: str):
        """Мониторинг поиска и отправка обновлений"""
        try:
            logger.info(f"Начат мониторинг поиска {request_id}")
            search_finished = False
            last_hotels_count = 0
            results_sent = False
            
            while request_id in self.active_connections and not search_finished:
                try:
                    # Получаем статус поиска
                    status = await tour_service.get_search_status(request_id)
                    
                    # Отправляем статус всем подключенным клиентам
                    await self._send_current_status(request_id)
                    
                    current_hotels_count = status.hotelsfound
                    
                    # Проверяем, есть ли новые результаты для отправки
                    should_send_results = False
                    
                    if current_hotels_count > last_hotels_count:
                        # Есть новые отели
                        if not results_sent:
                            # Первая отправка результатов - отправляем если есть хотя бы несколько отелей
                            if current_hotels_count >= 5:
                                should_send_results = True
                                results_sent = True
                                logger.info(f"Отправляем первые результаты для поиска {request_id}: {current_hotels_count} отелей")
                        else:
                            # Проверяем, нужно ли обновить результаты
                            # Отправляем обновления если количество отелей увеличилось значительно
                            hotels_diff = current_hotels_count - last_hotels_count
                            if hotels_diff >= 10 or (hotels_diff >= 5 and current_hotels_count < 25):
                                should_send_results = True
                                logger.info(f"Обновляем результаты для поиска {request_id}: +{hotels_diff} отелей (всего {current_hotels_count})")
                    
                    # Если поиск завершен и еще не отправляли результаты, отправляем обязательно
                    if status.state == "finished":
                        if not results_sent or current_hotels_count > last_hotels_count:
                            should_send_results = True
                            logger.info(f"Поиск {request_id} завершен, отправляем финальные результаты: {current_hotels_count} отелей")
                        
                        # Отмечаем поиск как завершенный
                        self.search_states[request_id]["is_finished"] = True
                        search_finished = True
                    
                    # Отправляем результаты если нужно
                    if should_send_results:
                        try:
                            current_page = self.search_states[request_id]["current_page"]
                            await self._send_page_results(request_id, current_page)
                            last_hotels_count = current_hotels_count
                            
                        except Exception as results_error:
                            logger.error(f"Ошибка при получении результатов для {request_id}: {results_error}")
                            
                            # Отправляем сообщение об ошибке
                            await self._broadcast_to_group(request_id, {
                                "type": "error",
                                "data": {
                                    "message": "Ошибка при получении результатов поиска",
                                    "error": str(results_error)
                                }
                            })
                    
                    if search_finished:
                        break
                    
                    # Ждем перед следующей проверкой
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    logger.error(f"Ошибка в мониторинге поиска {request_id}: {e}")
                    await asyncio.sleep(5)  # Больше времени при ошибке
            
        except asyncio.CancelledError:
            logger.info(f"Мониторинг поиска {request_id} отменен")
        except Exception as e:
            logger.error(f"Критическая ошибка в мониторинге {request_id}: {e}")
            # При критической ошибке закрываем все соединения
            await self._close_all_connections(request_id, close_code=1011, reason="Ошибка сервера")
        finally:
            # Очистка при завершении
            if request_id in self.monitoring_tasks:
                del self.monitoring_tasks[request_id]
    
    async def _broadcast_to_group(self, request_id: str, message: dict):
        """Отправка сообщения всем клиентам в группе"""
        if request_id not in self.active_connections:
            return
        
        disconnected = set()
        message_text = json.dumps(message, ensure_ascii=False, default=str)
        
        for websocket in self.active_connections[request_id]:
            try:
                await websocket.send_text(message_text)
            except Exception as e:
                logger.warning(f"Не удалось отправить сообщение через WebSocket: {e}")
                disconnected.add(websocket)
        
        # Удаляем отключенные соединения
        for websocket in disconnected:
            self.active_connections[request_id].discard(websocket)
    
    async def _close_all_connections(self, request_id: str, close_code: int = 1000, reason: str = "Завершено"):
        """Закрытие всех WebSocket соединений для поиска"""
        if request_id not in self.active_connections:
            return
        
        connections_to_close = list(self.active_connections[request_id])
        
        for websocket in connections_to_close:
            try:
                await websocket.close(code=close_code, reason=reason)
                logger.debug(f"WebSocket соединение закрыто для поиска {request_id}")
            except Exception as e:
                logger.warning(f"Ошибка при закрытии WebSocket: {e}")
        
        # Очищаем все соединения для этого поиска
        if request_id in self.active_connections:
            del self.active_connections[request_id]
        
        # Отменяем задачу мониторинга
        if request_id in self.monitoring_tasks:
            self.monitoring_tasks[request_id].cancel()
            del self.monitoring_tasks[request_id]
        
        # Очищаем состояние поиска
        if request_id in self.search_states:
            del self.search_states[request_id]
        
        logger.info(f"Все WebSocket соединения закрыты для поиска {request_id}")
    
    async def send_search_update(self, request_id: str, update_type: str, data: dict):
        """Публичный метод для отправки обновлений поиска"""
        await self._broadcast_to_group(request_id, {
            "type": update_type,
            "data": data
        })
    
    async def force_close_search_connections(self, request_id: str):
        """Принудительное закрытие всех соединений для поиска (для внешнего использования)"""
        await self._close_all_connections(request_id, close_code=1000, reason="Принудительное закрытие")
    
    def get_active_connections_count(self) -> int:
        """Получение общего количества активных соединений"""
        total = 0
        for connections in self.active_connections.values():
            total += len(connections)
        return total
    
    def get_search_connections_info(self) -> Dict[str, int]:
        """Получение информации о соединениях по поискам"""
        return {
            request_id: len(connections) 
            for request_id, connections in self.active_connections.items()
        }
    
    async def close_client_connection(self, request_id: str, websocket: WebSocket):
        """Публичный метод для закрытия конкретного клиентского соединения"""
        await self._handle_close_connection(websocket, request_id)
    
    async def close_all_clients_for_search(self, request_id: str, reason: str = "Закрыто администратором"):
        """Закрытие всех клиентских соединений для конкретного поиска"""
        if request_id not in self.active_connections:
            logger.info(f"Нет активных соединений для поиска {request_id}")
            return
        
        connections_to_close = list(self.active_connections[request_id])
        logger.info(f"Закрытие {len(connections_to_close)} соединений для поиска {request_id}")
        
        # Уведомляем всех клиентов о предстоящем закрытии
        await self._broadcast_to_group(request_id, {
            "type": "connection_closing",
            "data": {
                "message": reason,
                "request_id": request_id
            }
        })
        
        # Даем время доставить сообщение
        await asyncio.sleep(0.2)
        
        # Закрываем все соединения
        for websocket in connections_to_close:
            try:
                await websocket.close(code=1000, reason=reason)
            except Exception as e:
                logger.warning(f"Ошибка при закрытии WebSocket: {e}")
        
        # Очищаем ресурсы
        await self._cleanup_search_resources(request_id)
    
    async def _cleanup_search_resources(self, request_id: str):
        """Очистка всех ресурсов для конкретного поиска"""
        try:
            # Удаляем соединения
            if request_id in self.active_connections:
                del self.active_connections[request_id]
            
            # Останавливаем мониторинг
            if request_id in self.monitoring_tasks:
                self.monitoring_tasks[request_id].cancel()
                del self.monitoring_tasks[request_id]
            
            # Очищаем состояние
            if request_id in self.search_states:
                del self.search_states[request_id]
            
            logger.info(f"Все ресурсы для поиска {request_id} очищены")
            
        except Exception as e:
            logger.error(f"Ошибка при очистке ресурсов для поиска {request_id}: {e}")
    
    def get_search_states_info(self) -> Dict[str, Dict[str, Any]]:
        """Получение информации о состояниях поисков"""
        return self.search_states.copy()

# Создаем глобальный экземпляр менеджера
websocket_manager = WebSocketManager()