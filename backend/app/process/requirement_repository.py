"""Version-preserving local persistence for RequirementState R-M1."""

from __future__ import annotations

import json
import os
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol

from backend.app.contracts.requirement_intelligence import (
    RequirementBaseline,
    RequirementConfirmationRecord,
    RequirementState,
)


class RequirementRepository(Protocol):
    def load_state(self, project_id: str, version: int | None = None) -> RequirementState | None: ...

    def save_state(self, state: RequirementState) -> None: ...

    def list_versions(self, project_id: str) -> list[int]: ...

    def list_baseline_versions(self, project_id: str) -> list[int]: ...

    def list_baselines(self, project_id: str) -> list[RequirementBaseline]: ...

    def load_baseline(
        self, project_id: str, version: int | None = None
    ) -> RequirementBaseline | None: ...

    def save_baseline(self, baseline: RequirementBaseline) -> None: ...

    def list_confirmation_records(
        self, project_id: str
    ) -> list[RequirementConfirmationRecord]: ...

    def save_confirmation_record(self, record: RequirementConfirmationRecord) -> None: ...


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

    def _baseline_path(self, project_id: str, version: int) -> Path:
        if version < 1:
            raise ValueError("baseline version must be positive")
        return self._project_dir(project_id) / f"baseline-{version:08d}.json"

    def _confirmation_path(self, project_id: str, confirmation_id: str) -> Path:
        if (
            not confirmation_id.startswith("confirmation-")
            or len(confirmation_id) != len("confirmation-") + 12
            or any(character not in "0123456789abcdef" for character in confirmation_id.removeprefix("confirmation-"))
        ):
            raise ValueError("confirmation_id must be a deterministic confirmation hash")
        return self._project_dir(project_id) / f"{confirmation_id}.json"

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

    def list_baseline_versions(self, project_id: str) -> list[int]:
        directory = self._project_dir(project_id)
        if not directory.exists():
            return []
        versions: list[int] = []
        for path in directory.glob("baseline-*.json"):
            try:
                versions.append(int(path.stem.removeprefix("baseline-")))
            except ValueError as exc:
                raise ValueError(f"invalid repository baseline filename: {path.name}") from exc
        return sorted(versions)

    def list_baselines(self, project_id: str) -> list[RequirementBaseline]:
        return [
            baseline
            for version in self.list_baseline_versions(project_id)
            if (baseline := self.load_baseline(project_id, version)) is not None
        ]

    def save_baseline(self, baseline: RequirementBaseline) -> None:
        path = self._baseline_path(baseline.project_id, baseline.baseline_version)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(
                f"RequirementBaseline version already exists: "
                f"{baseline.project_id}/{baseline.baseline_version}"
            )
        versions = self.list_baseline_versions(baseline.project_id)
        expected = versions[-1] + 1 if versions else 1
        if baseline.baseline_version != expected:
            raise ValueError(f"RequirementBaseline next version must be {expected}")
        self._atomic_write(path, baseline.model_dump(mode="json"))

    def load_baseline(
        self,
        project_id: str,
        version: int | None = None,
    ) -> RequirementBaseline | None:
        if version is None:
            versions = self.list_baseline_versions(project_id)
            if not versions:
                return None
            version = versions[-1]
        path = self._baseline_path(project_id, version)
        if not path.exists():
            raise FileNotFoundError(
                f"RequirementBaseline version does not exist: {project_id}/{version}"
            )
        try:
            baseline = RequirementBaseline.model_validate(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid RequirementBaseline repository data: {path}") from exc
        if baseline.project_id != project_id:
            raise ValueError("repository baseline project_id does not match requested project")
        if baseline.baseline_version != version:
            raise ValueError("repository baseline version does not match requested version")
        return baseline

    def save_confirmation_record(self, record: RequirementConfirmationRecord) -> None:
        path = self._confirmation_path(record.project_id, record.confirmation_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(
                f"RequirementConfirmationRecord already exists: {record.confirmation_id}"
            )
        self._atomic_write(path, record.model_dump(mode="json"))

    def list_confirmation_records(
        self,
        project_id: str,
    ) -> list[RequirementConfirmationRecord]:
        directory = self._project_dir(project_id)
        if not directory.exists():
            return []
        records: list[RequirementConfirmationRecord] = []
        for path in sorted(directory.glob("confirmation-*.json"), key=lambda item: item.name):
            try:
                record = RequirementConfirmationRecord.model_validate(
                    json.loads(path.read_text(encoding="utf-8"))
                )
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"invalid RequirementConfirmationRecord repository data: {path}"
                ) from exc
            if record.project_id != project_id:
                raise ValueError(
                    "repository confirmation project_id does not match requested project"
                )
            if path.stem != record.confirmation_id:
                raise ValueError("repository confirmation ID does not match filename")
            records.append(record)
        return sorted(
            records,
            key=lambda record: (
                record.source_state_version,
                record.result_state_version,
                record.confirmation_id,
            ),
        )

    @staticmethod
    def _atomic_write(path: Path, payload: dict[str, object]) -> None:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
