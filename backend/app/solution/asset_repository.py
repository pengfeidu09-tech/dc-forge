import json
from pathlib import Path

from pydantic import ValidationError

from backend.app.contracts.solution_intelligence import SolutionAsset


class AssetRepository:
    """Strict, file-backed loader for curated SolutionAsset fixtures."""

    def __init__(self, assets_dir: Path | None = None) -> None:
        self._assets_dir = assets_dir or Path(__file__).resolve().parents[3] / "data" / "solution_assets"
        self._assets = self._load_assets()

    def list_assets(self) -> list[SolutionAsset]:
        return list(self._assets.values())

    def get_asset(self, asset_id: str) -> SolutionAsset:
        try:
            return self._assets[asset_id]
        except KeyError as error:
            raise KeyError(f"SolutionAsset not found: {asset_id}") from error

    def _load_assets(self) -> dict[str, SolutionAsset]:
        if not self._assets_dir.is_dir():
            raise FileNotFoundError(f"SolutionAsset directory not found: {self._assets_dir}")

        paths = sorted(self._assets_dir.glob("*.json"))
        if not paths:
            raise FileNotFoundError(f"No SolutionAsset JSON files found in: {self._assets_dir}")

        assets: dict[str, SolutionAsset] = {}
        for path in paths:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid SolutionAsset JSON: {path}") from error

            try:
                asset = SolutionAsset.model_validate(payload)
            except ValidationError as error:
                raise ValueError(f"Invalid SolutionAsset contract in {path}: {error}") from error

            if asset.asset_id in assets:
                raise ValueError(f"duplicate asset_id: {asset.asset_id}")
            assets[asset.asset_id] = asset
        return assets
