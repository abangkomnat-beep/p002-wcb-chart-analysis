"""Validated production route for BTCUSD Style M."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from . import style_m_daily, style_m_writer
from .unified_registry import ArticleStylesRegistry, RegistryError, RegistryLoader


UNIT_ID = "M_BTCUSD_H1_VISUAL"
STYLE_ID = style_m_daily.STYLE_ID


@dataclass(frozen=True)
class MProductionRoute:
    registry: ArticleStylesRegistry

    @classmethod
    def load(cls, path: Path | None = None) -> "MProductionRoute":
        target = path or (Path(__file__).resolve().parents[1] / "config" / "article_styles.json")
        registry = RegistryLoader().load(target)
        try:
            entry = registry.styles[STYLE_ID]
            unit = registry.execution_units[UNIT_ID]
        except KeyError as exc:
            raise RegistryError(f"missing Style M registration: {exc.args[0]}") from exc
        if tuple(unit.members) != (STYLE_ID,) or not unit.execute_once_per_asset:
            raise RegistryError(f"{UNIT_ID} ต้องมี Style M หนึ่งตัวและ execute once per asset")
        if entry.letter != style_m_daily.STYLE_LETTER:
            raise RegistryError("Style M registration ใช้ letter ผิด")
        if entry.adapter != "style_m_daily" or entry.execution_unit != UNIT_ID:
            raise RegistryError("Style M ต้องใช้ style_m_daily/M_BTCUSD_H1_VISUAL")
        if tuple(entry.assets) != style_m_daily.ASSETS or tuple(entry.timeframes) != style_m_daily.TIMEFRAMES:
            raise RegistryError("Style M assets/timeframes ไม่ตรง implementation")
        if entry.folder != style_m_daily.FOLDER or entry.failure_policy != "fail_closed":
            raise RegistryError("Style M folder/failure policy ไม่ตรง contract")
        if entry.metadata.get("contract_version") != style_m_daily.CONTRACT_VERSION:
            raise RegistryError("Style M registration ใช้ contract version ไม่ตรง runtime")
        if tuple(entry.metadata.get("public_routes") or ()) != (
                style_m_writer.ASSET_LINK, style_m_writer.ANALYSIS_LINK):
            raise RegistryError("Style M public routes ไม่ตรง writer allowlist")
        return cls(registry)

    @property
    def production(self) -> bool:
        return self.registry.styles[STYLE_ID].production

    @property
    def assets(self) -> tuple[str, ...]:
        return self.registry.styles[STYLE_ID].assets

    def run_round(self, *, asset: str, publish_root: Path, cutoff_at: str,
                  work_root: Path = Path("../work/build"), publish: bool = True,
                  _runner_kwargs: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        if asset not in self.assets:
            raise RegistryError(f"{UNIT_ID} does not support asset {asset!r}")
        return style_m_daily.run_round(asset=asset, publish_root=publish_root,
                                       work_root=work_root, cutoff_at=cutoff_at,
                                       publish=publish, **dict(_runner_kwargs or {}))


__all__ = ["MProductionRoute", "STYLE_ID", "UNIT_ID"]
