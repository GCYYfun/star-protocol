"""
监控指标系统

提供性能指标收集、聚合和分析功能
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union, Callable
from collections import defaultdict, deque
import statistics
import threading
import time


class MetricType(Enum):
    """指标类型"""

    # 计数器 - 累积值
    COUNTER = "counter"

    # 仪表 - 当前值
    GAUGE = "gauge"

    # 直方图 - 分布统计
    HISTOGRAM = "histogram"

    # 摘要 - 分位数统计
    SUMMARY = "summary"

    # 计时器 - 时间测量
    TIMER = "timer"


@dataclass
class Metric:
    """指标数据"""

    name: str
    metric_type: MetricType
    value: Union[float, int]
    timestamp: datetime = field(default_factory=datetime.now)
    labels: Dict[str, str] = field(default_factory=dict)
    unit: str = ""
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "type": self.metric_type.value,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels,
            "unit": self.unit,
            "description": self.description,
        }


@dataclass
class MetricSummary:
    """指标摘要统计"""

    name: str
    count: int
    sum_value: float
    min_value: float
    max_value: float
    avg_value: float
    median_value: float
    p95_value: float
    p99_value: float
    last_updated: datetime

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "count": self.count,
            "sum": self.sum_value,
            "min": self.min_value,
            "max": self.max_value,
            "avg": self.avg_value,
            "median": self.median_value,
            "p95": self.p95_value,
            "p99": self.p99_value,
            "last_updated": self.last_updated.isoformat(),
        }


class MetricsCollector:
    """指标收集器"""

    def __init__(
        self,
        source: str,
        source_type: str,
        max_history: int = 1000,
        summary_window: int = 300,  # 5分钟窗口
    ):
        self.source = source
        self.source_type = source_type
        self.max_history = max_history
        self.summary_window = summary_window

        # 存储指标数据
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = defaultdict(float)
        self._timers: Dict[str, List[float]] = defaultdict(list)

        # 线程锁
        self._lock = threading.RLock()

        # 回调函数
        self._metric_callbacks: List[Callable[[Metric], None]] = []

    def add_callback(self, callback: Callable[[Metric], None]) -> None:
        """添加指标回调"""
        with self._lock:
            self._metric_callbacks.append(callback)

    def remove_callback(self, callback: Callable[[Metric], None]) -> None:
        """移除指标回调"""
        with self._lock:
            if callback in self._metric_callbacks:
                self._metric_callbacks.remove(callback)

    def _notify_callbacks(self, metric: Metric) -> None:
        """通知回调函数"""
        for callback in self._metric_callbacks:
            try:
                callback(metric)
            except Exception:
                pass  # 忽略回调异常

    def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        labels: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> None:
        """增加计数器"""
        with self._lock:
            key = self._get_metric_key(name, labels)
            self._counters[key] += value

            metric = Metric(
                name=name,
                metric_type=MetricType.COUNTER,
                value=self._counters[key],
                labels=labels or {},
                **kwargs,
            )

            self._metrics[key].append(metric)
            self._notify_callbacks(metric)

    def set_gauge(
        self, name: str, value: float, labels: Optional[Dict[str, str]] = None, **kwargs
    ) -> None:
        """设置仪表值"""
        with self._lock:
            key = self._get_metric_key(name, labels)
            self._gauges[key] = value

            metric = Metric(
                name=name,
                metric_type=MetricType.GAUGE,
                value=value,
                labels=labels or {},
                **kwargs,
            )

            self._metrics[key].append(metric)
            self._notify_callbacks(metric)

    def record_histogram(
        self, name: str, value: float, labels: Optional[Dict[str, str]] = None, **kwargs
    ) -> None:
        """记录直方图值"""
        with self._lock:
            key = self._get_metric_key(name, labels)

            metric = Metric(
                name=name,
                metric_type=MetricType.HISTOGRAM,
                value=value,
                labels=labels or {},
                **kwargs,
            )

            self._metrics[key].append(metric)
            self._notify_callbacks(metric)

    def time_operation(self, name: str, labels: Optional[Dict[str, str]] = None):
        """时间测量装饰器/上下文管理器"""
        return TimerContext(self, name, labels)

    def record_timer(
        self,
        name: str,
        duration_ms: float,
        labels: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> None:
        """记录时间测量"""
        with self._lock:
            key = self._get_metric_key(name, labels)
            self._timers[key].append(duration_ms)

            # 限制历史记录大小
            if len(self._timers[key]) > self.max_history:
                self._timers[key] = self._timers[key][-self.max_history :]

            metric = Metric(
                name=name,
                metric_type=MetricType.TIMER,
                value=duration_ms,
                labels=labels or {},
                unit="ms",
                **kwargs,
            )

            self._metrics[key].append(metric)
            self._notify_callbacks(metric)

    def get_metric_summary(
        self, name: str, labels: Optional[Dict[str, str]] = None
    ) -> Optional[MetricSummary]:
        """获取指标摘要"""
        with self._lock:
            key = self._get_metric_key(name, labels)

            if key not in self._metrics or not self._metrics[key]:
                return None

            # 获取窗口内的数据
            cutoff_time = datetime.now() - timedelta(seconds=self.summary_window)
            recent_metrics = [
                m for m in self._metrics[key] if m.timestamp >= cutoff_time
            ]

            if not recent_metrics:
                return None

            values = [m.value for m in recent_metrics]

            try:
                return MetricSummary(
                    name=name,
                    count=len(values),
                    sum_value=sum(values),
                    min_value=min(values),
                    max_value=max(values),
                    avg_value=statistics.mean(values),
                    median_value=statistics.median(values),
                    p95_value=self._percentile(values, 95),
                    p99_value=self._percentile(values, 99),
                    last_updated=recent_metrics[-1].timestamp,
                )
            except Exception:
                return None

    def get_all_summaries(self) -> Dict[str, MetricSummary]:
        """获取所有指标摘要"""
        summaries = {}

        with self._lock:
            # 解析所有指标名称
            metric_names = set()
            for key in self._metrics.keys():
                name = key.split("|")[0]  # 提取指标名称
                metric_names.add(name)

            for name in metric_names:
                summary = self.get_metric_summary(name)
                if summary:
                    summaries[name] = summary

        return summaries

    def get_recent_metrics(
        self,
        name: Optional[str] = None,
        limit: int = 100,
        since: Optional[datetime] = None,
    ) -> List[Metric]:
        """获取最近的指标"""
        with self._lock:
            all_metrics = []

            for key, metrics in self._metrics.items():
                if name and not key.startswith(name):
                    continue

                for metric in metrics:
                    if since and metric.timestamp < since:
                        continue
                    all_metrics.append(metric)

            # 按时间排序
            all_metrics.sort(key=lambda m: m.timestamp, reverse=True)

            return all_metrics[:limit]

    def clear_metrics(self, name: Optional[str] = None) -> None:
        """清除指标数据"""
        with self._lock:
            if name:
                # 清除特定指标
                keys_to_clear = [k for k in self._metrics.keys() if k.startswith(name)]
                for key in keys_to_clear:
                    self._metrics[key].clear()
                    if key in self._counters:
                        del self._counters[key]
                    if key in self._gauges:
                        del self._gauges[key]
                    if key in self._timers:
                        del self._timers[key]
            else:
                # 清除所有指标
                self._metrics.clear()
                self._counters.clear()
                self._gauges.clear()
                self._timers.clear()

    def _get_metric_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """生成指标键"""
        if not labels:
            return name

        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}|{label_str}"

    @staticmethod
    def _percentile(values: List[float], percentile: float) -> float:
        """计算百分位数"""
        if not values:
            return 0.0

        sorted_values = sorted(values)
        k = (len(sorted_values) - 1) * percentile / 100
        f = int(k)
        c = k - f

        if f == len(sorted_values) - 1:
            return sorted_values[f]
        else:
            return sorted_values[f] * (1 - c) + sorted_values[f + 1] * c


class TimerContext:
    """时间测量上下文管理器"""

    def __init__(
        self,
        collector: MetricsCollector,
        name: str,
        labels: Optional[Dict[str, str]] = None,
    ):
        self.collector = collector
        self.name = name
        self.labels = labels
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration_ms = (time.time() - self.start_time) * 1000
            self.collector.record_timer(self.name, duration_ms, self.labels)

    def __call__(self, func):
        """作为装饰器使用"""

        def wrapper(*args, **kwargs):
            with self:
                return func(*args, **kwargs)

        return wrapper


# 预定义的常用指标名称
class CommonMetrics:
    """常用指标名称"""

    # 连接指标
    CONNECTIONS_TOTAL = "connections_total"
    CONNECTIONS_ACTIVE = "connections_active"
    CONNECTION_DURATION = "connection_duration_ms"
    CONNECTION_ERRORS = "connection_errors_total"

    # 消息指标
    MESSAGES_SENT = "messages_sent_total"
    MESSAGES_RECEIVED = "messages_received_total"
    MESSAGE_SIZE = "message_size_bytes"
    MESSAGE_LATENCY = "message_latency_ms"
    MESSAGE_ERRORS = "message_errors_total"

    # 性能指标
    CPU_USAGE = "cpu_usage_percent"
    MEMORY_USAGE = "memory_usage_mb"
    MEMORY_USAGE_PERCENT = "memory_usage_percent"
    RESPONSE_TIME = "response_time_ms"
    THROUGHPUT = "throughput_ops_per_sec"

    # 错误指标
    ERRORS_TOTAL = "errors_total"
    WARNINGS_TOTAL = "warnings_total"
    EXCEPTIONS_TOTAL = "exceptions_total"

    # 业务指标
    ACTIONS_EXECUTED = "actions_executed_total"
    EVENTS_BROADCAST = "events_broadcast_total"
    USERS_ACTIVE = "users_active"
    ENVIRONMENTS_ACTIVE = "environments_active"
