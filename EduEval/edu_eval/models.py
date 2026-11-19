"""
数据结构：题库、人设、生成的问题、评分项、报告。

全部用 dataclass，便于直接打印与序列化；不做嵌套 ORM 之类的重设计。
"""
from dataclasses import dataclass, field


@dataclass
class Checkpoint:
    """采分点：某道讲题必须讲到的点。"""
    id: str
    description: str
    is_core: bool = False
    category: str = "知识点覆盖"


@dataclass
class Pitfall:
    """典型易错点。"""
    id: str
    description: str


@dataclass
class Question:
    """讲题（题库中的一条）。"""
    id: str
    title: str
    grade: str
    task: str
    checkpoints: list[Checkpoint] = field(default_factory=list)
    pitfalls: list[Pitfall] = field(default_factory=list)
    reference_points: str = ""

    @property
    def label(self) -> str:
        return f"{self.id} {self.title}（{self.grade}）"

    @property
    def core_checkpoints(self) -> list[Checkpoint]:
        return [cp for cp in self.checkpoints if cp.is_core]


@dataclass
class Persona:
    """虚拟学生人设。"""
    id: str
    name: str
    features: str
    perspective: str


@dataclass
class GeneratedQuestion:
    """生成的学生提问。"""
    round: int
    persona_id: str
    persona_name: str
    text: str
    reference_points: list[str] = field(default_factory=list)


@dataclass
class QAPair:
    """一轮问答。"""
    question: GeneratedQuestion
    answer: str


@dataclass
class ScoreItem:
    """一个评分项（通用标准或问答标准）。"""
    category: str      # general / qa
    dimension: str     # G1/G2/G3 或 Q1/Q2/Q3
    name: str
    score: float       # 1~5
    rationale: str
    evidence: str = ""


@dataclass
class CheckpointResult:
    """采分点判定结果。"""
    checkpoint_id: str
    description: str
    status: str        # 覆盖 / 部分覆盖 / 未覆盖
    evidence: str = ""
    is_core: bool = False

    @property
    def covered(self) -> bool:
        return self.status == "覆盖"


@dataclass
class Report:
    """最终报告。"""
    session_id: str
    question: Question
    lecture: str
    qa_pairs: list[QAPair] = field(default_factory=list)
    general_scores: list[ScoreItem] = field(default_factory=list)
    qa_scores: list[ScoreItem] = field(default_factory=list)
    checkpoints: list[CheckpointResult] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    rating: str = ""
    general_avg: float = 0.0
    qa_avg: float = 0.0
    meta: dict = field(default_factory=dict)

    # ---------- 派生指标 ----------

    @property
    def covered_count(self) -> int:
        return sum(1 for cp in self.checkpoints if cp.covered)

    @property
    def total_checkpoints(self) -> int:
        return len(self.checkpoints)

    @property
    def missing_core(self) -> list[CheckpointResult]:
        return [cp for cp in self.checkpoints if cp.is_core and not cp.covered]