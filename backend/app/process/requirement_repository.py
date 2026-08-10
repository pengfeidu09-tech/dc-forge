"""Version-preserving local persistence for RequirementState R-M1."""

from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol

from backend.app.contracts.requirement_intelligence import RequirementState


class RequirementRepository(Protocol):
    def load_state(self, project_id: str, version: int | None = None) -> RequirementState | None: ...

    def save_state(self, state: RequirementState) -> None: ...

    def list_versions(self, project_id: str) -> list[int]: ...


class FileRequirementRepository:
    """Stores immutable state versions as JSON with an atomic replace write."""

    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def _project_dir(self, project_id: str) -> Path:
        if not project_id:
            raise ValueError("project_id must not be blank")
        return self._root / sha256(project_id.encode("utf-8")).hexdigest()

    def _state_path(self, project_id: str, version: int) -> Path:
        if version < 1:
            raise ValueError("state version must be positive")
        return self._project_dir(project_id) / f"state-{version:08d}.json"

    def list_versions(self, project_id: str) -> list[int]:
        directory = self._project_dir(project_id)
        if not directory.exists():
            return []
        versions: list[int] = []
        for path in directory.glob("state-*.json"):
            try:
                versions.append(int(path.stem.removeprefix("state-")))
            except ValueError as exc:
                raise ValueError(f"invalid repository state filename: {path.name}") from exc
        return sorted(versions)

    def save_state(self, state: RequirementState) -> None:
        path = self._state_path(state.project_id, state.state_version)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(f"RequirementState version already exists: {state.project_id}/{state.state_version}")
        payload = json.dumps(state.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def load_state(self, project_id: str, version: int | None = None) -> RequirementState | None:
        if version is None:
            versions = self.list_versions(project_id)
            if not versions:
                return None
            version = versions[-1]
        path = self._state_path(project_id, version)
        if not path.exists():
            raise FileNotFoundError(f"RequirementState version does not exist: {project_id}/{version}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            state = RequirementState.model_validate(payload)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid RequirementState repository data: {path}") from exc
        if state.project_id != project_id:
            raise ValueError("repository project_id does not match requested project")
        if state.state_version != version:
            raise ValueError("repository state version does not match requested version")
        return state
