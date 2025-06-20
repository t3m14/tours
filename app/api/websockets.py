import asyncio
import json
from typing import Dict, Set
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
                            results = await tour_service.get_search_results(request_id, 1, 25)
                            
                            logger.info(f"Получено результатов для {request_id}: {len(results.result) if results.result else 0} отелей")
                            
                            # Отправляем результаты
                            await self._broadcast_to_group(request_id, {
                                "type": "results", 
                                "data": {
                                    "status": results.status.model_dump(),
                                    "hotels": [hotel.model_dump() for hotel in results.result] if results.result else []
                                }
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