"""会话和连接管理"""

from dataclasses import dataclass, field
from typing import Dict, Set, Optional, List
from enum import Enum
import time
from starlette.websockets import WebSocket

# 导入必要的模型
from star_protocol.models import Envelope, EnvelopeType, MonitorPayload, MonitorType

import logging

logger = logging.getLogger(__name__)


class SessionState(str, Enum):
    """会话状态"""

    CONNECTED = "connected"  # 已连接，但未加入环境
    IN_ENVIRONMENT = "in_env"  # 已加入环境
    DISCONNECTED = "disconnected"


class ClientRole(str, Enum):
    """客户端角色"""

    AGENT = "agent"
    ENVIRONMENT = "environment"
    HUMAN = "human"
    MONITOR = "monitor"  # 业务监控（接收 monitor 协议消息）
    HUB_MONITOR = "hub_monitor"  # 系统监控（监听所有消息）


@dataclass
class Session:
    """客户端会话"""

    client_id: str
    role: ClientRole
    websocket: WebSocket
    state: SessionState = SessionState.CONNECTED
    current_env: Optional[str] = None
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    message_count: int = 0  # 消息计数
    metadata: dict = field(default_factory=dict)  # 元数据（IP、User-Agent等）

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "client_id": self.client_id,
            "role": self.role.value,
            "state": self.state.value,
            "current_env": self.current_env,
            "connected_at": self.connected_at,
            "uptime": time.time() - self.connected_at,
            "last_heartbeat": self.last_heartbeat,
            "message_count": self.message_count,
            "metadata": self.metadata,
        }


class SessionManager:
    """
    统一的连接管理器

    职责：
    1. 管理所有客户端会话（Session）
    2. 按角色分类管理（agent/environment/human/monitor）
    3. 管理环境和成员关系
    4. 提供查询和统计功能
    """

    def __init__(self, max_connections: int = 1000):
        self.max_connections = max_connections

        # 核心存储：client_id -> Session
        self._sessions: Dict[str, Session] = {}

        # 按角色分类索引：role -> set of client_ids
        self._by_role: Dict[ClientRole, Set[str]] = {
            ClientRole.AGENT: set(),
            ClientRole.ENVIRONMENT: set(),
            ClientRole.HUMAN: set(),
            ClientRole.MONITOR: set(),
            ClientRole.HUB_MONITOR: set(),
        }

        # 环境管理：env_id -> set of client_ids (members)
        self._environments: Dict[str, Set[str]] = {}

        # 反向索引：client_id -> env_id
        self._client_to_env: Dict[str, str] = {}

        # Monitor 功能：哪些 Client 启用了监控
        self._monitored_clients: Dict[str, str] = {}  # {client_id: level}

        # Monitor 功能：订阅关系
        self._subscriptions: Dict[str, Set[str]] = {}  # {client_id: {monitor_ids}}

    # ==================== 会话管理 ====================

    async def create_session(
        self, websocket: WebSocket, client_id: str, role: str
    ) -> Optional[Session]:
        """
        创建新会话

        Args:
            websocket: WebSocket 连接
            client_id: 客户端 ID
            role: 客户端角色

        Returns:
            创建的 Session，如果失败返回 None
        """
        # 检查连接数限制
        if len(self._sessions) >= self.max_connections:
            await websocket.close(code=1008, reason="Max connections reached")
            return None

        # 如果已存在，先移除旧会话
        if client_id in self._sessions:
            await self.remove_session(client_id)

        # 接受连接
        await websocket.accept()

        # 创建会话
        client_role = ClientRole(role)
        session = Session(client_id=client_id, role=client_role, websocket=websocket)

        # 存储会话
        self._sessions[client_id] = session
        self._by_role[client_role].add(client_id)

        # 如果是 Environment 角色，自动创建环境
        if client_role == ClientRole.ENVIRONMENT:
            self._create_environment(client_id)

        return session

    async def remove_session(self, client_id: str) -> None:
        """
        移除会话

        Args:
            client_id: 客户端 ID
        """
        session = self._sessions.get(client_id)
        if not session:
            return

        # 如果在环境中，先离开
        if session.current_env:
            self.leave_environment(client_id)

        # 如果是 Environment 角色，销毁环境
        if session.role == ClientRole.ENVIRONMENT:
            self._destroy_environment(client_id)

        # 清理 Monitor 相关数据
        if session.role == ClientRole.MONITOR:
            self._cleanup_monitor(client_id)
        else:
            self._cleanup_monitored_client(client_id)
        # 关闭 WebSocket
        try:
            await session.websocket.close()
        except Exception:
            pass

        # 从索引中移除
        self._by_role[session.role].discard(client_id)

        # 移除会话
        session.state = SessionState.DISCONNECTED
        del self._sessions[client_id]

    def get_session(self, client_id: str) -> Optional[Session]:
        """
        获取会话

        Args:
            client_id: 客户端 ID

        Returns:
            Session 或 None
        """
        return self._sessions.get(client_id)

    def session_exists(self, client_id: str) -> bool:
        """检查会话是否存在"""
        return client_id in self._sessions

    # ==================== 环境管理 ====================

    def _create_environment(self, env_id: str) -> bool:
        """
        创建环境（内部方法，由 Environment 客户端连接时自动调用）

        Args:
            env_id: 环境 ID（等于 Environment 客户端的 client_id）

        Returns:
            是否成功创建
        """
        if env_id in self._environments:
            return False

        self._environments[env_id] = set()
        return True

    def _destroy_environment(self, env_id: str) -> Set[str]:
        """
        销毁环境（内部方法，由 Environment 客户端断开时自动调用）

        Args:
            env_id: 环境 ID

        Returns:
            被踢出的成员 ID 集合
        """
        if env_id not in self._environments:
            return set()

        # 获取所有成员
        members = self._environments[env_id].copy()

        # 移除所有成员的环境关联
        for client_id in members:
            if client_id in self._client_to_env:
                del self._client_to_env[client_id]

            # 更新会话状态
            session = self.get_session(client_id)
            if session:
                session.state = SessionState.CONNECTED
                session.current_env = None

        # 删除环境
        del self._environments[env_id]

        return members

    def join_environment(self, client_id: str, env_id: str) -> bool:
        """
        客户端加入环境

        Args:
            client_id: 客户端 ID
            env_id: 环境 ID

        Returns:
            是否成功加入
        """
        # 检查环境是否存在
        if env_id not in self._environments:
            return False

        # 检查会话是否存在
        session = self.get_session(client_id)
        if not session:
            return False

        # 如果已在其他环境，先离开
        if session.current_env:
            self.leave_environment(client_id)

        # 加入环境
        self._environments[env_id].add(client_id)
        self._client_to_env[client_id] = env_id

        # 更新会话状态
        session.state = SessionState.IN_ENVIRONMENT
        session.current_env = env_id

        return True

    def leave_environment(self, client_id: str) -> bool:
        """
        客户端离开环境

        Args:
            client_id: 客户端 ID

        Returns:
            是否成功离开
        """
        if client_id not in self._client_to_env:
            return False

        env_id = self._client_to_env[client_id]

        # 从环境中移除
        self._environments[env_id].discard(client_id)
        del self._client_to_env[client_id]

        # 更新会话状态
        session = self.get_session(client_id)
        if session:
            session.state = SessionState.CONNECTED
            session.current_env = None

        return True

    def environment_exists(self, env_id: str) -> bool:
        """检查环境是否存在"""
        return env_id in self._environments

    def get_environment_members(self, env_id: str) -> Set[str]:
        """获取环境成员"""
        return self._environments.get(env_id, set()).copy()

    def get_client_environment(self, client_id: str) -> Optional[str]:
        """获取客户端所在环境"""
        return self._client_to_env.get(client_id)

    # ==================== 查询和统计 ====================

    def get_total_sessions(self) -> int:
        """获取总会话数"""
        return len(self._sessions)

    def get_sessions_by_role(self, role: ClientRole) -> List[Session]:
        """获取指定角色的所有会话"""
        return [
            self._sessions[client_id]
            for client_id in self._by_role[role]
            if client_id in self._sessions
        ]

    def get_all_environments(self) -> List[str]:
        """获取所有环境 ID"""
        return list(self._environments.keys())

    def get_environments_info(self) -> List[dict]:
        """获取所有环境详情"""
        return [
            {"env_id": env_id, "member_count": len(members), "members": list(members)}
            for env_id, members in self._environments.items()
        ]

    def get_environment_info(self, env_id: str) -> Optional[dict]:
        """获取单个环境的详细信息"""
        if env_id not in self._environments:
            return None

        members = self._environments[env_id]
        member_details = []

        for member_id in members:
            session = self._sessions.get(member_id)
            if session:
                member_details.append(
                    {
                        "client_id": session.client_id,
                        "role": session.role.value,
                        "state": session.state.value,
                        "joined_at": session.connected_at,
                        "message_count": session.message_count,
                    }
                )

        # 获取环境创建时间（Environment 客户端的连接时间）
        env_session = self._sessions.get(env_id)
        created_at = env_session.connected_at if env_session else time.time()

        return {
            "env_id": env_id,
            "state": "active",
            "member_count": len(members),
            "members": member_details,
            "created_at": created_at,
            "uptime": time.time() - created_at,
        }

    def get_statistics(self) -> dict:
        """获取统计信息"""
        return {
            "total_sessions": len(self._sessions),
            "by_role": {
                "agents": len(self._by_role[ClientRole.AGENT]),
                "environments": len(self._by_role[ClientRole.ENVIRONMENT]),
                "humans": len(self._by_role[ClientRole.HUMAN]),
                "monitors": len(self._by_role[ClientRole.MONITOR]),
                "hub_monitors": len(self._by_role[ClientRole.HUB_MONITOR]),
            },
            "environments": {
                "total": len(self._environments),
                "details": self.get_environments_info(),
            },
        }

    # ==================== Monitor 管理 ====================

    def enable_monitoring(self, client_id: str, level: str) -> bool:
        """
        启用客户端监控

        Args:
            client_id: 客户端 ID
            level: 监控级别

        Returns:
            是否成功启用
        """
        if client_id not in self._sessions:
            return False

        self._monitored_clients[client_id] = level
        logger.info(f"Client {client_id} enabled monitoring (level: {level})")
        return True

    def disable_monitoring(self, client_id: str) -> bool:
        """
        禁用客户端监控

        Args:
            client_id: 客户端 ID

        Returns:
            是否成功禁用
        """
        if client_id not in self._monitored_clients:
            return False

        self._monitored_clients.pop(client_id, None)
        logger.info(f"Client {client_id} disabled monitoring")
        return True

    def is_monitored(self, client_id: str) -> bool:
        """检查客户端是否启用了监控"""
        return client_id in self._monitored_clients

    def subscribe_monitor(self, monitor_id: str, target_client_id: str) -> bool:
        """
        Monitor 订阅客户端

        Args:
            monitor_id: Monitor ID
            target_client_id: 目标客户端 ID

        Returns:
            是否成功订阅
        """
        # 检查 Monitor 和目标客户端是否存在
        if monitor_id not in self._sessions or target_client_id not in self._sessions:
            return False

        # 添加订阅关系
        if target_client_id not in self._subscriptions:
            self._subscriptions[target_client_id] = set()

        self._subscriptions[target_client_id].add(monitor_id)
        logger.info(f"Monitor {monitor_id} subscribed to {target_client_id}")
        return True

    def unsubscribe_monitor(self, monitor_id: str, target_client_id: str) -> bool:
        """
        Monitor 取消订阅客户端

        Args:
            monitor_id: Monitor ID
            target_client_id: 目标客户端 ID

        Returns:
            是否成功取消订阅
        """
        if target_client_id not in self._subscriptions:
            return False

        self._subscriptions[target_client_id].discard(monitor_id)

        # 如果没有订阅者了，删除键
        if not self._subscriptions[target_client_id]:
            del self._subscriptions[target_client_id]

        logger.info(f"Monitor {monitor_id} unsubscribed from {target_client_id}")
        return True

    def get_subscribers(self, client_id: str) -> Set[str]:
        """
        获取订阅某个客户端的所有 Monitor

        Args:
            client_id: 客户端 ID

        Returns:
            Monitor ID 集合
        """
        return self._subscriptions.get(client_id, set()).copy()

    async def forward_monitor_data(self, client_id: str, name: str, data: dict) -> None:
        """
        转发监控数据给订阅的 Monitor (仅限 MONITOR 角色，不送给 HUB_MONITOR)

        Args:
            client_id: 被监控的客户端 ID
            name: 监控数据类型
            data: 监控数据内容
        """
        # 检查是否有 Monitor 订阅此客户端
        if client_id not in self._subscriptions:
            return

        # 构建转发消息
        envelope = Envelope(
            type=EnvelopeType.MONITOR,
            sender=client_id,  # 保持原始客户端 ID
            recipient="",  # 稍后填充
            payload=MonitorPayload(
                type=MonitorType.DATA,
                content={
                    "name": name,
                    "data": data,
                    "timestamp": int(time.time() * 1000),
                },
            ),
        )

        # 转发给所有订阅的 Monitor
        for monitor_id in self._subscriptions[client_id]:
            session = self.get_session(monitor_id)
            if session and session.role == ClientRole.MONITOR:
                envelope.recipient = monitor_id
                try:
                    await session.websocket.send_text(envelope.model_dump_json())
                    logger.debug(f"Forwarded {name} from {client_id} to {monitor_id}")
                except Exception as e:
                    logger.warning(f"Failed to forward to monitor {monitor_id}: {e}")
            elif session and session.role == ClientRole.HUB_MONITOR:
                # HUB_MONITOR 不通过订阅方式接收 MonitorDataContent 消息，以避免循环
                pass
            else:
                logger.warning(
                    f"Monitor {monitor_id} session not found or role mismatch"
                )

    def _cleanup_monitored_client(self, client_id: str) -> None:
        """
        清理被监控客户端的数据（内部方法）

        Args:
            client_id: 客户端 ID
        """
        # 移除监控状态
        self._monitored_clients.pop(client_id, None)

        # 移除订阅关系
        self._subscriptions.pop(client_id, None)

        logger.info(f"Cleaned up monitoring data for {client_id}")

    def _cleanup_monitor(self, monitor_id: str) -> None:
        """
        清理 Monitor 的订阅数据（内部方法）

        Args:
            monitor_id: Monitor ID
        """
        # 从所有订阅中移除此 Monitor
        for client_id in list(self._subscriptions.keys()):
            self._subscriptions[client_id].discard(monitor_id)
            if not self._subscriptions[client_id]:
                del self._subscriptions[client_id]

        logger.info(f"Cleaned up subscriptions for monitor {monitor_id}")
