"""
数学表达式排版：把裸露的 ^ 次方写法转成 Unicode 上标。

为什么需要：
    Markdown 渲染器（Typora、Obsidian 等）把一对 ^…^ 当作上标定界符。
    报告里只要出现「10^5 …… -1×10^5」，两个 ^ 之间的整段中文就会被吸到
    右上角做上标，版面直接乱掉。改成 Unicode 上标（10⁵、10⁻⁴）后不再有
    任何定界符：Markdown、网页、纯文本、复制进 Word 都不会串行。

约定：
    * 只处理 ^ 后面跟「一个原子」的情况：{…}、()、带符号的数字、单个字母；
    * $…$ / $$…$$ 里的 LaTeX 保持原样（那边由数学渲染器负责）；
    * 已经是 \\^ 的不重复处理；
    * 无法转成上标的字符退回转义写法 \\^，宁可显示 ^，也不让渲染器配对。
"""
import re

# Unicode 上标字符表（只收存在字形的那部分）
_SUPERSCRIPT = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻", "−": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
    "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ", "f": "ᶠ", "g": "ᵍ",
    "h": "ʰ", "i": "ⁱ", "j": "ʲ", "k": "ᵏ", "l": "ˡ", "m": "ᵐ", "n": "ⁿ",
    "o": "ᵒ", "p": "ᵖ", "r": "ʳ", "s": "ˢ", "t": "ᵗ", "u": "ᵘ", "v": "ᵛ",
    "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ",
}

# ^ 后面的一个「原子」：花括号组 / 圆括号组 / 带符号数字 / 单个字母
_EXPONENT = re.compile(
    r"(?<!\\)\^(?:(\{[^{}]*\})|(\([^()]*\))|([+\-−]?\d+)|([A-Za-z]))"
)

# 代码片段与 LaTeX 公式（这些地方不动）
_MATH_SPAN = re.compile(r"(\$\$.*?\$\$|\$[^$\n]*\$|`[^`\n]*`)", re.S)


def normalize_math(text: str) -> str:
    """把文本里的 ^ 次方统一改成 Unicode 上标；字符串其余部分原样返回。"""
    parts = _MATH_SPAN.split(text)
    for index in range(0, len(parts), 2):      # 奇数下标是被保护起来的片段
        parts[index] = _convert(parts[index])
    return "".join(parts)


def _convert(text: str) -> str:
    """转换一段普通文本里的 ^ 写法。"""
    text = _EXPONENT.sub(_replace, text)
    # 落单的 ^（后面没有可解析的内容）一律转义，防止和别的 ^ 配成一对
    return re.sub(r"(?<!\\)\^", r"\\^", text)


def _replace(match: re.Match) -> str:
    """把匹配到的 ^组 替换成上标；有字符转不了就退回转义写法。"""
    raw = next(group for group in match.groups() if group is not None)
    inner = raw[1:-1] if raw[0] in "{(" else raw

    superscript = _to_superscript(inner)
    if superscript is None:
        return "\\^" + raw
    return superscript


def _to_superscript(text: str) -> str | None:
    """逐字符转上标；表里没有的字符返回 None。"""
    pieces = [_SUPERSCRIPT.get(char) for char in text]
    if any(piece is None for piece in pieces):
        return None
    return "".join(pieces)