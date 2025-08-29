"""简单监控实现"""

import asyncio
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any
from .metrics import MetricsCollector, MetricsBackend, MemoryBackend
from ..utils import get_logger


class FileBackend(MetricsBackend):
    """文件后端实现"""

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.memory_backend = MemoryBackend()
        self.logger = get_logger("star_protocol.monitor.file")

    # 代理属性访问到内存后端
    @property
    def connections(self):
        return self.memory_backend.connections

    @property
    def envelopes(self):
        return self.memory_backend.envelopes

    @property
    def counters(self):
        return self.memory_backend.counters

    @property
    def gauges(self):
        return self.memory_backend.gauges

    @property
    def histograms(self):
        return self.memory_backend.histograms

    async def record_connection(self, metric) -> None:
        await self.memory_backend.record_connection(metric)

    async def record_envelope(self, metric) -> None:
        await self.memory_backend.record_envelope(metric)

    async def record_counter(
        self, name: str, value: float, labels: Dict[str, str] = None
    ) -> None:
        await self.memory_backend.record_counter(name, value, labels)

    async def record_gauge(
        self, name: str, value: float, labels: Dict[str, str] = None
    ) -> None:
        await self.memory_backend.record_gauge(name, value, labels)

    async def record_histogram(
        self, name: str, value: float, labels: Dict[str, str] = None
    ) -> None:
        await self.memory_backend.record_histogram(name, value, labels)

    async def export_metrics(self) -> Dict[str, Any]:
        return await self.memory_backend.export_metrics()

    async def save_to_file(self) -> None:
        """保存指标到文件"""
        try:
            metrics = await self.export_metrics()

            # 添加元数据
            output = {"timestamp": time.time(), "version": "1.0", "metrics": metrics}

            # 确保目录存在
            self.file_path.parent.mkdir(parents=True, exist_ok=True)

            # 写入文件
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, ensure_ascii=False)

            self.logger.debug(f"指标已保存到: {self.file_path}")

        except Exception as e:
            self.logger.error(f"保存指标文件失败: {e}")


class SimpleMonitor:
    """简单监控实现"""

    def __init__(
        self,
        export_interval: float = 60.0,
        file_path: Optional[str] = None,
        console_output: bool = True,
    ):
        self.export_interval = export_interval
        self.console_output = console_output

        # 创建后端
        if file_path:
            self.backend = FileBackend(file_path)
        else:
            self.backend = MemoryBackend()

        # 创建收集器
        self.collector = MetricsCollector(self.backend)

        # 监控任务
        self._export_task: Optional[asyncio.Task] = None
        self._running = False

        self.logger = get_logger("star_protocol.monitor.simple")

    def start(self) -> None:
        """启动监控"""
        if self._running:
            return

        self._running = True
        # self._export_task = asyncio.create_task(self._export_loop())
        self.logger.info("简单监控已启动")

    def stop(self) -> None:
        """停止监控"""
        if not self._running:
            return

        self._running = False
        if self._export_task:
            self._export_task.cancel()

        self.logger.info("简单监控已停止")

    async def _export_loop(self) -> None:
        """导出循环"""
        # 启动时立即导出一次
        if self._running:
            await self._export_metrics()

        while self._running:
            try:
                await asyncio.sleep(self.export_interval)

                if not self._running:
                    break

                # 导出指标
                await self._export_metrics()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"导出指标失败: {e}")

    async def _export_metrics(self) -> None:
        """导出指标"""
        try:
            # 获取摘要
            summary = self.collector.get_summary()

            # 控制台输出
            if self.console_output:
                print(
                    f"\n=== Star Protocol 监控摘要 ({time.strftime('%Y-%m-%d %H:%M:%S')}) ==="
                )
                print(f"活跃连接: {summary['active_connections']}")
                print(f"发送信封: {summary['envelopes_sent']}")
                print(f"接收信封: {summary['envelopes_received']}")
                print(f"路由信封: {summary['envelopes_routed']}")
                print("=" * 60)

            # 文件输出
            if isinstance(self.backend, FileBackend):
                await self.backend.save_to_file()

        except Exception as e:
            self.logger.error(f"导出指标时出错: {e}")

    async def get_current_metrics(self) -> Dict[str, Any]:
        """获取当前指标"""
        return await self.collector.export_metrics()

    def get_collector(self) -> MetricsCollector:
        """获取指标收集器"""
        return self.collector


# 便捷函数
def create_simple_monitor(
    export_interval: float = 60.0,
    file_path: Optional[str] = None,
    console_output: bool = True,
) -> SimpleMonitor:
    """创建简单监控器

    Args:
        export_interval: 导出间隔（秒）
        file_path: 文件路径
        console_output: 是否控制台输出

    Returns:
        简单监控器实例
    """
    return SimpleMonitor(
        export_interval=export_interval,
        file_path=file_path,
        console_output=console_output,
    )
