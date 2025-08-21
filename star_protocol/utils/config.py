"""
Star Protocol 配置管理

提供配置文件读取、环境变量处理和配置验证
"""

import os
import json
import toml
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
import logging


@dataclass
class ServerConfig:
    """服务器配置"""
    host: str = "localhost"
    port: int = 8765
    enable_auth: bool = False
    enable_validation: bool = True
    enable_cors: bool = True
    max_connections: int = 1000
    ping_interval: int = 30
    ping_timeout: int = 10


@dataclass
class AuthConfig:
    """认证配置"""
    jwt_secret: Optional[str] = None
    token_expiry_hours: int = 24
    enable_api_keys: bool = True
    password_min_length: int = 8
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 15


@dataclass
class LoggingConfig:
    """日志配置"""
    level: str = "INFO"
    log_file: Optional[str] = "logs/star_protocol.log"
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5
    json_format: bool = False
    console_output: bool = True


@dataclass
class DatabaseConfig:
    """数据库配置（预留）"""
    url: str = "sqlite:///star_protocol.db"
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30


@dataclass
class RedisConfig:
    """Redis 配置（预留）"""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    max_connections: int = 10


@dataclass
class StarProtocolConfig:
    """Star Protocol 完整配置"""
    server: ServerConfig = field(default_factory=ServerConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    
    # 环境特定配置
    environment: str = "development"
    debug: bool = False
    
    # 协议特定配置
    message_size_limit: int = 1024 * 1024  # 1MB
    heartbeat_interval: int = 30
    client_timeout: int = 300  # 5分钟
    
    # 环境管理配置
    max_environments: int = 100
    max_agents_per_env: int = 50
    max_humans_per_env: int = 20


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file
        self.config = StarProtocolConfig()
        self.logger = logging.getLogger("config_manager")
        
        # 加载配置
        self._load_config()
        self._load_env_variables()
        self._validate_config()
    
    def _load_config(self) -> None:
        """加载配置文件"""
        if not self.config_file:
            # 尝试查找默认配置文件
            possible_files = [
                "star_protocol.toml",
                "config/star_protocol.toml",
                "configs/star_protocol.toml",
                "star_protocol.json",
                "config/star_protocol.json"
            ]
            
            for file_path in possible_files:
                if Path(file_path).exists():
                    self.config_file = file_path
                    break
        
        if not self.config_file:
            self.logger.info("No config file found, using defaults")
            return
        
        config_path = Path(self.config_file)
        if not config_path.exists():
            self.logger.warning(f"Config file not found: {self.config_file}")
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                if config_path.suffix.lower() == '.toml':
                    config_data = toml.load(f)
                else:
                    config_data = json.load(f)
            
            self._merge_config(config_data)
            self.logger.info(f"Loaded config from {self.config_file}")
            
        except Exception as e:
            self.logger.error(f"Error loading config file {self.config_file}: {e}")
    
    def _merge_config(self, config_data: Dict[str, Any]) -> None:
        """合并配置数据"""
        # 服务器配置
        if "server" in config_data:
            server_data = config_data["server"]
            for key, value in server_data.items():
                if hasattr(self.config.server, key):
                    setattr(self.config.server, key, value)
        
        # 认证配置
        if "auth" in config_data:
            auth_data = config_data["auth"]
            for key, value in auth_data.items():
                if hasattr(self.config.auth, key):
                    setattr(self.config.auth, key, value)
        
        # 日志配置
        if "logging" in config_data:
            logging_data = config_data["logging"]
            for key, value in logging_data.items():
                if hasattr(self.config.logging, key):
                    setattr(self.config.logging, key, value)
        
        # 数据库配置
        if "database" in config_data:
            db_data = config_data["database"]
            for key, value in db_data.items():
                if hasattr(self.config.database, key):
                    setattr(self.config.database, key, value)
        
        # Redis 配置
        if "redis" in config_data:
            redis_data = config_data["redis"]
            for key, value in redis_data.items():
                if hasattr(self.config.redis, key):
                    setattr(self.config.redis, key, value)
        
        # 根级配置
        root_keys = [
            "environment", "debug", "message_size_limit",
            "heartbeat_interval", "client_timeout", 
            "max_environments", "max_agents_per_env", "max_humans_per_env"
        ]
        
        for key in root_keys:
            if key in config_data and hasattr(self.config, key):
                setattr(self.config, key, config_data[key])
    
    def _load_env_variables(self) -> None:
        """加载环境变量"""
        env_mappings = {
            # 服务器配置
            "STAR_HOST": ("server", "host"),
            "STAR_PORT": ("server", "port", int),
            "STAR_ENABLE_AUTH": ("server", "enable_auth", self._parse_bool),
            "STAR_ENABLE_VALIDATION": ("server", "enable_validation", self._parse_bool),
            "STAR_MAX_CONNECTIONS": ("server", "max_connections", int),
            
            # 认证配置
            "STAR_JWT_SECRET": ("auth", "jwt_secret"),
            "STAR_TOKEN_EXPIRY_HOURS": ("auth", "token_expiry_hours", int),
            "STAR_ENABLE_API_KEYS": ("auth", "enable_api_keys", self._parse_bool),
            
            # 日志配置
            "STAR_LOG_LEVEL": ("logging", "level"),
            "STAR_LOG_FILE": ("logging", "log_file"),
            "STAR_LOG_JSON_FORMAT": ("logging", "json_format", self._parse_bool),
            
            # 环境配置
            "STAR_ENVIRONMENT": ("", "environment"),
            "STAR_DEBUG": ("", "debug", self._parse_bool),
            
            # 数据库配置
            "DATABASE_URL": ("database", "url"),
            
            # Redis 配置
            "REDIS_HOST": ("redis", "host"),
            "REDIS_PORT": ("redis", "port", int),
            "REDIS_PASSWORD": ("redis", "password"),
        }
        
        for env_var, mapping in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                if len(mapping) == 2:
                    section, key = mapping
                    converter = str
                elif len(mapping) == 3:
                    section, key, converter = mapping
                else:
                    continue
                
                try:
                    converted_value = converter(value)
                    
                    if section:
                        section_obj = getattr(self.config, section)
                        setattr(section_obj, key, converted_value)
                    else:
                        setattr(self.config, key, converted_value)
                    
                    self.logger.debug(f"Set {env_var} -> {section}.{key} = {converted_value}")
                    
                except (ValueError, TypeError) as e:
                    self.logger.warning(f"Invalid value for {env_var}: {value} ({e})")
    
    def _parse_bool(self, value: str) -> bool:
        """解析布尔值"""
        return value.lower() in ("true", "1", "yes", "on", "enabled")
    
    def _validate_config(self) -> None:
        """验证配置"""
        errors = []
        
        # 验证端口
        if not (1 <= self.config.server.port <= 65535):
            errors.append(f"Invalid port: {self.config.server.port}")
        
        # 验证日志级别
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.config.logging.level.upper() not in valid_levels:
            errors.append(f"Invalid log level: {self.config.logging.level}")
        
        # 验证认证配置
        if self.config.auth.token_expiry_hours <= 0:
            errors.append("Token expiry hours must be positive")
        
        if self.config.auth.password_min_length < 4:
            errors.append("Password minimum length too short")
        
        # 验证资源限制
        if self.config.message_size_limit <= 0:
            errors.append("Message size limit must be positive")
        
        if self.config.max_environments <= 0:
            errors.append("Max environments must be positive")
        
        if errors:
            error_msg = "Configuration validation errors:\n" + "\n".join(f"  - {err}" for err in errors)
            raise ValueError(error_msg)
        
        self.logger.info("Configuration validation passed")
    
    def get_config(self) -> StarProtocolConfig:
        """获取配置对象"""
        return self.config
    
    def save_config(self, file_path: Optional[str] = None) -> None:
        """保存配置到文件"""
        if not file_path:
            file_path = self.config_file or "star_protocol.toml"
        
        config_dict = self._config_to_dict()
        
        file_path_obj = Path(file_path)
        file_path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            if file_path_obj.suffix.lower() == '.toml':
                toml.dump(config_dict, f)
            else:
                json.dump(config_dict, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Config saved to {file_path}")
    
    def _config_to_dict(self) -> Dict[str, Any]:
        """将配置对象转换为字典"""
        return {
            "server": {
                "host": self.config.server.host,
                "port": self.config.server.port,
                "enable_auth": self.config.server.enable_auth,
                "enable_validation": self.config.server.enable_validation,
                "enable_cors": self.config.server.enable_cors,
                "max_connections": self.config.server.max_connections,
                "ping_interval": self.config.server.ping_interval,
                "ping_timeout": self.config.server.ping_timeout,
            },
            "auth": {
                "jwt_secret": self.config.auth.jwt_secret,
                "token_expiry_hours": self.config.auth.token_expiry_hours,
                "enable_api_keys": self.config.auth.enable_api_keys,
                "password_min_length": self.config.auth.password_min_length,
                "max_login_attempts": self.config.auth.max_login_attempts,
                "lockout_duration_minutes": self.config.auth.lockout_duration_minutes,
            },
            "logging": {
                "level": self.config.logging.level,
                "log_file": self.config.logging.log_file,
                "max_file_size": self.config.logging.max_file_size,
                "backup_count": self.config.logging.backup_count,
                "json_format": self.config.logging.json_format,
                "console_output": self.config.logging.console_output,
            },
            "database": {
                "url": self.config.database.url,
                "pool_size": self.config.database.pool_size,
                "max_overflow": self.config.database.max_overflow,
                "pool_timeout": self.config.database.pool_timeout,
            },
            "redis": {
                "host": self.config.redis.host,
                "port": self.config.redis.port,
                "db": self.config.redis.db,
                "password": self.config.redis.password,
                "max_connections": self.config.redis.max_connections,
            },
            "environment": self.config.environment,
            "debug": self.config.debug,
            "message_size_limit": self.config.message_size_limit,
            "heartbeat_interval": self.config.heartbeat_interval,
            "client_timeout": self.config.client_timeout,
            "max_environments": self.config.max_environments,
            "max_agents_per_env": self.config.max_agents_per_env,
            "max_humans_per_env": self.config.max_humans_per_env,
        }
    
    def create_sample_config(self, file_path: str = "star_protocol.toml") -> None:
        """创建示例配置文件"""
        sample_config = StarProtocolConfig()
        
        # 设置一些示例值
        sample_config.server.host = "0.0.0.0"
        sample_config.auth.enable_api_keys = True
        sample_config.logging.level = "INFO"
        sample_config.logging.log_file = "logs/star_protocol.log"
        
        # 临时替换配置
        original_config = self.config
        self.config = sample_config
        
        try:
            self.save_config(file_path)
            self.logger.info(f"Sample config created at {file_path}")
        finally:
            # 恢复原配置
            self.config = original_config


# 全局配置实例
_config_manager: Optional[ConfigManager] = None


def get_config(config_file: Optional[str] = None) -> StarProtocolConfig:
    """获取全局配置"""
    global _config_manager
    
    if _config_manager is None:
        _config_manager = ConfigManager(config_file)
    
    return _config_manager.get_config()


def init_config(config_file: Optional[str] = None) -> ConfigManager:
    """初始化配置管理器"""
    global _config_manager
    _config_manager = ConfigManager(config_file)
    return _config_manager