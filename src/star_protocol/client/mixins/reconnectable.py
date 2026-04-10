"""自动重连 Mixin"""

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from star_protocol.client.base import BaseClient


class ReconnectableMixin:
    """
    自动重连 Mixin
    
    为客户端添加自动重连能力：
    - 检测连接断开
    - 自动尝试重连
    - 重连后恢复状态
    """
    
    def __init__(
        self,
        *args,
        auto_reconnect: bool = False,
        reconnect_interval: float = 5.0,
        max_reconnect_attempts: int = 10,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.auto_reconnect = auto_reconnect
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_attempts = max_reconnect_attempts
        self._reconnect_attempts = 0
        self.logger = getattr(self, 'logger', logging.getLogger(__name__))
    
    async def _attempt_reconnect(self) -> bool:
        """
        尝试重连
        
        Returns:
            是否成功重连
        """
        if not self.auto_reconnect:
            return False
        
        if self._reconnect_attempts >= self.max_reconnect_attempts:
            self.logger.error("Max reconnect attempts reached")
            return False
        
        self._reconnect_attempts += 1
        self.logger.info(
            f"Attempting reconnect {self._reconnect_attempts}/{self.max_reconnect_attempts}"
        )
        
        await asyncio.sleep(self.reconnect_interval)
        
        try:
            # 获取原始 URL
            url = getattr(self, '_url', None)
            if not url:
                self.logger.error("No URL to reconnect to")
                return False
            
            # 提取基础 URL（移除 /ws/role/client_id 部分）
            base_url = url.rsplit("/ws/", 1)[0]
            
            # 重新连接
            await self.connect(base_url)
            
            # 如果之前在环境中，重新加入
            current_env = getattr(self, 'current_env', None)
            if current_env:
                await self.join_environment(current_env)
            
            self._reconnect_attempts = 0
            self.logger.info("Reconnected successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Reconnect failed: {e}")
            return False
    
    def reset_reconnect_attempts(self) -> None:
        """重置重连计数"""
        self._reconnect_attempts = 0
