from pathlib import Path


class FileTools:
    """Constrained project-local file helper for future explicit agent file operations."""

    def __init__(self, root: str = "user_files") -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe(self, name: str) -> Path:
        path = (self.root / name).resolve()
        if self.root not in path.parents and path != self.root:
            raise ValueError("File path must stay inside user_files")
        return path

    def list_files(self) -> list[str]:
        return [str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file()]

    def read_text(self, name: str) -> str:
        return self._safe(name).read_text(encoding="utf-8")
