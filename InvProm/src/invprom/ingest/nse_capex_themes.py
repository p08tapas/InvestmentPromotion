from __future__ import annotations

import re
from dataclasses import dataclass

NEW_PLANT = re.compile(
    r"\b(new plant|new unit|new facility|greenfield|brownfield site|setting up (?:a |an )?(?:plant|unit|facility))\b",
    re.I,
)
CAPACITY_EXPANSION = re.compile(
    r"\b(capacity expansion|capacity addition|debottleneck|expand(?:ing)? capacity|"
    r"increase capacity|second line|additional capacity)\b",
    re.I,
)
LAND_ACQUISITION = re.compile(
    r"\b(land acquisition|acquired land|purchase of land|allotment of land|"
    r"industrial land|land parcel|land bank)\b",
    re.I,
)
CAPEX_APPROVAL = re.compile(
    r"\b(capex|capex of|capital expenditure|capital outlay|project cost|"
    r"board approved.{0,40}(?:capex|project|investment)|sanction(?:ed)?.{0,30}capex)\b",
    re.I,
)
FUNDRAISING = re.compile(
    r"\b(fund raising|fundraising|qip\b|preferential allotment|rights issue|"
    r"external commercial borrowing|ecb\b|debenture|nccd|fccb|"
    r"qualified institutions placement|raising of funds)\b",
    re.I,
)

FINANCIAL_RESULTS = re.compile(
    r"\b(financial results|unaudited financial|audited financial|quarter ended|"
    r"quarter and year ended|half year ended)\b",
    re.I,
)


@dataclass(frozen=True)
class CapexThemes:
    new_plant: bool
    capacity_expansion: bool
    land_acquisition: bool
    capex_approval: bool
    fundraising: bool
    is_financial_results: bool

    @property
    def any_trigger(self) -> bool:
        return any(
            (
                self.new_plant,
                self.capacity_expansion,
                self.land_acquisition,
                self.capex_approval,
                self.fundraising,
            )
        )

    def as_dict(self) -> dict[str, bool]:
        return {
            "new_plant": self.new_plant,
            "capacity_expansion": self.capacity_expansion,
            "land_acquisition": self.land_acquisition,
            "capex_approval": self.capex_approval,
            "fundraising": self.fundraising,
            "financial_results": self.is_financial_results,
        }


def tag_capex_themes(*parts: str | None) -> CapexThemes:
    text = " ".join(p for p in parts if p)
    return CapexThemes(
        new_plant=bool(NEW_PLANT.search(text)),
        capacity_expansion=bool(CAPACITY_EXPANSION.search(text)),
        land_acquisition=bool(LAND_ACQUISITION.search(text)),
        capex_approval=bool(CAPEX_APPROVAL.search(text)),
        fundraising=bool(FUNDRAISING.search(text)),
        is_financial_results=bool(FINANCIAL_RESULTS.search(text)),
    )
