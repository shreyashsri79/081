"""web/src/lib/contract.ts and blend/api_models.py must describe the same JSON (plan T2)."""

import re
from pathlib import Path

import pytest

from blend import api_models as A

CONTRACT = Path(__file__).resolve().parents[1] / "web" / "src" / "lib" / "contract.ts"

# contract interface -> pydantic model
TOP = {
    "Grid": A.Grid, "Regime": A.Regime, "RunStep": A.RunStep, "RunSummary": A.RunSummary, "Run": A.Run,
    "Field": A.Field, "WeightSet": A.WeightSet, "ScoreRow": A.ScoreRow, "Scorecard": A.Scorecard,
    "ExtremeMap": A.ExtremeMap, "CellReport": A.CellReport, "Meteogram": A.Meteogram,
}
# (interface, field holding an inline object type) -> pydantic model of that inline object
INLINE = {
    ("Scorecard", "regions"): A.Region, ("ExtremeMap", "states"): A.ExtremeState,
    ("CellReport", "members"): A.Member, ("CellReport", "mseByLead"): A.MseByLead,
    ("Meteogram", "vars"): A.MeteogramVar,
}


def _blocks(src: str) -> dict[str, str]:
    """Body of every `export interface X [extends Y] { ... }`, matched by brace depth."""
    out = {}
    for m in re.finditer(r"export interface (\w+)(?: extends (\w+))? \{", src):
        depth, i = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(src[i], 0)
            i += 1
        body = src[m.end():i - 1]
        out[m.group(1)] = (m.group(2), body)
    return out


def _top_fields(body: str) -> dict[str, str]:
    """Top-level `name?: type` fields (two-space indent), with their full type text; object types may span lines."""
    out = {}
    for m in re.finditer(r"^  (\w+)\??: ", body, re.M):
        i, depth = m.end(), 0
        while i < len(body) and not (depth == 0 and body[i] == "\n"):
            depth += {"{": 1, "}": -1}.get(body[i], 0)
            i += 1
        out[m.group(1)] = body[m.end():i]
    return out


def _aliases(model) -> set[str]:
    return {f.alias or n for n, f in model.model_fields.items()}


BLOCKS = _blocks(CONTRACT.read_text())


@pytest.mark.parametrize("name", sorted(TOP))
def test_interface_fields_match(name):
    parent, body = BLOCKS[name]
    fields = set(_top_fields(body))
    if parent:
        fields |= set(_top_fields(BLOCKS[parent][1]))
    assert fields == _aliases(TOP[name]), f"{name}: contract {sorted(fields)} vs server {sorted(_aliases(TOP[name]))}"


@pytest.mark.parametrize("key", sorted(INLINE))
def test_inline_fields_match(key):
    iface, field = key
    typ = _top_fields(BLOCKS[iface][1])[field]
    inner = typ[typ.index("{") + 1:typ.rindex("}")]
    # keys of the first-level object only (skip nested braces)
    depth, flat = 0, ""
    for ch in inner:
        depth += {"{": 1, "}": -1}.get(ch, 0)
        flat += ch if depth == 0 else ""
    keys = set(re.findall(r"(\w+)\??:", flat))
    assert keys == _aliases(INLINE[key]), f"{iface}.{field}: {sorted(keys)} vs {sorted(_aliases(INLINE[key]))}"


def test_meteogram_member_inline():
    typ = _top_fields(BLOCKS["Meteogram"][1])["vars"]
    member = re.search(r"members: \{([^}]*)\}", typ, re.S).group(1)
    assert set(re.findall(r"(\w+)\??:", member)) == _aliases(A.MeteogramMember)
