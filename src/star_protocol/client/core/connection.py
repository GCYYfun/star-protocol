"""WebSocket 连接管理模块 (WebSocket Connection Management Module).

此模块提供了底层 WebSocket 连接的封装，负责与 Hub Server 进行稳定的双向通信。
包含连接建立、安全断开、数据收发及状态生命周期维护等能力。
支持异步上下文管理器，更适用于生产环境版本发布。
"""

import asyncio
import logging
from typing import Optional
from urllib.parse import urljoin

import websockets
from websockets.client import ClientConnection
from websockets.exceptions import ConnectionClosed, WebSocketException
from websockets.protocol import State

from star_protocol.exceptions import ConnectionError as StarConnectionError


class ConnectionManager:
    """WebSocket 连接管理器。

    主要职责：
    1. 建立和安全断开与 Hub Server 的 WebSocket 连接。
    2. 发送和接收原始字符串形式（如 JSON）的数据。
    3. 连接状态检查以及生命周期的维护机制。
    4. 封装底层的 exceptions 并转换为域内统一的 StarConnectionError 抛出以提升模块封装度。

    Attributes:
        logger (logging.Logger): 用于打印日志的 Logger 实例。
        _ws (Optional[ClientConnection]): 原生 WebSocket 客户端连接实例。
        _url (Optional[str]): 当前建立连接的完整 WebSocket 统一资源定位符 (URL)。
    """

    def __init__(self, logger: logging.Logger) -> None:
        """初始化 ConnectionManager。

        Args:
            logger (logging.Logger): 注入的日志记录器实例。
        """
        self.logger = logger
        self._ws: Optional[ClientConnection] = None
        self._url: Optional[str] = None

    async def __aenter__(self):
        """支持 async with 语法直接管理连接上下文，发布版本的标准实践"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出上下文时确保连接进行优雅地断开资源释放"""
        await self.disconnect()

    def _build_ws_url(self, base_url: str, role: str, client_id: str) -> str:
        """构建 WebSocket 按规则约定的连接 URL（内部封装，高内聚）。

        Args:
            base_url (str): 基础 URL, 例如 'ws://host:port' 等
            role (str): 客户端角色, 例如 'agent' 或 'human'
            client_id (str): 客户端实例的唯一标识符

        Returns:
            str: 拼接后的完整 WebSocket URL，格式如 'ws://host:port/ws/{role}/{client_id}'
        """
        # 确保 base_url 以 "/" 结尾以支持可靠的拼接
        if not base_url.endswith("/"):
            base_url += "/"
        
        path = f"ws/{role}/{client_id}"
        return urljoin(base_url, path)

    async def connect(self, url: str, role: str, client_id: str) -> None:
        """建立至 Hub Server 的 WebSocket 连接。

        Args:
            url (str): Hub Server 的基础 WebSocket URL
            role (str): 客户端承担的角色类型
            client_id (str): 唯一的客户端 ID

        Raises:
            StarConnectionError: 当协议级别或网络错误导致无法连接时抛出。
        """
        self._url = self._build_ws_url(url, role, client_id)
        
        try:
            self.logger.debug(f"Attempting to connect WebSocket to {self._url}")
            # 进行实际连接，根据 websockets 版本可能有不同的行为表现
            self._ws = await websockets.connect(self._url)
            self.logger.info(f"Successfully connected to Hub Server at {self._url}")
            
        except WebSocketException as ws_err:
            # 区分底层 WebSocket 特异性异常
            self.logger.error(f"WebSocket specific network error during connect: {ws_err}")
            raise StarConnectionError(f"WebSocket specific error connecting to {self._url}: {ws_err}") from ws_err
            
        except Exception as e:
            # 捕获其它例如 DNS无法解析、拒绝连接等基础网络或 OS 异常
            self.logger.error(f"General connection failed: {e}")
            raise StarConnectionError(f"Failed to connect to {self._url}: {e}") from e

    async def disconnect(self) -> None:
        """安全且幂等的方式断开与服务端的 WebSocket 连接并彻底释放资源。

        即使连接已断开，多次调用亦不会抛出异常。
        """
        if self._ws:
            self.logger.debug("Closing WebSocket connection to the server...")
            try:
                await self._ws.close()
            except Exception as e:
                self.logger.warning(f"Error occasionally occurred while closing websocket: {e}")
            finally:
                self._ws = None
                self.logger.info("WebSocket disconnected gracefully.")
        else:
            self.logger.debug("Attempted to disconnect, but websocket is already closed.")

    async def send_raw(self, data: str) -> None:
        """向 Hub 服务器下发未加工原始字符串包数据（通常期望是序列化过的 JSON）。

        Args:
            data (str): 待发送出去的即时串流载荷。

        Raises:
            StarConnectionError: 当前未连接，或者发送中途检测到由于网络导致中途中断。
        """
        if not self.is_connected():
            raise StarConnectionError("Cannot send payload: No active connection with any server.")
        
        try:
            # ClientConnection.send supports str & bytes. We send str.
            await self._ws.send(data)
            self.logger.debug(f"Sent websocket payload: {len(data)} bytes")
            
        except ConnectionClosed as closed_err:
            self.logger.error(f"Remote connection unexpectedly closed during payload transmission: {closed_err}")
            await self.disconnect()
            raise StarConnectionError(f"Connection automatically lost while sending data: {closed_err}") from closed_err
            
        except Exception as e:
            self.logger.error(f"Failed to send outbound data through websocket: {e}")
            raise StarConnectionError(f"Failed to transmit data: {e}") from e

    async def receive_raw(self) -> str:
        """以阻塞协程的方式从被连接 Hub 接收下一条发来的原始消息。

        Returns:
            str: 成功接收到的消息内容（多数场景下解构为有效 JSON 格式）。

        Raises:
            StarConnectionError: 服务端掉线无法接收、管道闭合并抛出等。
        """
        if not self.is_connected():
            raise StarConnectionError("Cannot receive incoming push: No active connection.")
        
        try:
            # ClientConnection.recv returns Data (str or bytes)
            message = await self._ws.recv()
            
            # 若 recv 处于不同配置的 SubProtocol 偶尔返回了 bytes，做前置兼容
            if isinstance(message, bytes):
                message = message.decode('utf-8')
                
            self.logger.debug(f"Received inbound payload: {len(message)} bytes")
            return message
            
        except ConnectionClosed as closed_err:
            self.logger.error(f"Host unexpectedly closed connection while waiting for frame read: {closed_err}")
            await self.disconnect()
            raise StarConnectionError(f"Connection terminated by Hub: {closed_err}") from closed_err
            
        except Exception as e:
            self.logger.error(f"Unexpected receive operation failure: {e}")
            raise StarConnectionError(f"Failed to extract payload: {e}") from e

    def is_connected(self) -> bool:
        """实时检查当前内部 WebSocket 流道是否处于具备正常读写的激活状态。

        Returns:
            bool: 完全激活（信道打开状态）返回 True，否则返回 False。
        """
        if self._ws is None:
            return False
            
        return self._ws.state == State.OPEN

    @property
    def websocket(self) -> Optional[ClientConnection]:
        """获取并暴露底层的 WebSocket 原生客户端连接对象。

        Warning: 对于追求封装完备性，外部只应观察或监听；不建议外部直接操作此对象。
        返回该对象主要兼容一些需要在上级代理执行直接心跳探活等特异性长流控制的场景。
        
        Returns:
            Optional[ClientConnection]: 后备所存 WebSocket 纯态连接对象。
        """
        return self._ws
