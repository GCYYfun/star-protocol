"""
Star Protocol 认证授权服务

提供用户认证、JWT 验证和权限管理
"""

import jwt
import hashlib
import secrets  
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

from ..protocol import Message, ClientInfo, ClientType


@dataclass
class UserCredentials:
    """用户凭证"""
    user_id: str
    username: str
    password_hash: str
    role: str = "observer"  # observer, player, admin
    permissions: Set[str] = field(default_factory=set)
    created_at: datetime = field(default_factory=datetime.now)
    last_login: Optional[datetime] = None
    is_active: bool = True


@dataclass
class APIKey:
    """API 密钥（用于 Agent 认证）"""
    key_id: str
    key_hash: str
    client_id: str
    client_type: ClientType
    permissions: Set[str] = field(default_factory=set)
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    is_active: bool = True


@dataclass  
class AuthToken:
    """认证令牌"""
    token: str
    user_id: str
    role: str
    permissions: Set[str]
    issued_at: datetime
    expires_at: datetime


class AuthenticationService:
    """认证服务"""
    
    def __init__(
        self,
        jwt_secret: str = None,
        token_expiry_hours: int = 24,
        enable_api_keys: bool = True
    ):
        self.jwt_secret = jwt_secret or self._generate_secret()
        self.token_expiry_hours = token_expiry_hours
        self.enable_api_keys = enable_api_keys
        
        # 存储（实际应该使用数据库）
        self.users: Dict[str, UserCredentials] = {}
        self.api_keys: Dict[str, APIKey] = {}
        self.active_tokens: Dict[str, AuthToken] = {}
        
        # 角色权限配置
        self.role_permissions = {
            "observer": {
                "observe_environment",
                "get_environments", 
                "get_server_stats"
            },
            "player": {
                "observe_environment",
                "control_character",
                "get_environments",
                "get_server_stats"
            },
            "admin": {
                "observe_environment",
                "control_character", 
                "admin_command",
                "spawn_item",
                "kick_user",
                "broadcast_announcement",
                "get_environments",
                "get_server_stats",
                "manage_users",
                "manage_api_keys"
            }
        }
        
        self.logger = logging.getLogger("auth_service")
        
        # 创建默认管理员用户
        self._create_default_admin()
    
    def _generate_secret(self) -> str:
        """生成 JWT 密钥"""
        return secrets.token_hex(32)
    
    def _create_default_admin(self) -> None:
        """创建默认管理员用户"""
        admin_password = "admin123"  # 实际应该从环境变量读取
        self.create_user(
            user_id="admin",
            username="admin", 
            password=admin_password,
            role="admin"
        )
        self.logger.info("Created default admin user (username: admin, password: admin123)")
    
    def create_user(
        self,
        user_id: str,
        username: str, 
        password: str,
        role: str = "observer"
    ) -> bool:
        """创建用户"""
        if user_id in self.users:
            return False
        
        password_hash = self._hash_password(password)
        permissions = self.role_permissions.get(role, set())
        
        user = UserCredentials(
            user_id=user_id,
            username=username,
            password_hash=password_hash,
            role=role,
            permissions=permissions.copy()
        )
        
        self.users[user_id] = user
        self.logger.info(f"Created user {username} with role {role}")
        return True
    
    def create_api_key(
        self,
        client_id: str,
        client_type: ClientType,
        permissions: Optional[Set[str]] = None
    ) -> Optional[str]:
        """创建 API 密钥"""
        if not self.enable_api_keys:
            return None
        
        # 生成密钥
        key = secrets.token_urlsafe(32)
        key_id = f"{client_type.value}_{client_id}_{secrets.token_hex(4)}"
        key_hash = self._hash_password(key)
        
        # 设置默认权限
        if permissions is None:
            if client_type == ClientType.AGENT:
                permissions = {"perform_action", "observe_environment"}
            elif client_type == ClientType.ENVIRONMENT:
                permissions = {"broadcast_event", "send_outcome", "manage_world_state"}
            else:
                permissions = set()
        
        api_key = APIKey(
            key_id=key_id,
            key_hash=key_hash,
            client_id=client_id,
            client_type=client_type,
            permissions=permissions,
            expires_at=datetime.now() + timedelta(days=365)  # 1年有效期
        )
        
        self.api_keys[key_id] = api_key
        self.logger.info(f"Created API key for {client_type.value} {client_id}")
        
        # 返回原始密钥（只有这一次机会获取）
        return f"{key_id}:{key}"
    
    async def authenticate_user(
        self,
        username: str,
        password: str
    ) -> Optional[AuthToken]:
        """用户认证"""
        # 查找用户
        user = None
        for u in self.users.values():
            if u.username == username and u.is_active:
                user = u
                break
        
        if not user:
            self.logger.warning(f"User not found: {username}")
            return None
        
        # 验证密码
        if not self._verify_password(password, user.password_hash):
            self.logger.warning(f"Invalid password for user: {username}")
            return None
        
        # 更新最后登录时间
        user.last_login = datetime.now()
        
        # 生成 JWT 令牌
        token = self._generate_jwt_token(user)
        
        # 创建认证令牌对象
        auth_token = AuthToken(
            token=token,
            user_id=user.user_id,
            role=user.role,
            permissions=user.permissions.copy(),
            issued_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=self.token_expiry_hours)
        )
        
        self.active_tokens[token] = auth_token
        self.logger.info(f"User {username} authenticated successfully")
        return auth_token
    
    async def authenticate_api_key(self, api_key_string: str) -> Optional[APIKey]:
        """API 密钥认证"""
        if not self.enable_api_keys:
            return None
        
        try:
            # 解析密钥格式：key_id:key
            key_id, key = api_key_string.split(':', 1)
        except ValueError:
            self.logger.warning("Invalid API key format")
            return None
        
        # 查找 API 密钥
        api_key = self.api_keys.get(key_id)
        if not api_key or not api_key.is_active:
            self.logger.warning(f"API key not found or inactive: {key_id}")
            return None
        
        # 检查是否过期
        if api_key.expires_at and datetime.now() > api_key.expires_at:
            self.logger.warning(f"API key expired: {key_id}")
            return None
        
        # 验证密钥
        if not self._verify_password(key, api_key.key_hash):
            self.logger.warning(f"Invalid API key: {key_id}")
            return None
        
        self.logger.info(f"API key authenticated: {key_id}")
        return api_key
    
    async def authenticate_message(self, message: Message) -> bool:
        """认证消息"""
        # 连接消息可能包含认证信息
        if message.type != "connect":
            return False
        
        payload = message.payload
        if not isinstance(payload, dict):
            return False
        
        action = payload.get("action", "")
        data = payload.get("data", {})
        
        # 用户认证
        if action == "authenticate":
            username = data.get("username", "")
            token = data.get("token", "")  # 可能是密码或 JWT
            
            # 尝试 JWT 认证
            if self._is_jwt_token(token):
                return await self._verify_jwt_token(token)
            
            # 尝试密码认证
            else:
                auth_token = await self.authenticate_user(username, token)
                return auth_token is not None
        
        # API 密钥认证
        elif action == "api_auth":
            api_key = data.get("api_key", "")
            if api_key:
                api_key_obj = await self.authenticate_api_key(api_key)
                return api_key_obj is not None
        
        return False
    
    def check_permission(
        self,
        user_id: str,
        required_permission: str
    ) -> bool:
        """检查用户权限"""
        user = self.users.get(user_id)
        if not user or not user.is_active:
            return False
        
        return required_permission in user.permissions
    
    def check_api_key_permission(
        self,
        key_id: str,
        required_permission: str
    ) -> bool:
        """检查 API 密钥权限"""
        api_key = self.api_keys.get(key_id)
        if not api_key or not api_key.is_active:
            return False
        
        return required_permission in api_key.permissions
    
    def _hash_password(self, password: str) -> str:
        """哈希密码"""
        salt = secrets.token_hex(16)
        password_hash = hashlib.pbkdf2_hmac(
            'sha256', 
            password.encode('utf-8'), 
            salt.encode('utf-8'), 
            100000
        )
        return f"{salt}:{password_hash.hex()}"
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """验证密码"""
        try:
            salt, hash_hex = password_hash.split(':', 1)
            password_hash_bytes = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt.encode('utf-8'),
                100000
            )
            return password_hash_bytes.hex() == hash_hex
        except ValueError:
            return False
    
    def _generate_jwt_token(self, user: UserCredentials) -> str:
        """生成 JWT 令牌"""
        payload = {
            'user_id': user.user_id,
            'username': user.username,
            'role': user.role,
            'permissions': list(user.permissions),
            'iat': datetime.utcnow(),
            'exp': datetime.utcnow() + timedelta(hours=self.token_expiry_hours)
        }
        
        return jwt.encode(payload, self.jwt_secret, algorithm='HS256')
    
    def _is_jwt_token(self, token: str) -> bool:
        """判断是否是 JWT 令牌"""
        return len(token.split('.')) == 3
    
    async def _verify_jwt_token(self, token: str) -> bool:
        """验证 JWT 令牌"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=['HS256'])
            user_id = payload.get('user_id')
            
            # 检查用户是否仍然存在且活跃
            user = self.users.get(user_id)
            if not user or not user.is_active:
                return False
            
            return True
            
        except jwt.ExpiredSignatureError:
            self.logger.warning("JWT token expired")
            return False
        except jwt.InvalidTokenError:
            self.logger.warning("Invalid JWT token")
            return False
    
    # 管理方法
    def revoke_api_key(self, key_id: str) -> bool:
        """撤销 API 密钥"""
        api_key = self.api_keys.get(key_id)
        if api_key:
            api_key.is_active = False
            self.logger.info(f"Revoked API key: {key_id}")
            return True
        return False
    
    def deactivate_user(self, user_id: str) -> bool:
        """停用用户"""
        user = self.users.get(user_id)
        if user:
            user.is_active = False
            self.logger.info(f"Deactivated user: {user_id}")
            return True
        return False
    
    def cleanup_expired_tokens(self) -> int:
        """清理过期令牌"""
        now = datetime.now()
        expired_tokens = [
            token for token, auth_token in self.active_tokens.items()
            if auth_token.expires_at < now
        ]
        
        for token in expired_tokens:
            del self.active_tokens[token]
        
        if expired_tokens:
            self.logger.info(f"Cleaned up {len(expired_tokens)} expired tokens")
        
        return len(expired_tokens)
    
    def get_user_info(self, user_id: str) -> Optional[Dict]:
        """获取用户信息"""
        user = self.users.get(user_id)
        if not user:
            return None
        
        return {
            "user_id": user.user_id,
            "username": user.username,
            "role": user.role,
            "permissions": list(user.permissions),
            "created_at": user.created_at.isoformat(),
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "is_active": user.is_active
        }
    
    def get_api_key_info(self, key_id: str) -> Optional[Dict]:
        """获取 API 密钥信息"""
        api_key = self.api_keys.get(key_id)
        if not api_key:
            return None
        
        return {
            "key_id": api_key.key_id,
            "client_id": api_key.client_id,
            "client_type": api_key.client_type.value,
            "permissions": list(api_key.permissions),
            "created_at": api_key.created_at.isoformat(),
            "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
            "is_active": api_key.is_active
        }