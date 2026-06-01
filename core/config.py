"""统一配置管理模块，提供单例模式的 YAML 配置加载与缓存。"""

from pathlib import Path
from typing import Any, Dict

import yaml


class _ConfigManager:
    """配置管理器，类级别缓存已加载的配置，避免重复 I/O。"""

    _config: Dict[str, Any] | None = None

    @classmethod
    def load_config(cls, config_path: str = "config.yaml") -> Dict[str, Any]:
        """加载 YAML 配置文件，首次调用后缓存。

        参数:
            config_path: 配置文件路径，默认 "config.yaml"。

        返回:
            解析后的配置字典。若文件不存在则抛出 FileNotFoundError。
        """
        if cls._config is None:
            cfg_path = Path(config_path)
            if not cfg_path.exists():
                raise FileNotFoundError(f"配置文件不存在: {config_path}")

            with open(cfg_path, "r", encoding="utf-8") as f:
                cls._config = yaml.safe_load(f) or {}

        return cls._config

    @classmethod
    def reload_config(cls, config_path: str = "config.yaml") -> Dict[str, Any]:
        """强制重新加载配置文件，清除缓存后重新读取。

        参数:
            config_path: 配置文件路径，默认 "config.yaml"。

        返回:
            重新解析后的配置字典。
        """
        cls._config = None
        return cls.load_config(config_path)


def get_config() -> Dict[str, Any]:
    """获取当前配置的便捷函数。

    返回:
        缓存的配置字典。首次调用时自动加载 config.yaml。
    """
    return _ConfigManager.load_config()
