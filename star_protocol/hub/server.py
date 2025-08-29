"""Hub WebSocket 服务器"""

import asyncio
import websockets
from typing import Optional
from .manager import ConnectionManager
from .router import MessageRouter
from ..protocol import Envelope, EnvelopeType, ClientInfo, ClientType, EventMessage
from ..utils import get_logger, get_config


class HubServer:
    """Hub WebSocket 服务器"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8000,
        max_connections: Optional[int] = None,
    ):
        self.host = host
        self.port = port
        self.max_connections = max_connections or 1000  # 默认最大连接数

        # 核心组件
        self.connection_manager = ConnectionManager()
        self.router = MessageRouter(self.connection_manager)

        # 服务器状态
        self.server: Optional[websockets.WebSocketServer] = None
        self.running = False

        # 监控（可选）
        self._metrics_enabled = False
        self._metrics_collector = None

        self.logger = get_logger("star_protocol.hub.server")

    async def start(self) -> None:
        """启动服务器"""
        if self.running:
            self.logger.warning("服务器已经在运行")
            return

        try:
            self.logger.info(f"启动 Hub 服务器: {self.host}:{self.port}")

            # 启动 WebSocket 服务器
            self.server = await websockets.serve(
                self._handle_client,
                self.host,
                self.port,
                max_size=None,  # 不限制消息大小
                ping_interval=30,  # 30秒ping间隔
                ping_timeout=10,  # 10秒ping超时
                close_timeout=10,  # 10秒关闭超时
            )

            self.running = True
            self.logger.info("Hub 服务器启动成功")

            # 启动心跳检查任务
            asyncio.create_task(self._heartbeat_checker())

        except Exception as e:
            self.logger.error(f"启动服务器失败: {e}")
            raise

    async def stop(self) -> None:
        """停止服务器"""
        if not self.running:
            return

        self.logger.info("停止 Hub 服务器")
        self.running = False

        try:
            # 首先断开所有客户端连接
            connections = self.connection_manager.get_all_connections()
            disconnect_tasks = []

            for client_id, connection in connections.items():
                try:
                    # 发送关闭消息给客户端
                    if not connection.websocket.closed:
                        disconnect_tasks.append(
                            connection.websocket.close(
                                code=1001, reason="Server shutdown"
                            )
                        )
                except Exception as e:
                    self.logger.debug(f"关闭客户端连接 {client_id} 失败: {e}")
                finally:
                    # 移除连接管理器中的连接
                    self.connection_manager.remove_connection(client_id)

            # 等待所有连接关闭
            if disconnect_tasks:
                await asyncio.gather(*disconnect_tasks, return_exceptions=True)

            # 停止 WebSocket 服务器
            if self.server:
                self.server.close()
                await self.server.wait_closed()
                self.server = None

            self.logger.info("Hub 服务器已停止")

        except Exception as e:
            self.logger.error(f"停止服务器时出错: {e}")
        finally:
            # 确保服务器状态被正确设置
            self.running = False

    async def _handle_client(
        self, websocket: websockets.WebSocketServerProtocol
    ) -> None:
        """处理客户端连接

        Args:
            websocket: WebSocket 连接
        """
        client_id = None

        try:
            # 处理客户端注册
            client_id, client_info = await self._handle_client_registration(websocket)
            if not client_id or not client_info:
                return  # 注册失败，连接已关闭

            # 进入消息循环
            async for raw_message in websocket:
                try:
                    envelope = Envelope.from_json(raw_message)

                    # 处理心跳消息
                    if envelope.envelope_type == EnvelopeType.HEARTBEAT:
                        self.connection_manager.update_heartbeat(client_id)
                        continue

                    # 路由消息
                    connection = self.connection_manager.get_connection(client_id)
                    if connection:
                        await self.router.route_envelope(envelope, connection)

                    # 记录指标（如果启用）
                    if self._metrics_enabled and self._metrics_collector:
                        await self._metrics_collector.record_envelope_routed(envelope)

                except Exception as e:
                    self.logger.error(f"处理客户端 {client_id} 消息失败: {e}")

        except websockets.exceptions.ConnectionClosed:
            self.logger.debug(f"客户端 {client_id} 连接已关闭")
        except asyncio.TimeoutError:
            self.logger.warning(f"客户端 {client_id} 连接超时")
        except Exception as e:
            self.logger.error(f"处理客户端 {client_id} 连接失败: {e}")

        finally:
            # 清理连接
            if client_id:
                self.connection_manager.remove_connection(client_id)

                # 记录指标（如果启用）
                if self._metrics_enabled and self._metrics_collector:
                    await self._metrics_collector.record_client_disconnected(client_id)

    async def _handle_client_registration(
        self, websocket: websockets.WebSocketServerProtocol
    ) -> tuple[Optional[str], Optional[ClientInfo]]:
        """处理客户端注册流程

        Args:
            websocket: WebSocket 连接

        Returns:
            tuple[client_id, client_info]: 成功时返回客户端ID和信息，失败时返回 (None, None)
        """
        try:
            # 等待第一条消息来识别客户端 - 应该是 connect event message
            raw_message = await asyncio.wait_for(
                websocket.recv(), timeout=30.0  # 30秒超时
            )

            # 解析并验证 connect event
            client_id, client_info = await self._parse_and_validate_connect_message(
                raw_message, websocket
            )
            if not client_id or not client_info:
                return None, None

            # 执行注册流程
            success = await self._register_client(websocket, client_id, client_info)
            if not success:
                return None, None

            return client_id, client_info

        except asyncio.TimeoutError:
            self.logger.warning("等待客户端连接消息超时")
            await websocket.close(code=1002, reason="Connection timeout")
            return None, None
        except Exception as e:
            self.logger.error(f"客户端注册失败: {e}")
            await websocket.close(code=1011, reason="Registration failed")
            return None, None

    async def _parse_and_validate_connect_message(
        self, raw_message: str, websocket: websockets.WebSocketServerProtocol
    ) -> tuple[Optional[str], Optional[ClientInfo]]:
        """解析和验证连接消息

        Args:
            raw_message: 原始消息
            websocket: WebSocket 连接

        Returns:
            tuple[client_id, client_info]: 成功时返回客户端ID和信息，失败时返回 (None, None)
        """
        try:
            # 解析信封获取客户端ID和连接信息
            envelope = Envelope.from_json(raw_message)
            client_id = envelope.sender

            # 验证第一条消息应该是 connect event
            if envelope.envelope_type != EnvelopeType.MESSAGE:
                await websocket.close(
                    code=1002, reason="First message must be EVENT message"
                )
                self.logger.warning(f"客户端 {client_id} 第一条消息类型错误")
                return None, None

            if (
                not isinstance(envelope.message, EventMessage)
                or envelope.message.event != "connect"
            ):
                await websocket.close(
                    code=1002, reason="First message must be connect event"
                )
                self.logger.warning(f"客户端 {client_id} 第一条消息不是 connect event")
                return None, None

            # 从 connect event 中提取客户端信息
            connect_data = envelope.message.data or {}
            client_info = self._create_client_info_from_connect(client_id, connect_data)

            return client_id, client_info

        except Exception as e:
            self.logger.error(f"解析连接消息失败: {e}")
            await websocket.close(code=1002, reason="Invalid connect message")
            return None, None

    async def _register_client(
        self,
        websocket: websockets.WebSocketServerProtocol,
        client_id: str,
        client_info: ClientInfo,
    ) -> bool:
        """注册客户端

        Args:
            websocket: WebSocket 连接
            client_id: 客户端ID
            client_info: 客户端信息

        Returns:
            bool: 注册是否成功
        """
        try:
            # 检查连接数限制
            if (
                len(self.connection_manager.get_all_connections())
                >= self.max_connections
            ):
                await websocket.close(code=1013, reason="Server overloaded")
                self.logger.warning(f"拒绝连接 {client_id}: 超过最大连接数")
                return False

            # 添加连接
            if not self.connection_manager.add_connection(websocket, client_info):
                await websocket.close(code=1002, reason="Duplicate client ID")
                self.logger.warning(f"拒绝连接 {client_id}: 客户端ID重复")
                return False

            self.logger.info(
                f"客户端连接成功: {client_id} ({client_info.client_type.value})"
            )

            # 设置初始心跳时间
            self.connection_manager.update_heartbeat(client_id)

            # 发送注册成功的 event message 给客户端
            await self._send_registration_success(client_id, client_info)

            # 如果是Agent连接，通知对应的Environment
            if client_info.client_type == ClientType.AGENT and client_info.env_id:
                await self._notify_environment_agent_joined(client_info)

            # 记录指标（如果启用）
            if self._metrics_enabled and self._metrics_collector:
                await self._metrics_collector.record_client_connected(client_info)

            return True

        except Exception as e:
            self.logger.error(f"注册客户端 {client_id} 失败: {e}")
            return False

    async def _heartbeat_checker(self) -> None:
        """心跳检查任务"""
        heartbeat_interval = 60.0  # 60秒心跳间隔

        while self.running:
            try:
                await asyncio.sleep(heartbeat_interval)

                if not self.running:
                    break

                current_time = asyncio.get_event_loop().time()
                timeout_threshold = current_time - heartbeat_interval * 2

                # 检查超时的连接
                connections = self.connection_manager.get_all_connections()
                timeout_clients = []

                for client_id, connection in connections.items():
                    if connection.last_heartbeat < timeout_threshold:
                        timeout_clients.append(client_id)

                # 断开超时的连接
                for client_id in timeout_clients:
                    self.logger.warning(f"客户端 {client_id} 心跳超时，断开连接")
                    connection = self.connection_manager.get_connection(client_id)
                    if connection:
                        try:
                            await connection.websocket.close(
                                code=1001, reason="Heartbeat timeout"
                            )
                        except Exception:
                            pass
                        self.connection_manager.remove_connection(client_id)

            except Exception as e:
                self.logger.error(f"心跳检查出错: {e}")

    def _create_client_info_from_connect(
        self, client_id: str, connect_data: dict
    ) -> ClientInfo:
        """从 connect event 数据创建客户端信息

        Args:
            client_id: 客户端ID
            connect_data: connect event 携带的数据

        Returns:
            客户端信息
        """
        # 从 connect_data 中提取客户端类型
        client_type_str = connect_data.get("client_type", "").lower()

        if client_type_str == "environment":
            client_type = ClientType.ENVIRONMENT
            # 对于环境客户端，env_id 就是环境名称
            env_id = connect_data.get("env_id") or client_id.replace("env_", "")
        elif client_type_str == "human":
            client_type = ClientType.HUMAN
            env_id = connect_data.get("env_id")
        else:
            # 默认为 Agent
            client_type = ClientType.AGENT
            env_id = connect_data.get("env_id")

            # 如果没有指定 env_id，尝试自动推断
            if not env_id:
                env_id = self._infer_env_id_for_agent(client_id)

        # 提取其他元数据
        metadata = connect_data.get("metadata", {})

        return ClientInfo(
            client_id=client_id,
            client_type=client_type,
            env_id=env_id,
            metadata=metadata,
        )

    def _infer_env_id_for_agent(self, client_id: str) -> Optional[str]:
        """为 Agent 推断 env_id

        Args:
            client_id: Agent 客户端ID

        Returns:
            推断出的 env_id
        """
        # 尝试从当前连接的环境中推断
        connections = self.connection_manager.get_all_connections()
        env_connections = [
            conn.client_info.env_id
            for conn in connections.values()
            if conn.client_info.client_type == ClientType.ENVIRONMENT
        ]

        # 如果只有一个环境连接，默认分配给它
        if len(env_connections) == 1:
            return env_connections[0]

        # 如果有多个环境，尝试从客户端ID中匹配
        if len(env_connections) > 1:
            for env_id_candidate in env_connections:
                if env_id_candidate in client_id.lower():
                    return env_id_candidate
            # 如果没有匹配，使用第一个环境作为默认
            return env_connections[0]

        # 特殊情况：demo 相关的 agent 默认分配给 demo_world
        if "demo" in client_id.lower():
            return "demo_world"

        return None

    async def _send_registration_success(
        self, client_id: str, client_info: ClientInfo
    ) -> None:
        """发送注册成功的 event message 给客户端

        Args:
            client_id: 客户端ID
            client_info: 客户端信息
        """
        connection = self.connection_manager.get_connection(client_id)
        if not connection:
            return

        try:
            # 创建注册成功事件消息

            event = EventMessage(
                event="connected",
                data={
                    "client_id": client_id,
                    "client_type": client_info.client_type.value,
                    "env_id": client_info.env_id,
                    "status": "success",
                    "message": "客户端注册成功",
                },
            )

            # 发送注册成功消息给客户端
            envelope = Envelope(
                envelope_type=EnvelopeType.MESSAGE,
                sender="hub",
                recipient=client_id,
                message=event,
            )

            await connection.websocket.send(envelope.to_json())
            self.logger.info(f"已发送注册成功消息给客户端: {client_id}")

        except Exception as e:
            self.logger.error(f"发送注册成功消息失败: {e}")

    async def _notify_environment_agent_joined(self, agent_info: ClientInfo) -> None:
        """通知Environment有新Agent加入

        Args:
            agent_info: Agent的客户端信息
        """
        if not agent_info.env_id:
            self.logger.debug(
                f"Agent {agent_info.client_id} 没有指定 env_id，跳过环境通知"
            )
            return

        # 查找对应的Environment - 环境客户端ID格式为 env_{env_id}
        env_client_id = f"{agent_info.env_id}"
        env_connection = self.connection_manager.get_connection(env_client_id)

        if env_connection:
            try:
                from ..protocol import EventMessage

                event = EventMessage(
                    event="agent_joined",
                    data={
                        "agent_id": agent_info.client_id,
                        "agent_metadata": agent_info.metadata,
                    },
                )

                # 发送通知给Environment
                envelope = Envelope(
                    envelope_type=EnvelopeType.MESSAGE,
                    sender="hub",
                    recipient=env_client_id,
                    message=event,
                )

                await env_connection.websocket.send(envelope.to_json())
                self.logger.info(
                    f"通知Environment {env_client_id} Agent {agent_info.client_id} 已加入"
                )

            except Exception as e:
                self.logger.error(f"通知Environment失败: {e}")
        else:
            self.logger.warning(
                f"未找到环境 {env_client_id} (对应Agent {agent_info.client_id} 的 env_id: {agent_info.env_id})，无法发送Agent加入通知"
            )

    def enable_metrics(self, collector=None) -> None:
        """启用监控

        Args:
            collector: 指标收集器，如果为 None 则使用默认收集器
        """
        self._metrics_enabled = True
        if collector is None:
            from ..monitor import MetricsCollector

            self._metrics_collector = MetricsCollector()
        else:
            self._metrics_collector = collector

    def disable_metrics(self) -> None:
        """禁用监控"""
        self._metrics_enabled = False
        self._metrics_collector = None

    def get_stats(self) -> dict:
        """获取服务器统计信息

        Returns:
            统计信息字典
        """
        connection_stats = self.connection_manager.get_stats()
        return {
            "server": {
                "running": self.running,
                "host": self.host,
                "port": self.port,
                "max_connections": self.max_connections,
            },
            "connections": connection_stats,
        }


# 便捷的启动函数
async def start_hub_server(
    host: str = "localhost", port: int = 8000, max_connections: Optional[int] = None
) -> HubServer:
    """启动 Hub 服务器

    Args:
        host: 监听地址
        port: 监听端口
        max_connections: 最大连接数

    Returns:
        Hub 服务器实例
    """
    server = HubServer(host, port, max_connections)
    await server.start()
    return server
