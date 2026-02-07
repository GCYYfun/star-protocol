"""FastAPI Hub Server 应用"""

import logging
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from star_protocol.server.router import MessageRouter


logger = logging.getLogger(__name__)


def create_hub_app(
    title: str = "Star Protocol Hub",
    max_connections: int = 1000,
    heartbeat_interval: float = 30.0,
    enable_cors: bool = True
) -> FastAPI:
    """
    创建 Hub Server 应用
    
    Args:
        title: 应用标题
        max_connections: 最大连接数
        heartbeat_interval: 心跳间隔（秒）
        enable_cors: 是否启用 CORS
    
    Returns:
        FastAPI 应用实例
    """
    
    app = FastAPI(
        title=title,
        description="Multi-Agent Communication Hub based on Star Protocol",
        version="0.1.0"
    )
    
    # CORS 中间件
    if enable_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    # 创建路由器
    router = MessageRouter(
        max_connections=max_connections,
        heartbeat_interval=heartbeat_interval
    )
    
    # 存储到应用状态
    app.state.router = router
    
    # WebSocket 端点
    @app.websocket("/ws/{role}/{client_id}")
    async def websocket_endpoint(
        websocket: WebSocket,
        role: str,
        client_id: str
    ):
        """
        WebSocket 连接端点
        
        Args:
            websocket: WebSocket 连接
            role: 客户端角色 (agent, environment, human)
            client_id: 客户端唯一标识
        """
        await router.handle_connection(websocket, role, client_id)
    
    # HTTP 端点
    @app.get("/health")
    async def health_check():
        """健康检查"""
        return {
            "status": "ok",
            "version": "0.1.0"
        }
    
    @app.get("/stats")
    async def get_stats():
        """获取统计信息"""
        stats = router.connection_manager.get_statistics()
        stats["uptime"] = router.get_uptime()
        return stats
    
    @app.get("/environments")
    async def list_environments():
        """列出所有环境"""
        return {
            "environments": router.connection_manager.get_environment_details()
        }
    
    @app.get("/clients/{client_id}")
    async def get_client_info(client_id: str):
        """
        获取客户端信息
        
        Args:
            client_id: 客户端 ID
        """
        session = router.connection_manager.get_session(client_id)
        if not session:
            return {"error": "Client not found"}, 404
        return session.to_dict()
    
    # 启动/关闭事件
    @app.on_event("startup")
    async def startup_event():
        """应用启动事件"""
        logger.info("Star Protocol Hub starting...")
        await router.start()
    
    @app.on_event("shutdown")
    async def shutdown_event():
        """应用关闭事件"""
        logger.info("Star Protocol Hub shutting down...")
        await router.stop()
    
    return app
