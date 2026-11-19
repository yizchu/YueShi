"""
EduEval 日志。

约定:
  * 运行状态与诊断（抽题、载入、重试、错误）走 logging，默认写 stderr；
  * 交互与结果（提问正文、回答确认、报告摘要）仍由调用方 print 到 stdout；
  * 级别由环境变量 EDUEVAL_LOG_LEVEL 控制，默认 INFO。

之所以分开：stdout 是给被试看的界面，stderr 是给开发者/运维看的痕迹，
重定向或管道时两者互不污染；库模块（如 qa_gen）因此不需要 print。
"""
from __future__ import annotations

import logging
import os
import sys

_LOGGER_NAME = "edu_eval"

# 级别 → 行首符号；INFO 不加符号，保持界面干净
_PREFIX = {
    logging.DEBUG: "· ",
    logging.INFO: "",
    logging.WARNING: "⚠ ",
    logging.ERROR: "✗ ",
    logging.CRITICAL: "✗ ",
}


class _LogFormatter(logging.Formatter):
    """极简格式：级别符号 + 消息，不输出时间/模块名。"""

    def format(self, record: logging.LogRecord) -> str:
        return f"{_PREFIX.get(record.levelno, '')}{record.getMessage()}"


def _resolve_level(level: str | int | None) -> int:
    """把级别名或数字解析成 logging 常量；无法识别时退回 INFO。"""
    if isinstance(level, int):
        return level
    name = (level or os.environ.get("EDUEVAL_LOG_LEVEL", "INFO")).upper()
    value = logging.getLevelName(name)
    return value if isinstance(value, int) else logging.INFO


def setup_logging(level: str | int | None = None) -> logging.Logger:
    """
    初始化 edu_eval 日志：写 stderr、幂等、不向 root 冒泡。

    Args:
        level: 级别名（"DEBUG"/"INFO"/"WARNING"…）或数字；省略时读
            EDUEVAL_LOG_LEVEL，再缺省 INFO
    Returns:
        edu_eval 根 logger
    """
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(_resolve_level(level))
    logger.propagate = False
    handler = next(
        (h for h in logger.handlers if getattr(h, "_edu_eval", False)), None
    )
    if handler is None:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_LogFormatter())
        handler._edu_eval = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    elif handler.stream is not sys.stderr:
        # 测试或重定向替换了 sys.stderr 时，把 handler 指回当前流
        handler.setStream(sys.stderr)
    return logger


def get_logger(name: str = "") -> logging.Logger:
    """
    取 edu_eval 命名空间下的 logger。

    Args:
        name: 通常是模块的 __name__；"edu_eval." 前缀会被去掉再加回，避免重名
    """
    suffix = name.replace(_LOGGER_NAME + ".", "").strip(".")
    return logging.getLogger(f"{_LOGGER_NAME}.{suffix}" if suffix else _LOGGER_NAME)