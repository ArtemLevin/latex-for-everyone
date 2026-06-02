"""
WebSocket handlers for live preview and real-time collaboration.
"""
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set
import json
import logging
import asyncio
from app.services.latex_compiler import LatexCompiler

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.compiler = LatexCompiler()

    async def connect(self, websocket: WebSocket, project_id: str):
        await websocket.accept()
        if project_id not in self.active_connections:
            self.active_connections[project_id] = set()
        self.active_connections[project_id].add(websocket)
        logger.info(f"WebSocket connected for project {project_id}")

    def disconnect(self, websocket: WebSocket, project_id: str):
        if project_id in self.active_connections:
            self.active_connections[project_id].discard(websocket)
            if not self.active_connections[project_id]:
                del self.active_connections[project_id]
        logger.info(f"WebSocket disconnected for project {project_id}")

    async def send_compile_result(self, project_id: str, result: dict):
        if project_id in self.active_connections:
            message = json.dumps({
                "type": "compile_result",
                "data": result,
            })
            disconnected = set()
            for connection in self.active_connections[project_id]:
                try:
                    await connection.send_text(message)
                except Exception:
                    disconnected.add(connection)
            for conn in disconnected:
                self.active_connections[project_id].discard(conn)


manager = ConnectionManager()


async def websocket_compile(websocket: WebSocket, project_id: str):
    await manager.connect(websocket, project_id)

    compile_queue = asyncio.Queue()
    last_content = ""

    async def compile_worker():
        nonlocal last_content
        while True:
            content = await compile_queue.get()
            if content != last_content:
                last_content = content
                result = manager.compiler.compile(content, {})
                await manager.send_compile_result(project_id, result)
            compile_queue.task_done()
            await asyncio.sleep(0.5)  # Debounce

    worker_task = asyncio.create_task(compile_worker())

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("type") == "content_change":
                await compile_queue.put(message.get("content", ""))

            elif message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(websocket, project_id)
    finally:
        worker_task.cancel()
