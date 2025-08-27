"""Hub 消息路由器"""

from typing import Dict
from .manager import ConnectionManager, Connection
from ..protocol import Envelope, EnvelopeType, MessageType, ClientType
from ..protocol import ActionMessage, OutcomeMessage, EventMessage, StreamMessage
from ..utils import get_logger


class MessageRouter:
    """消息路由器"""

    def __init__(self, connection_manager: ConnectionManager):
        self.connection_manager = connection_manager
        self.logger = get_logger("star_protocol.hub.router")

    async def route_envelope(
        self, envelope: Envelope, sender_connection: Connection
    ) -> bool:
        """路由信封

        Args:
            envelope: 要路由的信封
            sender_connection: 发送者连接

        Returns:
            是否路由成功
        """
        try:
            # 更新发送者心跳
            sender_connection.update_heartbeat()

            # 记录消息
            self.logger.debug(
                f"路由信封: {envelope.envelope_type.value} "
                f"from {envelope.sender} "
                f"to {envelope.recipient or 'broadcast'}"
            )

            # 根据信封类型和接收者路由
            if envelope.recipient and envelope.recipient != "broadcast":
                # 点对点消息
                return await self._route_to_specific_client(envelope)
            else:
                # 广播消息
                return await self._route_broadcast(envelope)

        except Exception as e:
            self.logger.error(f"路由信封失败: {e}")
            return False

    async def _route_to_specific_client(self, envelope: Envelope) -> bool:
        """路由到特定客户端

        Args:
            envelope: 信封

        Returns:
            是否路由成功
        """
        recipient = envelope.recipient
        connection = self.connection_manager.get_connection(recipient)

        if not connection:
            self.logger.warning(f"目标客户端不存在: {recipient}")
            return False

        success = await connection.send_envelope(envelope)
        if not success:
            # 连接已断开，清理连接
            self.connection_manager.remove_connection(recipient)
            self.logger.warning(f"目标客户端连接已断开: {recipient}")

        return success

    async def _route_broadcast(self, envelope: Envelope) -> bool:
        """广播消息

        Args:
            envelope: 信封

        Returns:
            是否至少发送给一个客户端
        """
        # 根据信封类型和消息类型决定广播范围
        target_connections = self._get_broadcast_targets(envelope)

        if not target_connections:
            self.logger.debug("没有广播目标")
            return False

        # 发送给所有目标
        success_count = 0
        failed_clients = []

        for client_id, connection in target_connections.items():
            # 不发送给自己
            if client_id == envelope.sender:
                continue

            success = await connection.send_envelope(envelope)
            if success:
                success_count += 1
            else:
                failed_clients.append(client_id)

        # 清理失败的连接
        for client_id in failed_clients:
            self.connection_manager.remove_connection(client_id)

        self.logger.debug(f"广播完成: 成功 {success_count}，失败 {len(failed_clients)}")
        return success_count > 0

    def _get_broadcast_targets(self, envelope: Envelope) -> Dict[str, Connection]:
        """获取广播目标

        Args:
            envelope: 信封

        Returns:
            目标连接字典
        """
        # 对于心跳和错误信封，通常不需要广播
        if envelope.envelope_type in [EnvelopeType.HEARTBEAT, EnvelopeType.ERROR]:
            return {}

        # 对于消息信封，根据消息类型决定广播范围
        if envelope.envelope_type == EnvelopeType.MESSAGE:
            return self._get_message_broadcast_targets(envelope)

        # 默认不广播
        return {}

    def _get_message_broadcast_targets(
        self, envelope: Envelope
    ) -> Dict[str, Connection]:
        """获取消息广播目标

        Args:
            envelope: 消息信封

        Returns:
            目标连接字典
        """
        message = envelope.message
        sender_id = envelope.sender
        sender_connection = self.connection_manager.get_connection(sender_id)

        if not sender_connection:
            return {}

        sender_info = sender_connection.client_info

        # 根据消息类型决定广播范围
        if isinstance(message, EventMessage):
            # 事件消息：根据发送者类型决定广播范围
            if sender_info.client_type == ClientType.ENVIRONMENT:
                # 环境事件：发送给同环境的所有客户端
                if sender_info.env_id:
                    return self.connection_manager.get_connections_by_env(
                        sender_info.env_id
                    )
                else:
                    # 没有环境ID，发送给所有客户端
                    return self.connection_manager.get_all_connections()

            elif sender_info.client_type == ClientType.HUMAN:
                # 人类观察者事件：发送给所有客户端
                return self.connection_manager.get_all_connections()

            else:
                # Agent 事件：发送给同环境的其他客户端
                if sender_info.env_id:
                    return self.connection_manager.get_connections_by_env(
                        sender_info.env_id
                    )

        elif isinstance(message, StreamMessage):
            # 流消息：根据发送者类型决定
            if sender_info.client_type == ClientType.HUMAN:
                # 人类流数据：发送给所有客户端
                return self.connection_manager.get_all_connections()
            elif sender_info.env_id:
                # 其他流数据：发送给同环境客户端
                return self.connection_manager.get_connections_by_env(
                    sender_info.env_id
                )

        # ACTION 和 OUTCOME 消息通常是点对点的，不广播
        # 但如果明确要求广播，则广播给同环境的客户端
        elif isinstance(message, (ActionMessage, OutcomeMessage)):
            if sender_info.env_id:
                # 发送给同环境的其他类型客户端
                env_connections = self.connection_manager.get_connections_by_env(
                    sender_info.env_id
                )
                # 过滤掉同类型的客户端（避免 Agent 向 Agent 广播 ACTION）
                return {
                    client_id: conn
                    for client_id, conn in env_connections.items()
                    if conn.client_info.client_type != sender_info.client_type
                }

        # 默认不广播
        return {}
