"""
pytest 全局配置。

把 EduEval 根目录放进 sys.path，这样 `pytest` 与 `python -m pytest`
两种跑法都能直接 `import edu_eval` / `import web`。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))