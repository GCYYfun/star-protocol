"""
Star Protocol 日志工具

提供统一的日志配置和管理
"""

import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import json


class StarProtocolFormatter(logging.Formatter):
    """Star Protocol 自定义日志格式器"""
    
    def __init__(self, include_extra: bool = True):
        self.include_extra = include_extra
        super().__init__()
    
    def format(self, record: logging.LogRecord) -> str:
        # 基础格式
        timestamp = datetime.fromtimestamp(record.created).isoformat()
        
        log_entry = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # 添加异常信息
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # 添加额外字段
        if self.include_extra:
            extra_fields = {}
            for key, value in record.__dict__.items():
                if key not in {
                    'name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                    'filename', 'module', 'exc_info', 'exc_text', 'stack_info',
                    'lineno', 'funcName', 'created', 'msecs', 'relativeCreated',
                    'thread', 'threadName', 'processName', 'process', 'getMessage'
                }:
                    extra_fields[key] = value
            
            if extra_fields:
                log_entry["extra"] = extra_fields
        
        return json.dumps(log_entry, ensure_ascii=False, default=str)


class StarProtocolLogger:
    """Star Protocol 日志管理器"""
    
    def __init__(
        self,
        name: str = "star_protocol",
        level: str = "INFO",
        log_file: Optional[str] = None,
        max_file_size: int = 10 * 1024 * 1024,  # 10MB
        backup_count: int = 5,
        console_output: bool = True,
        json_format: bool = False
    ):
        self.name = name
        self.level = getattr(logging, level.upper())
        self.log_file = log_file
        self.max_file_size = max_file_size
        self.backup_count = backup_count
        self.console_output = console_output
        self.json_format = json_format
        
        self.logger = logging.getLogger(name)
        self.logger.setLevel(self.level)
        
        # 清除现有处理器
        self.logger.handlers.clear()
        
        # 设置处理器
        self._setup_handlers()
    
    def _setup_handlers(self) -> None:
        """设置日志处理器"""
        # 控制台处理器
        if self.console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self.level)
            
            if self.json_format:
                console_formatter = StarProtocolFormatter()
            else:
                console_formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                )
            
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)
        
        # 文件处理器
        if self.log_file:
            # 确保日志目录存在
            log_path = Path(self.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = logging.handlers.RotatingFileHandler(
                self.log_file,
                maxBytes=self.max_file_size,
                backupCount=self.backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(self.level)
            
            # 文件日志始终使用 JSON 格式便于分析
            file_formatter = StarProtocolFormatter()
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)
    
    def get_logger(self) -> logging.Logger:
        """获取 logger 实例"""
        return self.logger
    
    def add_context_filter(self, **context: Any) -> None:
        """添加上下文过滤器"""
        class ContextFilter(logging.Filter):
            def filter(self, record):
                for key, value in context.items():
                    setattr(record, key, value)
                return True
        
        self.logger.addFilter(ContextFilter())
    
    def set_level(self, level: str) -> None:
        """设置日志级别"""
        new_level = getattr(logging, level.upper())
        self.logger.setLevel(new_level)
        for handler in self.logger.handlers:
            handler.setLevel(new_level)


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    json_format: bool = False,
    console_output: bool = True
) -> logging.Logger:
    """快速设置日志"""
    star_logger = StarProtocolLogger(
        level=level,
        log_file=log_file,
        json_format=json_format,
        console_output=console_output
    )
    return star_logger.get_logger()


def get_client_logger(
    client_type: str,
    client_id: str,
    level: str = "INFO"
) -> logging.Logger:
    """获取客户端专用 logger"""
    logger_name = f"star_protocol.{client_type}.{client_id}"
    logger = logging.getLogger(logger_name)
    
    if not logger.handlers:
        # 继承根 logger 的配置
        parent_logger = logging.getLogger("star_protocol")
        if parent_logger.handlers:
            logger.setLevel(parent_logger.level)
            for handler in parent_logger.handlers:
                logger.addHandler(handler)
        else:
            # 如果没有父 logger，使用默认配置
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                f'%(asctime)s - {client_type}:{client_id} - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(getattr(logging, level.upper()))
    
    return logger


def get_hub_logger(level: str = "INFO") -> logging.Logger:
    """获取 Hub 专用 logger"""
    return get_client_logger("hub", "server", level)


class LoggerMixin:
    """日志混入类"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_logger()
    
    def _setup_logger(self) -> None:
        """设置 logger"""
        class_name = self.__class__.__name__
        self.logger = logging.getLogger(f"star_protocol.{class_name}")
    
    def log_method_call(self, method_name: str, **kwargs) -> None:
        """记录方法调用"""
        self.logger.debug(f"Calling {method_name}", extra={"method": method_name, "args": kwargs})
    
    def log_error(self, error: Exception, context: str = "") -> None:
        """记录错误"""
        self.logger.error(f"Error in {context}: {error}", exc_info=True, extra={"context": context})


# 预定义的 logger 实例
def create_default_loggers():
    """创建默认的 logger 实例"""
    # 主 logger
    main_logger = setup_logging(
        level="INFO",
        log_file="logs/star_protocol.log",
        json_format=False,
        console_output=True
    )
    
    # Hub logger
    hub_logger = get_hub_logger("INFO")
    
    return {
        "main": main_logger,
        "hub": hub_logger
    }


# 日志级别常量
class LogLevel:
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"