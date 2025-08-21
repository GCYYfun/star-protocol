"""
Star Protocol 会话管理

管理客户端连接、会话状态和认证信息
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
import websockets
from websockets.server import WebSocketServerProtocol
from websockets.exceptions import ConnectionClosed

from ..protocol import ClientInfo, ClientType


@dataclass
class Session:
    """客户端会话信息"""

    client_info: ClientInfo
    websocket: WebSocketServerProtocol
    connected_at: datetime = field(default_factory=datetime.now)
    is_authenticated: bool = False
    last_heartbeat: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, any] = field(default_factory=dict)

    def __post_init__(self):
        self.session_id = f"{self.client_info.type.value}_{self.client_info.id}"

    def is_alive(self) -> bool:
        """检查连接是否活跃"""
        # 在新版本的 websockets 中使用 state 属性
        from websockets import State

        return self.websocket.state == State.OPEN

    def update_heartbeat(self) -> None:
        """更新心跳时间"""
        self.last_heartbeat = datetime.now()


class SessionManager:
    """会话管理器"""

    def __init__(self):
        # 会话存储：client_id -> Session
        self.sessions: Dict[str, Session] = {}

        # 按类型分组的客户端 ID
        self.agents: Set[str] = set()
        self.environments: Set[str] = set()
        self.humans: Set[str] = set()

        # 环境到客户端的映射
        self.env_clients: Dict[str, Set[str]] = {}  # env_id -> {client_ids}

        self.logger = logging.getLogger("session_manager")

    def register_session(
        self, client_info: ClientInfo, websocket: WebSocketServerProtocol
    ) -> Session:
        """注册新会话"""
        client_id = client_info.id

        # 如果已存在会话，先清理
        if client_id in self.sessions:
            self.logger.warning(
                f"Client {client_id} already has a session, replacing..."
            )
            self.unregister_session(client_id)

        # 创建新会话
        session = Session(client_info, websocket)
        self.sessions[client_id] = session

        # 按类型分组
        if client_info.type == ClientType.AGENT:
            self.agents.add(client_id)
        elif client_info.type == ClientType.ENVIRONMENT:
            self.environments.add(client_id)
        elif client_info.type == ClientType.HUMAN:
            self.humans.add(client_id)

        self.logger.info(f"Registered session for {client_info.type.value} {client_id}")
        return session

    def unregister_session(self, client_id: str) -> bool:
        """注销会话"""
        if client_id not in self.sessions:
            return False

        session = self.sessions.pop(client_id)
        client_type = session.client_info.type

        # 从分组中移除
        if client_type == ClientType.AGENT:
            self.agents.discard(client_id)
        elif client_type == ClientType.ENVIRONMENT:
            self.environments.discard(client_id)
        elif client_type == ClientType.HUMAN:
            self.humans.discard(client_id)

        # 从环境映射中移除
        for env_id, clients in self.env_clients.items():
            clients.discard(client_id)

        # 清理空的环境映射
        self.env_clients = {
            env_id: clients for env_id, clients in self.env_clients.items() if clients
        }

        self.logger.info(f"Unregistered session for {client_type.value} {client_id}")
        return True

    def get_session(self, client_id: str) -> Optional[Session]:
        """获取会话"""
        return self.sessions.get(client_id)

    def get_websocket(self, client_id: str) -> Optional[WebSocketServerProtocol]:
        """获取 WebSocket 连接"""
        session = self.get_session(client_id)
        return session.websocket if session else None

    def is_connected(self, client_id: str) -> bool:
        """检查客户端是否连接"""
        session = self.get_session(client_id)
        return session is not None and session.is_alive()

    def is_authenticated(self, client_id: str) -> bool:
        """检查客户端是否已认证"""
        session = self.get_session(client_id)
        return session is not None and session.is_authenticated

    def set_authenticated(self, client_id: str, authenticated: bool = True) -> bool:
        """设置客户端认证状态"""
        session = self.get_session(client_id)
        if session:
            session.is_authenticated = authenticated
            return True
        return False

    def update_heartbeat(self, client_id: str) -> bool:
        """更新客户端心跳"""
        session = self.get_session(client_id)
        if session:
            session.update_heartbeat()
            return True
        return False

    def set_session_metadata(self, client_id: str, key: str, value: any) -> bool:
        """设置会话元数据"""
        session = self.get_session(client_id)
        if session:
            session.metadata[key] = value
            return True
        return False

    def get_session_metadata(self, client_id: str, key: str) -> any:
        """获取会话元数据"""
        session = self.get_session(client_id)
        if session:
            return session.metadata.get(key)
        return None

    # 环境管理
    def add_client_to_env(self, client_id: str, env_id: str) -> None:
        """将客户端添加到环境"""
        if env_id not in self.env_clients:
            self.env_clients[env_id] = set()
        self.env_clients[env_id].add(client_id)

        # 在会话元数据中记录环境
        self.set_session_metadata(client_id, "env_id", env_id)

    def remove_client_from_env(self, client_id: str, env_id: str) -> None:
        """从环境中移除客户端"""
        if env_id in self.env_clients:
            self.env_clients[env_id].discard(client_id)
            if not self.env_clients[env_id]:
                del self.env_clients[env_id]

    def get_env_clients(self, env_id: str) -> Set[str]:
        """获取环境中的所有客户端"""
        return self.env_clients.get(env_id, set()).copy()

    def get_client_env(self, client_id: str) -> Optional[str]:
        """获取客户端所在的环境"""
        return self.get_session_metadata(client_id, "env_id")

    # 消息发送
    async def send_to_client(self, client_id: str, message: str) -> bool:
        """向指定客户端发送消息"""
        websocket = self.get_websocket(client_id)
        if not websocket:
            self.logger.warning(f"Client {client_id} not found or not connected")
            return False

        try:
            await websocket.send(message)
            return True
        except ConnectionClosed:
            self.logger.info(f"Connection to {client_id} is closed")
            self.unregister_session(client_id)
            return False
        except Exception as e:
            self.logger.error(f"Error sending message to {client_id}: {e}")
            return False

    async def broadcast_to_env(
        self, env_id: str, message: str, exclude: Optional[Set[str]] = None
    ) -> int:
        """向环境中的所有客户端广播消息"""
        clients = self.get_env_clients(env_id)
        if exclude:
            clients -= exclude

        sent_count = 0
        for client_id in clients:
            if await self.send_to_client(client_id, message):
                sent_count += 1

        return sent_count

    async def broadcast_to_type(
        self, client_type: ClientType, message: str, exclude: Optional[Set[str]] = None
    ) -> int:
        """向指定类型的所有客户端广播消息"""
        if client_type == ClientType.AGENT:
            clients = self.agents.copy()
        elif client_type == ClientType.ENVIRONMENT:
            clients = self.environments.copy()
        elif client_type == ClientType.HUMAN:
            clients = self.humans.copy()
        else:
            return 0

        if exclude:
            clients -= exclude

        sent_count = 0
        for client_id in clients:
            if await self.send_to_client(client_id, message):
                sent_count += 1

        return sent_count

    async def broadcast_to_all(
        self, message: str, exclude: Optional[Set[str]] = None
    ) -> int:
        """向所有客户端广播消息"""
        clients = set(self.sessions.keys())
        if exclude:
            clients -= exclude

        sent_count = 0
        for client_id in clients:
            if await self.send_to_client(client_id, message):
                sent_count += 1

        return sent_count

    # 查询方法
    def get_agents(self) -> List[str]:
        """获取所有 Agent 列表"""
        return list(self.agents)

    def get_environments(self) -> List[str]:
        """获取所有环境列表"""
        return list(self.environments)

    def get_humans(self) -> List[str]:
        """获取所有人类用户列表"""
        return list(self.humans)

    def get_all_clients(self) -> List[str]:
        """获取所有客户端列表"""
        return list(self.sessions.keys())

    def get_session_count(self) -> int:
        """获取会话总数"""
        return len(self.sessions)

    def get_env_count(self) -> int:
        """获取活跃环境数量"""
        return len(self.env_clients)

    # 清理方法
    async def disconnect_client(self, client_id: str) -> bool:
        """断开客户端连接"""
        websocket = self.get_websocket(client_id)
        if websocket:
            try:
                await websocket.close()
                return True
            except Exception as e:
                self.logger.error(f"Error disconnecting client {client_id}: {e}")
        return False

    async def disconnect_all_clients(self) -> None:
        """断开所有客户端连接"""
        clients = list(self.sessions.keys())
        for client_id in clients:
            await self.disconnect_client(client_id)

    def cleanup_dead_sessions(self) -> int:
        """清理已断开的会话"""
        dead_sessions = []

        for client_id, session in self.sessions.items():
            if not session.is_alive():
                dead_sessions.append(client_id)

        for client_id in dead_sessions:
            self.unregister_session(client_id)

        if dead_sessions:
            self.logger.info(f"Cleaned up {len(dead_sessions)} dead sessions")

        return len(dead_sessions)

    def get_session_info(self, client_id: str) -> Optional[Dict[str, any]]:
        """获取会话详细信息"""
        session = self.get_session(client_id)
        if not session:
            return None

        return {
            "client_id": client_id,
            "client_type": session.client_info.type.value,
            "connected_at": session.connected_at.isoformat(),
            "is_authenticated": session.is_authenticated,
            "last_heartbeat": session.last_heartbeat.isoformat(),
            "is_alive": session.is_alive(),
            "env_id": self.get_client_env(client_id),
            "metadata": session.metadata.copy(),
        }
