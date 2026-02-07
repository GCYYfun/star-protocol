# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Monitor 功能完整实现
  - `MonitorClient` 客户端，支持订阅和接收监控数据
  - `MonitorableMixin` 为客户端添加可监控功能
  - `MonitorManager` Hub 端监控管理器
  - Monitor 协议（EnvelopeType.MONITOR, MonitorType, MonitorPayload）
- 完整的示例代码
  - `examples/monitor_demo.py` - Monitor 功能完整演示
  - `examples/basic_agent.py` - 基础 Agent 示例
  - `examples/basic_environment.py` - 基础 Environment 示例
- 完整的文档
  - 更新 README.md，添加 Monitor 功能介绍
  - `docs/quickstart.md` - 快速开始指南
  - `docs/api_reference.md` - 完整 API 参考文档

### Changed
- 重构客户端架构，使用核心模块（Connection, State, Messaging, Lifecycle）
- 优化 Mixin 系统，支持 MonitorableMixin 和 ReconnectableMixin
- 改进错误处理和日志记录

### Fixed
- 修复 Monitor 消息发送方法（session.websocket.send_text）
- 修复方法名不匹配问题（_on_state_change, _on_message_sent/received）
- 修复无限递归问题（在监控回调中过滤 MONITOR 类型消息）
- 统一命名规范（SessionManager）

## [0.1.0] - 2024-XX-XX

### Added
- 初始版本发布
- 核心数据模型（Envelope, Payloads, Enums）
- 四种客户端类型（Agent, Environment, Human, Monitor）
- FastAPI Hub Server
- WebSocket 实时通信
- 环境管理和消息路由
- 自动重连功能
- 基础文档和示例

[Unreleased]: https://github.com/your-org/star-protocol-python/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/your-org/star-protocol-python/releases/tag/v0.1.0
