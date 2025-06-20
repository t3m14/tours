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
    
    async def connect(self, websocket: WebSocket, request_id: str):
        """Подключение WebSocket клиента"""
        await websocket.accept()
        
        # Добавляем соединение в группу по request_id
        if request_id not in self.active_connections:
            self.active_connections[request_id] = set()
        
        self.active_connections[request_id].add(websocket)
        
        # Запускаем мониторинг поиска, если еще не запущен
        if request_id not in self.monitoring_tasks:
            task = asyncio.create_task(self._monitor_search(request_id))
            self.monitoring_tasks[request_id] = task
        
        logger.info(f"WebSocket подключен для поиска {request_id}")
        
        try:
            # Отправляем текущий статус сразу после подключения
            await self._send_current_status(request_id)
            
            # Ожидаем отключения
            while True:
                await websocket.receive_text()
                
        except WebSocketDisconnect:
            await self._disconnect(websocket, request_id)
        except Exception as e:
            logger.error(f"Ошибка WebSocket соединения: {e}")
            await self._disconnect(websocket, request_id)
    
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
                
                logger.info(f"Остановлен мониторинг для поиска {request_id}")
        
        logger.info(f"WebSocket отключен для поиска {request_id}")
    
    async def _send_current_status(self, request_id: str):
        """Отправка текущего статуса поиска"""
        try:
            status = await tour_service.get_search_status(request_id)
            await self._broadcast_to_group(request_id, {
                "type": "status",
                "data": status.model_dump()
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
    
    async def _get_search_results_safe(self, request_id: str) -> Dict[str, Any]:
        """Безопасное получение результатов поиска с очисткой данных"""
        try:
            # Получаем сырые данные напрямую от TourVisor клиента
            from app.core.tourvisor_client import tourvisor_client
            raw_results = await tourvisor_client.get_search_results(request_id, 1, 25)
            
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
            
            while request_id in self.active_connections and not search_finished:
                try:
                    # Получаем статус поиска
                    status = await tour_service.get_search_status(request_id)
                    
                    # Отправляем статус всем подключенным клиентам
                    await self._broadcast_to_group(request_id, {
                        "type": "status",
                        "data": status.model_dump()
                    })
                    
                    # Если поиск завершен, отправляем результаты
                    if status.state == "finished":
                        logger.info(f"Поиск {request_id} завершен, получаем результаты...")
                        
                        try:
                            # Используем безопасный метод получения результатов
                            results = await self._get_search_results_safe(request_id)
                            
                            hotels_count = len(results["hotels"])
                            logger.info(f"Получено результатов для {request_id}: {hotels_count} отелей")
                            
                            # Отправляем результаты
                            await self._broadcast_to_group(request_id, {
                                "type": "results", 
                                "data": results
                            })
                            
                            # Даем время доставить сообщение
                            await asyncio.sleep(1)
                            
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
                        
                        # Закрываем все соединения для этого поиска
                        await self._close_all_connections(request_id, close_code=1000, reason="Поиск завершен")
                        search_finished = True
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

# Создаем глобальный экземпляр менеджера
websocket_manager = WebSocketManager()