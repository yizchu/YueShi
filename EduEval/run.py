"""
EduEval 快速入口

用法:
    python run.py list
    python run.py run --question M-CZ-001 --lecture datasets/examples/M-CZ-001-高质量讲稿.md --dry-run
"""
import sys

from edu_eval.__main__ import main

if __name__ == "__main__":
    sys.exit(main() or 0)