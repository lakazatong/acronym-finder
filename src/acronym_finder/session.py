from dataclasses import dataclass
from pathlib import Path

from dataclasses_json import DataClassJsonMixin

from .config import WORKING_DIR
from .generator import GenerationRequest, GeneratorStack

SESSION_DIR = WORKING_DIR / ".sessions"


@dataclass
class GenerationResult(DataClassJsonMixin):
    acronym: str
    masks: list[list[str]]


@dataclass
class Session(DataClassJsonMixin):
    request: GenerationRequest
    generator_stack: GeneratorStack
    results: list[GenerationResult]


def make_session_path(request: GenerationRequest):
    readable = "-".join(request.words)
    readable += f"_min{request.min_len}-max{request.max_len}"

    return SESSION_DIR / f"{readable}.json"


def load_session(path: Path) -> Session | None:
    try:
        return Session.from_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def save_session(path: Path, session: Session):
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        session.to_json(indent=4),
        encoding="utf-8",
    )

    temporary.replace(path)
