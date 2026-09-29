from __future__ import annotations

from job_radar.adaptive import AdaptiveCardLocator
from job_radar.models import SourceConfig, SourceKind
from job_radar.sources.base import SourceAdapter
from job_radar.sources.dynamic import DynamicAdapter
from job_radar.sources.generic import GenericListAdapter
from job_radar.sources.gupy import GupyAdapter
from job_radar.sources.indeed import IndeedAdapter


def adapter_for(
    config: SourceConfig,
    locator: AdaptiveCardLocator | None = None,
) -> SourceAdapter:
    adapters: dict[SourceKind, type[SourceAdapter]] = {
        SourceKind.GENERIC: GenericListAdapter,
        SourceKind.GUPY: GupyAdapter,
        SourceKind.INDEED: IndeedAdapter,
        SourceKind.DYNAMIC: DynamicAdapter,
    }
    return adapters[config.kind](locator=locator)


__all__ = ["SourceAdapter", "adapter_for"]
