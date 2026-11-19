"""
配置加载：项目根 config.yaml + .env。

约定:
  * config.yaml 入库，存评分参数、温度、采样与字数阈值；
  * .env 不入库，只存 LLM 密钥与端点。
"""
import os
from pathlib import Path

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT_DIR / "config.yaml"
ENV_FILE = ROOT_DIR / ".env"

DEFAULT = {
    "llm": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    },
    "temperature": {
        "qa": 0.8,
        "score": 0.5,
        "suggestion": 0.7,
    },
    "limits": {
        "min_script_words": 300,
        "min_answer_words": 50,
        "max_script_words": 8000,
    },
    "qa": {
        "rounds": 3,
        "persona_count": 3,
    },
    "paths": {
        "datasets": "datasets",
        "workspace": "workspace",
    },
}


def _load_env():
    """读 .env（若存在），把 KEY=VALUE 注入 os.environ。不依赖 python-dotenv。"""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _merge(base: dict, override: dict) -> dict:
    """浅合并两层（够用即可，不做深度递归）。"""
    result = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = {**result[key], **value}
        else:
            result[key] = value
    return result


def _load_config() -> dict:
    _load_env()
    custom = {}
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            custom = yaml.safe_load(f) or {}
    merged = _merge(DEFAULT, custom)
    # .env 优先于 yaml（密钥只放 .env）
    merged["llm"]["api_key"] = os.environ.get("LLM_API_KEY", "")
    merged["llm"]["base_url"] = os.environ.get("LLM_BASE_URL", merged["llm"]["base_url"])
    merged["llm"]["model"] = os.environ.get("LLM_MODEL", merged["llm"]["model"])
    return merged


config = _load_config()


def path_config() -> dict:
    """把配置里的相对路径解析成绝对路径（相对项目根）。"""
    paths = config["paths"]
    return {
        "datasets": ROOT_DIR / paths["datasets"],
        "workspace": ROOT_DIR / paths["workspace"],
    }