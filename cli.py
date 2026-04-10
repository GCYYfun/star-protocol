"""命令行工具"""

import argparse
import logging
import uvicorn

from app import create_hub_app


def main():
    """启动 Hub Server 的命令行入口"""
    parser = argparse.ArgumentParser(description="Star Protocol Hub Server")

    parser.add_argument(
        "--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)"
    )

    parser.add_argument(
        "--port", type=int, default=8765, help="Port to bind (default: 8765)"
    )

    parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload for development"
    )

    parser.add_argument(
        "--log-level",
        default="info",
        choices=["debug", "info", "warning", "error"],
        help="Log level (default: info)",
    )

    parser.add_argument(
        "--max-connections",
        type=int,
        default=1000,
        help="Maximum number of connections (default: 1000)",
    )

    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # 创建应用
    app = create_hub_app(max_connections=args.max_connections)

    # 启动服务器
    print(f"🚀 Starting Star Protocol Hub on {args.host}:{args.port}")
    print(
        f"📡 WebSocket endpoint: ws://{args.host}:{args.port}/ws/{{role}}/{{client_id}}"
    )
    print(f"🏥 Health check: http://{args.host}:{args.port}/health")

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
