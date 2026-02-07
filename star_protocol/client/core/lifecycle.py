"""客户端生命周期管理"""

import asyncio
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from star_protocol.client.base import BaseClient


class LifecycleManager:
    """
    生命周期管理器
    
    职责：
    - 启动/停止客户端
    - 管理消息循环任务
    - 上下文管理器支持
    """
    
    def __init__(self, client: "BaseClient"):
        self.client = client
        self._message_loop_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self) -> None:
        """
        启动客户端（启动消息循环）
        
        这是一个便捷方法，在后台启动消息循环
        """
        # 如果已经有消息循环在运行，先停止
        if self._message_loop_task and not self._message_loop_task.done():
            await self.stop()
        
        # 启动消息循环任务
        self._running = True
        self._message_loop_task = asyncio.create_task(self.client.run())
        self.client.logger.info("Client started (message loop running in background)")
    
    async def stop(self) -> None:
        """
        停止客户端（停止消息循环 + 断开连接）
        
        这是一个便捷方法，用于优雅地停止客户端
        """
        # 停止消息循环
        self._running = False
        
        if self._message_loop_task and not self._message_loop_task.done():
            try:
                await asyncio.wait_for(self._message_loop_task, timeout=2.0)
            except asyncio.TimeoutError:
                self._message_loop_task.cancel()
                try:
                    await self._message_loop_task
                except asyncio.CancelledError:
                    pass
            self._message_loop_task = None
        
        # 断开连接
        await self.client.disconnect()
        self.client.logger.info("Client stopped")
    
    def is_running(self) -> bool:
        """检查消息循环是否在运行"""
        return self._running and self._message_loop_task and not self._message_loop_task.done()
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self.client
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.stop()
        return False
