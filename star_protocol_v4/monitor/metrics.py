"""Star Protocol 指标收集器"""

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from ..protocol import Envelope, ClientInfo, MessageType, ClientType
from ..utils import get_logger


@dataclass
class MetricPoint:
    """指标数据点"""

    timestamp: float
    value: Any
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class ConnectionMetric:
    """连接指标"""

    client_id: str
    client_type: ClientType
    env_id: Optional[str]
    connected_at: float
    disconnected_at: Optional[float] = None

    @property
    def duration(self) -> Optional[float]:
        """连接持续时间"""
        if self.disconnected_at:
            return self.disconnected_at - self.connected_at
        return time.time() - self.connected_at


@dataclass
class MessageMetric:
    """消息指标"""

    envelope_type: str
    sender_id: str
    recipient_id: Optional[str]
    timestamp: float
    envelope_size: int

    @property
    def labels(self) -> Dict[str, str]:
        """指标标签"""
        return {
            "envelope_type": self.envelope_type,
            "recipient": self.recipient_id or "broadcast",
        }


class MetricsBackend(ABC):
    """指标后端抽象接口"""

    @abstractmethod
    async def record_connection(self, metric: ConnectionMetric) -> None:
        """记录连接指标"""
        pass

    @abstractmethod
    async def record_envelope(self, metric: MessageMetric) -> None:
        """记录信封指标"""
        pass

    @abstractmethod
    async def record_counter(
        self, name: str, value: float, labels: Dict[str, str] = None
    ) -> None:
        """记录计数器指标"""
        pass

    @abstractmethod
    async def record_gauge(
        self, name: str, value: float, labels: Dict[str, str] = None
    ) -> None:
        """记录仪表指标"""
        pass

    @abstractmethod
    async def record_histogram(
        self, name: str, value: float, labels: Dict[str, str] = None
    ) -> None:
        """记录直方图指标"""
        pass

    @abstractmethod
    async def export_metrics(self) -> Dict[str, Any]:
        """导出指标数据"""
        pass


class MemoryBackend(MetricsBackend):
    """内存后端实现"""

    def __init__(self, max_points: int = 10000):
        self.max_points = max_points

        # 存储各种指标
        self.connections: List[ConnectionMetric] = []
        self.envelopes: List[MessageMetric] = []
        self.counters: Dict[str, List[MetricPoint]] = {}
        self.gauges: Dict[str, List[MetricPoint]] = {}
        self.histograms: Dict[str, List[MetricPoint]] = {}

    async def record_connection(self, metric: ConnectionMetric) -> None:
        """记录连接指标"""
        self.connections.append(metric)
        # 限制存储数量
        if len(self.connections) > self.max_points:
            self.connections.pop(0)

    async def record_envelope(self, metric: MessageMetric) -> None:
        """记录信封指标"""
        self.envelopes.append(metric)
        # 限制存储数量
        if len(self.envelopes) > self.max_points:
            self.envelopes.pop(0)

    async def record_counter(
        self, name: str, value: float, labels: Dict[str, str] = None
    ) -> None:
        """记录计数器指标"""
        if name not in self.counters:
            self.counters[name] = []

        point = MetricPoint(timestamp=time.time(), value=value, labels=labels or {})
        self.counters[name].append(point)

        # 限制存储数量
        if len(self.counters[name]) > self.max_points:
            self.counters[name].pop(0)

    async def record_gauge(
        self, name: str, value: float, labels: Dict[str, str] = None
    ) -> None:
        """记录仪表指标"""
        if name not in self.gauges:
            self.gauges[name] = []

        point = MetricPoint(timestamp=time.time(), value=value, labels=labels or {})
        self.gauges[name].append(point)

        # 限制存储数量
        if len(self.gauges[name]) > self.max_points:
            self.gauges[name].pop(0)

    async def record_histogram(
        self, name: str, value: float, labels: Dict[str, str] = None
    ) -> None:
        """记录直方图指标"""
        if name not in self.histograms:
            self.histograms[name] = []

        point = MetricPoint(timestamp=time.time(), value=value, labels=labels or {})
        self.histograms[name].append(point)

        # 限制存储数量
        if len(self.histograms[name]) > self.max_points:
            self.histograms[name].pop(0)

    async def export_metrics(self) -> Dict[str, Any]:
        """导出指标数据"""
        return {
            "connections": [
                {
                    "client_id": conn.client_id,
                    "client_type": conn.client_type.value,
                    "env_id": conn.env_id,
                    "connected_at": conn.connected_at,
                    "disconnected_at": conn.disconnected_at,
                    "duration": conn.duration,
                }
                for conn in self.connections
            ],
            "envelopes": [
                {
                    "envelope_type": env.envelope_type,
                    "sender_id": env.sender_id,
                    "recipient_id": env.recipient_id,
                    "timestamp": env.timestamp,
                    "envelope_size": env.envelope_size,
                }
                for env in self.envelopes
            ],
            "counters": {
                name: [
                    {
                        "timestamp": point.timestamp,
                        "value": point.value,
                        "labels": point.labels,
                    }
                    for point in points
                ]
                for name, points in self.counters.items()
            },
            "gauges": {
                name: [
                    {
                        "timestamp": point.timestamp,
                        "value": point.value,
                        "labels": point.labels,
                    }
                    for point in points
                ]
                for name, points in self.gauges.items()
            },
            "histograms": {
                name: [
                    {
                        "timestamp": point.timestamp,
                        "value": point.value,
                        "labels": point.labels,
                    }
                    for point in points
                ]
                for name, points in self.histograms.items()
            },
        }


class MetricsCollector:
    """指标收集器"""

    def __init__(self, backend: Optional[MetricsBackend] = None):
        self.backend = backend or MemoryBackend()
        self.logger = get_logger("star_protocol.monitor")

        # 内部计数器
        self._envelope_sent_count = 0
        self._envelope_received_count = 0
        self._envelope_routed_count = 0
        self._active_connections = 0

    async def record_client_connected(self, client_info: ClientInfo) -> None:
        """记录客户端连接"""
        metric = ConnectionMetric(
            client_id=client_info.client_id,
            client_type=client_info.client_type,
            env_id=client_info.env_id,
            connected_at=time.time(),
        )

        await self.backend.record_connection(metric)

        self._active_connections += 1
        await self.backend.record_gauge("active_connections", self._active_connections)

        # 按类型计数
        await self.backend.record_counter(
            "client_connections_total",
            1,
            {"client_type": client_info.client_type.value},
        )

        self.logger.debug(f"记录客户端连接: {client_info.client_id}")

    async def record_client_disconnected(self, client_id: str) -> None:
        """记录客户端断开连接"""
        # 更新连接指标中的断开时间
        for conn in self.backend.connections:
            if conn.client_id == client_id and conn.disconnected_at is None:
                conn.disconnected_at = time.time()
                break

        self._active_connections = max(0, self._active_connections - 1)
        await self.backend.record_gauge("active_connections", self._active_connections)

        await self.backend.record_counter("client_disconnections_total", 1)

        self.logger.debug(f"记录客户端断开: {client_id}")

    async def record_envelope_sent(self, envelope: Envelope) -> None:
        """记录发送的信封"""
        metric = MessageMetric(
            envelope_type=envelope.envelope_type.value,
            sender_id=envelope.sender,
            recipient_id=envelope.recipient,
            timestamp=envelope.timestamp or time.time(),
            envelope_size=len(envelope.to_json()),
        )

        await self.backend.record_envelope(metric)

        self._envelope_sent_count += 1
        await self.backend.record_counter("envelopes_sent_total", 1, metric.labels)

        await self.backend.record_histogram(
            "envelope_size_bytes", metric.envelope_size, metric.labels
        )

    async def record_envelope_received(self, envelope: Envelope) -> None:
        """记录接收的信封"""
        self._envelope_received_count += 1

        metric = MessageMetric(
            envelope_type=envelope.envelope_type.value,
            sender_id=envelope.sender,
            recipient_id=envelope.recipient,
            timestamp=envelope.timestamp or time.time(),
            envelope_size=len(envelope.to_json()),
        )

        await self.backend.record_envelope(metric)

        await self.backend.record_counter("envelopes_received_total", 1, metric.labels)

    async def record_envelope_routed(self, envelope: Envelope) -> None:
        """记录路由的信封"""
        self._envelope_routed_count += 1

        metric = MessageMetric(
            envelope_type=envelope.envelope_type.value,
            sender_id=envelope.sender,
            recipient_id=envelope.recipient,
            timestamp=envelope.timestamp or time.time(),
            envelope_size=len(envelope.to_json()),
        )

        await self.backend.record_envelope(metric)

        await self.backend.record_counter("envelopes_routed_total", 1, metric.labels)

    async def record_custom_metric(
        self, metric_type: str, name: str, value: float, labels: Dict[str, str] = None
    ) -> None:
        """记录自定义指标

        Args:
            metric_type: 指标类型 (counter, gauge, histogram)
            name: 指标名称
            value: 指标值
            labels: 标签
        """
        if metric_type == "counter":
            await self.backend.record_counter(name, value, labels)
        elif metric_type == "gauge":
            await self.backend.record_gauge(name, value, labels)
        elif metric_type == "histogram":
            await self.backend.record_histogram(name, value, labels)
        else:
            self.logger.warning(f"未知指标类型: {metric_type}")

    async def export_metrics(self) -> Dict[str, Any]:
        """导出所有指标"""
        return await self.backend.export_metrics()

    def get_summary(self) -> Dict[str, Any]:
        """获取指标摘要"""
        return {
            "active_connections": self._active_connections,
            "envelopes_sent": self._envelope_sent_count,
            "envelopes_received": self._envelope_received_count,
            "envelopes_routed": self._envelope_routed_count,
        }
