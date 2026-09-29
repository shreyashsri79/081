"""C11 API shapes (BACKEND_BUILD_PLAN.md T2). One pydantic model per type in web/src/lib/contract.ts.

Field names are snake_case here and camelCase on the wire (alias generator). Any change to contract.ts must be
mirrored here in the same commit; tests/test_contract.py fails otherwise.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

CONTRACT_VERSION = "1.1"

ModelId = Literal["hres", "graphcast", "pangu", "fuxi", "gencast", "ifs", "aifs", "gfs"]
VarId = Literal["rain", "t2m", "wind", "mslp"]
ExtremeId = Literal["rain64", "rain115", "rain204", "heat", "wind15"]
Season = Literal["JF", "MAM", "JJAS", "OND"]
Rung = Literal["B0", "B1", "B2", "B2c", "B3s", "B3", "B3c", "B4"]
StepStatus = Literal["ok", "failed", "skipped"]

Num = float | None  # null on the wire for NaN


class Api(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Grid(Api):
    lat0: float
    lon0: float
    step: float
    ny: int
    nx: int


class Regime(Api):
    season: Season
    label: str
    basis: Literal["init", "forecast"]


class RunStep(Api):
    name: str
    status: StepStatus
    seconds: float
    note: str | None = None


class RunSummary(Api):
    id: str
    kind: Literal["live", "hindcast"]
    init: str
    status: Literal["ok", "partial", "failed"]
    models: list[ModelId]


class Run(RunSummary):
    grid: Grid
    leads: list[int]
    vars: list[VarId]
    models_by_var: dict[VarId, list[ModelId]]
    regime: Regime
    rung: Rung
    steps: list[RunStep]
    provenance: Literal["synthetic", "measured"]
    notes: list[str] | None = None


class Field(Api):
    var: VarId
    lead: int
    units: str
    values: list[Num]
    u: list[Num] | None = None
    v: list[Num] | None = None


class WeightSet(Api):
    var: VarId
    lead: int
    models: list[ModelId]
    weights: list[list[Num]]
    dominant: list[int]


class ScoreRow(Api):
    var: VarId
    lead: int
    rmse: dict[str, Num]
    best: ModelId
    delta: Num
    ci: tuple[Num, Num]


class Region(Api):
    var: VarId
    name: str
    delta: Num
    ci: tuple[Num, Num]


class Scorecard(Api):
    validation: str
    rows: list[ScoreRow]
    regions: list[Region]


class ExtremeState(Api):
    name: str
    pmax: float
    pmean: float
    cells: int


class ExtremeMap(Api):
    type: ExtremeId
    lead: int
    threshold: str
    prob: list[Num]
    states: list[ExtremeState]
    available: bool | None = None
    calibrated: bool | None = None
    method: str | None = None
    note: str | None = None


class Member(Api):
    model: ModelId
    value: Num
    weight: Num
    mse: Num
    bias: Num


class MseByLead(Api):
    model: ModelId
    mse: list[Num]


class CellReport(Api):
    i: int
    j: int
    lat: float
    lon: float
    var: VarId
    lead: int
    blend: Num
    members: list[Member]
    mse_by_lead: list[MseByLead]
    n_regime: int
    n_season: int
    k: float


class MeteogramMember(Api):
    model: ModelId
    values: list[Num]
    weights: list[Num]


class MeteogramVar(Api):
    var: VarId
    blend: list[Num]
    members: list[MeteogramMember]


class Meteogram(Api):
    i: int
    j: int
    lat: float
    lon: float
    leads: list[int]
    vars: list[MeteogramVar]


class Health(Api):
    status: str
    contract_version: str
    runs: int
    provenance: Literal["synthetic", "measured"]
