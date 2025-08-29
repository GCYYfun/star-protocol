"""客户端上下文管理模块"""

import asyncio
import time
import uuid
from typing import Dict, Any, Optional, Callable, Awaitable, TypeVar, Generic
from dataclasses import dataclass, field
from enum import Enum
from ..utils import get_logger

T = TypeVar("T")


class ContextStatus(Enum):
    """上下文状态"""

    PENDING = "pending"  # 等待响应
    COMPLETED = "completed"  # 已完成
    TIMEOUT = "timeout"  # 超时
    ERROR = "error"  # 错误


@dataclass
class ContextItem(Generic[T]):
    """上下文项"""

    request_id: str
    request_type: str
    request_data: Dict[str, Any]
    status: ContextStatus = ContextStatus.PENDING
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    timeout: float = 30.0
    future: Optional[asyncio.Future[T]] = None
    callback: Optional[Callable[[T], Awaitable[None]]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.future is None:
            self.future = asyncio.Future()

    @property
    def elapsed_time(self) -> float:
        """获取已经过的时间"""
        if self.completed_at:
            return self.completed_at - self.created_at
        return time.time() - self.created_at

    @property
    def is_expired(self) -> bool:
        """检查是否超时"""
        return self.elapsed_time > self.timeout

    def complete(self, result: T) -> None:
        """完成上下文项"""
        if self.status != ContextStatus.PENDING:
            return

        self.status = ContextStatus.COMPLETED
        self.completed_at = time.time()

        if self.future and not self.future.done():
            self.future.set_result(result)

    def error(self, exception: Exception) -> None:
        """设置错误状态"""
        if self.status != ContextStatus.PENDING:
            return

        self.status = ContextStatus.ERROR
        self.completed_at = time.time()

        if self.future and not self.future.done():
            self.future.set_exception(exception)

    def timeout_expired(self) -> None:
        """设置超时状态"""
        if self.status != ContextStatus.PENDING:
            return

        self.status = ContextStatus.TIMEOUT
        self.completed_at = time.time()

        if self.future and not self.future.done():
            self.future.set_exception(
                asyncio.TimeoutError(f"Request {self.request_id} timed out")
            )


class ClientContext:
    """客户端上下文管理器

    管理异步请求-响应的对应关系，支持：
    - Action -> Outcome 映射
    - Event -> Response 映射
    - 超时处理
    - 回调处理
    - 统计信息
    """

    def __init__(self, client_id: str, default_timeout: float = 30.0):
        self.client_id = client_id
        self.default_timeout = default_timeout

        # 上下文存储：request_id -> ContextItem
        self._contexts: Dict[str, ContextItem] = {}

        # 类型映射：便于按类型查找
        self._type_mapping: Dict[str, set] = {}

        # 统计信息
        self._stats = {
            "total_requests": 0,
            "completed_requests": 0,
            "timeout_requests": 0,
            "error_requests": 0,
        }

        # 清理任务
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval = 60.0  # 60秒清理一次

        self.logger = get_logger(f"star_protocol.client.context.{client_id}")

    async def start(self) -> None:
        """启动上下文管理器"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            self.logger.debug("上下文管理器已启动")

    async def stop(self) -> None:
        """停止上下文管理器"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            self.logger.debug("上下文管理器已停止")

    def create_request_context(
        self,
        request_type: str,
        request_data: Dict[str, Any],
        timeout: Optional[float] = None,
        callback: Optional[Callable[[Any], Awaitable[None]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ) -> ContextItem:
        """创建请求上下文

        Args:
            request_type: 请求类型（如 "action", "event"）
            request_data: 请求数据
            timeout: 超时时间（秒）
            callback: 响应回调函数
            metadata: 额外元数据
            request_id: 自定义请求ID

        Returns:
            创建的上下文项
        """
        if request_id is None:
            request_id = self._generate_request_id(request_type)

        if timeout is None:
            timeout = self.default_timeout

        context_item = ContextItem(
            request_id=request_id,
            request_type=request_type,
            request_data=request_data,
            timeout=timeout,
            callback=callback,
            metadata=metadata or {},
        )

        # 存储上下文
        self._contexts[request_id] = context_item

        # 更新类型映射
        if request_type not in self._type_mapping:
            self._type_mapping[request_type] = set()
        self._type_mapping[request_type].add(request_id)

        # 更新统计
        self._stats["total_requests"] += 1

        self.logger.debug(f"创建上下文: {request_id} ({request_type})")
        return context_item

    def complete_request(
        self,
        request_id: str,
        result: Any,
        trigger_callback: bool = True,
    ) -> bool:
        """完成请求

        Args:
            request_id: 请求ID
            result: 响应结果
            trigger_callback: 是否触发回调

        Returns:
            是否成功完成
        """
        context_item = self._contexts.get(request_id)
        if not context_item:
            self.logger.warning(f"未找到上下文: {request_id}")
            return False

        if context_item.status != ContextStatus.PENDING:
            self.logger.warning(
                f"上下文 {request_id} 已经完成，状态: {context_item.status}"
            )
            return False

        # 完成上下文
        context_item.complete(result)
        self._stats["completed_requests"] += 1

        self.logger.debug(
            f"完成上下文: {request_id} 耗时: {context_item.elapsed_time:.2f}s"
        )

        # 触发回调
        if trigger_callback and context_item.callback:
            asyncio.create_task(self._execute_callback(context_item, result))

        return True

    def error_request(self, request_id: str, exception: Exception) -> bool:
        """设置请求错误

        Args:
            request_id: 请求ID
            exception: 异常对象

        Returns:
            是否成功设置错误
        """
        context_item = self._contexts.get(request_id)
        if not context_item:
            self.logger.warning(f"未找到上下文: {request_id}")
            return False

        if context_item.status != ContextStatus.PENDING:
            return False

        context_item.error(exception)
        self._stats["error_requests"] += 1

        self.logger.warning(f"上下文错误: {request_id} - {exception}")
        return True

    async def wait_for_response(
        self,
        request_id: str,
        timeout: Optional[float] = None,
    ) -> Any:
        """等待响应

        Args:
            request_id: 请求ID
            timeout: 超时时间（秒）

        Returns:
            响应结果

        Raises:
            asyncio.TimeoutError: 超时
            KeyError: 未找到上下文
            Exception: 其他错误
        """
        context_item = self._contexts.get(request_id)
        if not context_item:
            raise KeyError(f"未找到上下文: {request_id}")

        if not context_item.future:
            raise RuntimeError(f"上下文 {request_id} 没有 future")

        if timeout is None:
            timeout = context_item.timeout

        try:
            result = await asyncio.wait_for(context_item.future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            # 标记为超时
            context_item.timeout_expired()
            self._stats["timeout_requests"] += 1
            self.logger.warning(f"上下文超时: {request_id}")
            raise

    def get_context(self, request_id: str) -> Optional[ContextItem]:
        """获取上下文项"""
        return self._contexts.get(request_id)

    def get_contexts_by_type(self, request_type: str) -> Dict[str, ContextItem]:
        """按类型获取上下文"""
        request_ids = self._type_mapping.get(request_type, set())
        return {
            request_id: self._contexts[request_id]
            for request_id in request_ids
            if request_id in self._contexts
        }

    def get_pending_contexts(self) -> Dict[str, ContextItem]:
        """获取所有待处理的上下文"""
        return {
            request_id: context
            for request_id, context in self._contexts.items()
            if context.status == ContextStatus.PENDING
        }

    def remove_context(self, request_id: str) -> bool:
        """移除上下文"""
        context_item = self._contexts.pop(request_id, None)
        if not context_item:
            return False

        # 从类型映射中移除
        request_type = context_item.request_type
        if request_type in self._type_mapping:
            self._type_mapping[request_type].discard(request_id)
            if not self._type_mapping[request_type]:
                del self._type_mapping[request_type]

        self.logger.debug(f"移除上下文: {request_id}")
        return True

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        pending_count = len(self.get_pending_contexts())
        return {
            **self._stats,
            "pending_requests": pending_count,
            "active_contexts": len(self._contexts),
            "request_types": list(self._type_mapping.keys()),
        }

    def _generate_request_id(self, request_type: str) -> str:
        """生成请求ID"""
        timestamp = int(time.time() * 1000)
        unique_id = str(uuid.uuid4())[:8]
        return f"{self.client_id}_{request_type}_{timestamp}_{unique_id}"

    async def _execute_callback(self, context_item: ContextItem, result: Any) -> None:
        """执行回调函数"""
        try:
            if context_item.callback:
                await context_item.callback(result)
        except Exception as e:
            self.logger.error(f"回调执行失败 {context_item.request_id}: {e}")

    async def _cleanup_loop(self) -> None:
        """清理循环，移除过期的上下文"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_expired_contexts()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"清理循环出错: {e}")

    async def _cleanup_expired_contexts(self) -> None:
        """清理过期的上下文"""
        expired_ids = []

        for request_id, context_item in self._contexts.items():
            if context_item.status == ContextStatus.PENDING and context_item.is_expired:
                # 标记为超时
                context_item.timeout_expired()
                self._stats["timeout_requests"] += 1
                expired_ids.append(request_id)
            elif context_item.status in [
                ContextStatus.COMPLETED,
                ContextStatus.TIMEOUT,
                ContextStatus.ERROR,
            ]:
                # 清理已完成的上下文（保留一段时间后清理）
                if context_item.elapsed_time > 300:  # 5分钟后清理
                    expired_ids.append(request_id)

        # 移除过期的上下文
        for request_id in expired_ids:
            self.remove_context(request_id)

        if expired_ids:
            self.logger.debug(f"清理了 {len(expired_ids)} 个过期上下文")


# 便捷的装饰器和工具函数


def with_context(
    context_manager: ClientContext,
    request_type: str,
    timeout: Optional[float] = None,
    callback: Optional[Callable] = None,
):
    """装饰器：自动管理上下文"""

    def decorator(func):
        async def wrapper(*args, **kwargs):
            # 执行原函数获取请求数据
            request_data = (
                await func(*args, **kwargs)
                if asyncio.iscoroutinefunction(func)
                else func(*args, **kwargs)
            )

            # 创建上下文
            context_item = context_manager.create_request_context(
                request_type=request_type,
                request_data=request_data,
                timeout=timeout,
                callback=callback,
            )

            # 返回上下文项和请求ID
            return context_item.request_id, request_data

        return wrapper

    return decorator
