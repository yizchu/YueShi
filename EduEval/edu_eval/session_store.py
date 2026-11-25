"""CLI 与 Web 共享的会话目录分配与进度文件写入。"""
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile


def reserve_session(workspace: Path) -> Path:
    workspace.mkdir(parents=True, exist_ok=True)
    base = "EV-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = 1
    while True:
        directory = workspace / (base if suffix == 1 else f"{base}-{suffix}")
        try:
            directory.mkdir()
            return directory
        except FileExistsError:
            suffix += 1


def write_snapshot(path: Path, content: str) -> None:
    """读者只会看到上一版或完整的新版本。"""
    temporary = NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False)
    staging = Path(temporary.name)
    try:
        with temporary:
            temporary.write(content)
        staging.replace(path)
    finally:
        staging.unlink(missing_ok=True)
