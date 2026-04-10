"""客户端状态管理"""

from typing import Optional
from star_protocol.models import ClientState
from star_protocol.exceptions import InvalidStateError


class StateManager:
    """
    客户端状态管理器

    职责：
    - 管理客户端状态（DISCONNECTED/HOME/IN_ENV）
    - 管理当前环境
    - 状态转换验证
    """

    def __init__(self):
        self.state = ClientState.DISCONNECTED
        self.current_env: Optional[str] = None

    def update_state(self, new_state: ClientState) -> None:
        """
        更新状态

        Args:
            new_state: 新状态
        """
        old_state = self.state
        self.state = new_state

    def set_environment(self, env_id: Optional[str]) -> None:
        """
        设置当前环境

        Args:
            env_id: 环境 ID，None 表示离开环境
        """
        self.current_env = env_id

        if env_id:
            self.state = ClientState.IN_ENV
        else:
            self.state = ClientState.HOME

    def can_join_environment(self) -> bool:
        """检查是否可以加入环境"""
        return self.state == ClientState.HOME

    def can_leave_environment(self) -> bool:
        """检查是否可以离开环境"""
        return self.state == ClientState.IN_ENV

    def can_send_message(self) -> bool:
        """检查是否可以发送消息"""
        return self.state == ClientState.IN_ENV

    def validate_join_environment(self) -> None:
        """
        验证是否可以加入环境

        Raises:
            InvalidStateError: 状态不允许
        """
        if not self.can_join_environment():
            raise InvalidStateError(f"Cannot join environment in state {self.state}")

    def validate_leave_environment(self) -> None:
        """
        验证是否可以离开环境

        Raises:
            InvalidStateError: 状态不允许
        """
        if not self.can_leave_environment():
            raise InvalidStateError(f"Not in environment (state: {self.state})")

    def validate_send_message(self) -> None:
        """
        验证是否可以发送消息

        Raises:
            InvalidStateError: 状态不允许
        """
        if not self.can_send_message():
            raise InvalidStateError(f"Cannot send message in state {self.state}")

    def reset(self) -> None:
        """重置状态"""
        self.state = ClientState.DISCONNECTED
        self.current_env = None
