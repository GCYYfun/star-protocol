"""WebSocket 连接管理"""

import logging
from typing import Optional
import websockets
from websockets.client import WebSocketClientProtocol

from star_protocol.exceptions import ConnectionError as StarConnectionError


class ConnectionManager:
    """
    WebSocket 连接管理器
    
    职责：
    - 建立和断开 WebSocket 连接
    - 发送和接收原始数据
    - 连接状态检查
    """
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._ws: Optional[WebSocketClientProtocol] = None
        self._url: Optional[str] = None
    
    async def connect(self, url: str, role: str, client_id: str) -> None:
        """
        连接到 Hub Server
        
        Args:
            url: WebSocket URL (ws://host:port)
            role: 客户端角色
            client_id: 客户端 ID
        
        Raises:
            StarConnectionError: 连接失败
        """
        # 构建完整 URL: ws://host:port/ws/role/client_id
        if not url.endswith("/"):
            url += "/"
        self._url = f"{url}ws/{role}/{client_id}"
        
        try:
            self._ws = await websockets.connect(self._url)
            self.logger.info(f"Connected to {self._url}")
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            raise StarConnectionError(f"Failed to connect to {self._url}: {e}")
    
    async def disconnect(self) -> None:
        """断开连接"""
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                self.logger.warning(f"Error closing websocket: {e}")
            finally:
                self._ws = None
        
        self.logger.info("Disconnected")
    
    async def send_raw(self, data: str) -> None:
        """
        发送原始数据
        
        Args:
            data: JSON 字符串
        
        Raises:
            StarConnectionError: 未连接
        """
        if not self._ws:
            raise StarConnectionError("Not connected")
        
        try:
            await self._ws.send(data)
            self.logger.debug(f"Sent: {len(data)} bytes")
        except Exception as e:
            self.logger.error(f"Send failed: {e}")
            raise StarConnectionError(f"Failed to send message: {e}")
    
    async def receive_raw(self) -> str:
        """
        接收原始数据
        
        Returns:
            JSON 字符串
        
        Raises:
            StarConnectionError: 未连接
        """
        if not self._ws:
            raise StarConnectionError("Not connected")
        
        try:
            message = await self._ws.recv()
            self.logger.debug(f"Received: {len(message)} bytes")
            return message
        except Exception as e:
            self.logger.error(f"Receive failed: {e}")
            raise StarConnectionError(f"Failed to receive message: {e}")
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        if self._ws is None:
            return False
        
        # 兼容不同版本的 websockets
        # 新版本使用 ClientConnection，没有 .open 属性
        # 旧版本使用 WebSocketClientProtocol，有 .open 属性
        try:
            # 尝试访问 .open 属性（旧版本）
            return self._ws.open
        except AttributeError:
            # 新版本：检查是否有 .close_code 属性
            # 如果连接已关闭，close_code 会被设置
            return not hasattr(self._ws, 'close_code') or self._ws.close_code is None
    
    @property
    def websocket(self) -> Optional[WebSocketClientProtocol]:
        """获取 WebSocket 对象"""
        return self._ws
