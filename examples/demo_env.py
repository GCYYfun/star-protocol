"""Run the new durable Environment; see examples/README.md."""
from examples.protocol_demo.client_cli import main
from examples.protocol_demo.environment import DemoEnvironment

__all__ = ["DemoEnvironment"]

if __name__ == "__main__":
    main("environment")
