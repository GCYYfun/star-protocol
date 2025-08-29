"""
Star Protocol V3 - agent通信协议

主要组件：
- protocol: 核心协议定义和序列化
- client: 各类客户端 SDK (Agent, Environment, Human)
- hub: 中央路由服务器
- monitor: 独立可插拔的监控工具
- cli: 交互式命令行工具
- utils: 通用工具和配置
"""

__version__ = "3.0.0"

# 子模块 (稍后实现具体类)
from . import protocol
from . import client
from . import hub
from . import monitor
from . import cli
from . import utils

__all__ = [
    # 版本
    "__version__",
    # 子模块
    "protocol",
    "client",
    "hub",
    "monitor",
    "cli",
    "utils",
]
