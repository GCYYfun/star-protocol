"""Run an interactive Agent with the same complete-demo schemas."""
from examples.protocol_demo.client_cli import main
from examples.protocol_demo.peers import DemoAgent

__all__ = ["DemoAgent"]

if __name__ == "__main__":
    main("agent")
