"""Run an interactive Human with explicit receiver capabilities."""
from examples.protocol_demo.client_cli import main
from examples.protocol_demo.peers import DemoHuman

__all__ = ["DemoHuman"]

if __name__ == "__main__":
    main("human")
