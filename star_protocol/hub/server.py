"""
Star Protocol Hub 服务器

WebSocket 服务器实现，管理所有客户端连接和消息路由
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Set
import websockets
from websockets.server import WebSocketServerProtocol
from websockets.exceptions import ConnectionClosed, WebSocketException

from ..protocol import (
    ClientInfo,
    ClientType,
    Message,
    MessageParser,
    MessageValidationService,
    ValidationError,
    PermissionError,
)
from .session import SessionManager
from .router import MessageRouter
from .auth import AuthenticationService


class StarHubServer:
    """Star Protocol Hub 服务器"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8765,
        enable_auth: bool = False,
        enable_validation: bool = True,
    ):
        self.host = host
        self.port = port
        self.enable_auth = enable_auth
        self.enable_validation = enable_validation

        # 核心组件
        self.session_manager = SessionManager()
        self.message_router = MessageRouter(self.session_manager)
        self.auth_service = AuthenticationService() if enable_auth else None
        self.validator = MessageValidationService() if enable_validation else None

        # 服务器状态
        self.is_running = False
        self.websocket_server: Optional[websockets.WebSocketServer] = None

        # 日志
        self.logger = logging.getLogger("star_hub_server")

        # 统计信息
        self.stats = {
            "total_connections": 0,
            "active_connections": 0,
            "messages_processed": 0,
            "errors": 0,
        }

    async def start(self) -> None:
        """启动服务器"""
        if self.is_running:
            self.logger.warning("Server is already running")
            return

        try:
            self.logger.info(f"Starting Star Hub Server on {self.host}:{self.port}")

            # 启动 WebSocket 服务器
            self.websocket_server = await websockets.serve(
                self._handle_client_connection,
                self.host,
                self.port,
                ping_interval=30,
                ping_timeout=10,
            )

            self.is_running = True
            self.logger.info("Server started successfully")

        except Exception as e:
            self.logger.error(f"Failed to start server: {e}")
            raise

    async def stop(self) -> None:
        """停止服务器"""
        if not self.is_running:
            return

        self.logger.info("Stopping server...")
        self.is_running = False

        # 关闭所有客户端连接
        await self.session_manager.disconnect_all_clients()

        # 关闭 WebSocket 服务器
        if self.websocket_server:
            self.websocket_server.close()
            await self.websocket_server.wait_closed()

        self.logger.info("Server stopped")

    async def _handle_client_connection(
        self, websocket: WebSocketServerProtocol
    ) -> None:
        """处理客户端连接"""
        client_id = None

        try:
            # 从 WebSocket 对象获取路径信息
            # 在新版本的 websockets 中，路径信息在 request.path 中
            path = websocket.request.path

            # 解析连接路径获取客户端信息
            client_info = self._parse_connection_path(path)
            if not client_info:
                await websocket.close(code=4000, reason="Invalid connection path")
                return

            client_id = client_info.id
            self.logger.info(f"New connection: {client_info.type.value} {client_id}")

            # 更新统计信息
            self.stats["total_connections"] += 1
            self.stats["active_connections"] += 1

            # 注册会话
            self.session_manager.register_session(client_info, websocket)

            # 发送连接确认
            await self._send_connection_ack(websocket, client_info)

            # 处理消息循环
            await self._message_loop(websocket, client_info)

        except ConnectionClosed:
            self.logger.info(f"Client {client_id} disconnected")
        except WebSocketException as e:
            self.logger.error(f"WebSocket error for client {client_id}: {e}")
        except Exception as e:
            self.logger.error(f"Error handling client {client_id}: {e}")
            self.stats["errors"] += 1

        finally:
            # 清理会话
            if client_id:
                self.session_manager.unregister_session(client_id)
                self.stats["active_connections"] -= 1
                self.logger.info(f"Client {client_id} session cleaned up")

    def _parse_connection_path(self, path: str) -> Optional[ClientInfo]:
        """解析连接路径获取客户端信息"""
        # 路径格式:
        # /env/{env_id}/agent/{agent_id}  - Agent 连接
        # /env/{env_id}                   - Environment 连接
        # /human/{human_id}               - Human 连接
        # /ws/metaverse                   - 通用连接

        parts = [p for p in path.split("/") if p]

        if len(parts) >= 4 and parts[0] == "env" and parts[2] == "agent":
            # Agent 连接
            return ClientInfo(id=parts[3], type=ClientType.AGENT)

        elif len(parts) >= 2 and parts[0] == "env":
            # Environment 连接
            return ClientInfo(id=parts[1], type=ClientType.ENVIRONMENT)

        elif len(parts) >= 2 and parts[0] == "human":
            # Human 连接
            return ClientInfo(id=parts[1], type=ClientType.HUMAN)

        elif len(parts) >= 2 and parts[0] == "ws" and parts[1] == "metaverse":
            # 通用连接 - 需要后续识别
            return ClientInfo(id="unknown", type=ClientType.HUB)

        return None

    async def _send_connection_ack(
        self, websocket: WebSocketServerProtocol, client_info: ClientInfo
    ) -> None:
        """发送连接确认 - 使用heartbeat响应"""
        hub_info = ClientInfo(id="server", type=ClientType.HUB)

        # 发送heartbeat响应而不是connect消息
        ack_message = Message(
            type="heartbeat",
            sender=hub_info,
            recipient=client_info,
            payload={
                "pong": True,
                "status": "connected",
                "server_time": self._get_current_timestamp(),
                "client_id": client_info.id,
                "client_type": client_info.type.value,
            },
        )

        await websocket.send(MessageParser.to_json(ack_message))

    async def _message_loop(
        self, websocket: WebSocketServerProtocol, client_info: ClientInfo
    ) -> None:
        """消息处理循环"""
        while True:
            try:
                # 接收消息
                message_json = await websocket.recv()
                await self._process_message(message_json, client_info)

            except ConnectionClosed:
                break
            except Exception as e:
                self.logger.error(f"Error in message loop for {client_info.id}: {e}")
                await asyncio.sleep(0.1)

    async def _process_message(
        self, message_json: str, sender_info: ClientInfo
    ) -> None:
        """处理接收到的消息"""
        try:
            # 更新统计
            self.stats["messages_processed"] += 1

            # 解析消息
            message = MessageParser.parse_json(message_json)

            # 更新发送者信息（防止伪造）
            message.sender = sender_info

            self.logger.debug(
                f"Processing message from {sender_info.id}: {message.type}"
            )

            # 验证消息
            if self.validator:
                try:
                    self.validator.validate_message(message.to_dict())
                except (ValidationError, PermissionError) as e:
                    self.logger.warning(f"Message validation failed: {e}")
                    await self._send_error_response(
                        sender_info, "validation_error", str(e)
                    )
                    return

            # 认证检查
            if self.auth_service and not await self._check_authentication(message):
                await self._send_error_response(
                    sender_info, "authentication_error", "Authentication required"
                )
                return

            # 路由消息
            await self.message_router.route_message(message)

        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
            self.stats["errors"] += 1
            await self._send_error_response(
                sender_info, "processing_error", "Message processing failed"
            )

    async def _check_authentication(self, message: Message) -> bool:
        """检查消息认证"""
        if not self.auth_service:
            return True

        # 心跳消息可能包含认证信息
        if message.type == "heartbeat":
            return await self.auth_service.authenticate_message(message)

        # 检查会话是否已认证
        return self.session_manager.is_authenticated(message.sender.id)

    async def _send_error_response(
        self, client_info: ClientInfo, error_type: str, error_message: str
    ) -> None:
        """发送错误响应"""
        hub_info = ClientInfo(id="server", type=ClientType.HUB)

        error_response = Message(
            type="error",
            sender=hub_info,
            recipient=client_info,
            payload={
                "error_code": "HUB001",
                "error_type": error_type,
                "message": error_message,
                "details": {},
            },
        )

        await self.session_manager.send_to_client(
            client_info.id, MessageParser.to_json(error_response)
        )

    def _get_current_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime

        return datetime.now().isoformat()

    # 服务器管理 API
    def get_stats(self) -> Dict[str, int]:
        """获取服务器统计信息"""
        return {
            **self.stats,
            "uptime_seconds": self._get_uptime_seconds(),
            "active_environments": len(self.session_manager.get_environments()),
            "active_agents": len(self.session_manager.get_agents()),
            "active_humans": len(self.session_manager.get_humans()),
        }

    def get_client_list(self) -> Dict[str, List[str]]:
        """获取客户端列表"""
        return {
            "agents": self.session_manager.get_agents(),
            "environments": self.session_manager.get_environments(),
            "humans": self.session_manager.get_humans(),
        }

    def _get_uptime_seconds(self) -> int:
        """获取运行时间（秒）"""
        # 简单实现，实际应该记录启动时间
        return 0

    # 上下文管理器支持
    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()


# 服务器启动辅助函数
async def run_server(
    host: str = "localhost",
    port: int = 8765,
    enable_auth: bool = False,
    enable_validation: bool = True,
) -> None:
    """运行服务器"""
    server = StarHubServer(host, port, enable_auth, enable_validation)

    try:
        await server.start()

        # 保持运行
        while server.is_running:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logging.info("Received interrupt signal")
    finally:
        await server.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_server())
