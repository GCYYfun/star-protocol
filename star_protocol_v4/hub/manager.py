"""Hub 连接管理器"""

import asyncio
import websockets
from typing import Dict, Optional, Set
from ..protocol import Envelope, ClientInfo, ClientType
from ..utils import get_logger


class Connection:
    """客户端连接"""

    def __init__(
        self, websocket: websockets.WebSocketServerProtocol, client_info: ClientInfo
    ):
        self.websocket = websocket
        self.client_info = client_info
        self.connected = True
        self.last_heartbeat = asyncio.get_event_loop().time()

    async def send_envelope(self, envelope: Envelope) -> bool:
        """发送信封到客户端

        Args:
            envelope: 要发送的信封

        Returns:
            发送是否成功
        """
        if not self.connected:
            return False

        try:
            json_str = envelope.to_json()
            await self.websocket.send(json_str)
            return True
        except Exception:
            self.connected = False
            return False

    def update_heartbeat(self) -> None:
        """更新心跳时间"""
        self.last_heartbeat = asyncio.get_event_loop().time()


class ConnectionManager:
    """连接管理器"""

    def __init__(self):
        # 连接映射：client_id -> Connection
        self._connections: Dict[str, Connection] = {}

        # 类型索引：client_type -> Set[client_id]
        self._type_index: Dict[ClientType, Set[str]] = {
            ClientType.AGENT: set(),
            ClientType.ENVIRONMENT: set(),
            ClientType.HUMAN: set(),
        }

        # 环境索引：env_id -> Set[client_id]
        self._env_index: Dict[str, Set[str]] = {}

        self.logger = get_logger("star_protocol.hub.manager")

    def add_connection(
        self, websocket: websockets.WebSocketServerProtocol, client_info: ClientInfo
    ) -> bool:
        """添加连接

        Args:
            websocket: WebSocket 连接
            client_info: 客户端信息

        Returns:
            是否添加成功
        """
        client_id = client_info.client_id

        # 检查重复连接
        if client_id in self._connections:
            self.logger.warning(f"客户端 {client_id} 已连接，拒绝重复连接")
            return False

        # 创建连接对象
        connection = Connection(websocket, client_info)

        # 添加到连接映射
        self._connections[client_id] = connection

        # 添加到类型索引
        self._type_index[client_info.client_type].add(client_id)

        # 添加到环境索引（如果有环境ID）
        if client_info.env_id:
            if client_info.env_id not in self._env_index:
                self._env_index[client_info.env_id] = set()
            self._env_index[client_info.env_id].add(client_id)

        self.logger.info(f"客户端连接: {client_id} ({client_info.client_type.value})")
        return True

    def remove_connection(self, client_id: str) -> bool:
        """移除连接

        Args:
            client_id: 客户端ID

        Returns:
            是否移除成功
        """
        if client_id not in self._connections:
            return False

        connection = self._connections[client_id]
        client_info = connection.client_info

        # 从连接映射移除
        del self._connections[client_id]

        # 从类型索引移除
        self._type_index[client_info.client_type].discard(client_id)

        # 从环境索引移除
        if client_info.env_id and client_info.env_id in self._env_index:
            self._env_index[client_info.env_id].discard(client_id)
            # 如果环境没有客户端了，删除环境索引
            if not self._env_index[client_info.env_id]:
                del self._env_index[client_info.env_id]

        self.logger.info(f"客户端断开: {client_id}")
        return True

    def get_connection(self, client_id: str) -> Optional[Connection]:
        """获取连接

        Args:
            client_id: 客户端ID

        Returns:
            连接对象，如果不存在返回 None
        """
        return self._connections.get(client_id)

    def get_connections_by_type(self, client_type: ClientType) -> Dict[str, Connection]:
        """根据类型获取连接

        Args:
            client_type: 客户端类型

        Returns:
            连接字典
        """
        client_ids = self._type_index.get(client_type, set())
        return {
            client_id: self._connections[client_id]
            for client_id in client_ids
            if client_id in self._connections
        }

    def get_connections_by_env(self, env_id: str) -> Dict[str, Connection]:
        """根据环境ID获取连接

        Args:
            env_id: 环境ID

        Returns:
            连接字典
        """
        client_ids = self._env_index.get(env_id, set())
        return {
            client_id: self._connections[client_id]
            for client_id in client_ids
            if client_id in self._connections
        }

    def get_all_connections(self) -> Dict[str, Connection]:
        """获取所有连接

        Returns:
            所有连接的字典
        """
        return self._connections.copy()

    def update_heartbeat(self, client_id: str) -> bool:
        """更新客户端心跳

        Args:
            client_id: 客户端ID

        Returns:
            是否更新成功
        """
        connection = self._connections.get(client_id)
        if connection:
            connection.update_heartbeat()
            return True
        return False

    def get_stats(self) -> Dict[str, int]:
        """获取连接统计

        Returns:
            统计信息字典
        """
        return {
            "total": len(self._connections),
            "agents": len(self._type_index[ClientType.AGENT]),
            "environments": len(self._type_index[ClientType.ENVIRONMENT]),
            "humans": len(self._type_index[ClientType.HUMAN]),
            "env_count": len(self._env_index),
        }
