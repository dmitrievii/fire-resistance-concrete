"""R0.6.0 fail-closed preflight: informational contracts, never R90 approval.

The existing K18 and experimental solvers can continue to produce diagnostic
quantities. This API separates them from normative fire-resistance evidence.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math
import re
from typing import Any
from .contracts import CONTRACT_VERSION, contract_sha256, methods_for_route

class NormativeQualificationError(RuntimeError):
    """Raised if a consumer requests an unqualified normative decision."""

@dataclass(frozen=True)
class Issue:
    code: str
    severity: str
    message: str
    clause: str

    def as_dict(self):
        return asdict(self)


def select_critical_isotherm(concrete_class: str, aggregate: str | None,
                              concrete_density_type: str | None = None) -> dict:
    """Enumerate only the expressly listed values under SP 2026 §8.2.21.

    A value here establishes *material eligibility*, not permission to use
    a reduced section: section symmetry, reinforcement and action plane are
    separate mandatory checks.
    """
    match = re.fullmatch(r"C(\d+)/(\d+)", str(concrete_class or ""))
    if not match:
        return {"temperature_C": None, "status": "INSUFFICIENT_INPUT",
                "clause": "СП 2.02.05-2026, 8.2.21"}
    fc = int(match.group(1))
    if concrete_density_type != "heavy":
        return {"temperature_C": None, "status": "NOT_TABULATED_DENSITY",
                "clause": "СП 2.02.05-2026, 8.2.21"}
    if fc <= 50:
        if aggregate == "siliceous": value = 500
        elif aggregate == "calcareous": value = 600
        else:
            return {"temperature_C": None, "status": "AGGREGATE_REQUIRED",
                    "clause": "СП 2.02.05-2026, 8.2.21"}
    elif fc in (55, 60): value = 460
    elif fc in (70, 80): value = 400
    else:
        return {"temperature_C": None, "status": "NOT_TABULATED_CLASS",
                "clause": "СП 2.02.05-2026, 8.2.21"}
    return {"temperature_C": value, "status": "MATERIAL_CRITERION_ONLY",
            "clause": "СП 2.02.05-2026, 8.2.21"}


def _finite_pos(v: Any) -> float | None:
    try:
        x = float(v)
        return x if math.isfinite(x) and x > 0 else None
    except (TypeError, ValueError): return None


def evaluate_tabular_column_scope(column: dict) -> dict:
    """Check *known* limits of 2026 §8.2.11/Table 3, not fire resistance.

    The user's current mu values and N/M may be unverified. Consequently a
    geometrically eligible row is only a CANDIDATE and cannot pass compliance.
    """
    failures, missing = [], []
    b = _finite_pos(column.get("b_mm"))
    h = _finite_pos(column.get("h_mm"))
    L = _finite_pos(column.get("length_m"))
    mux = _finite_pos(column.get("mu_x"))
    muy = _finite_pos(column.get("mu_y"))
    if not all((b, h, L, mux, muy)):
        missing.append("geometry / effective lengths")
    else:
        if L * max(mux, muy) > 3.0 + 1e-10:
            failures.append("effective length exceeds 3 m")
    if b is not None and h is not None:
        try:
            As = sum(math.pi * (float(bar["diameter_mm"]) ** 2) / 4
                     for bar in column["bars"])
            if not math.isfinite(As): raise ValueError()
            if As / (b * h) > .04 + 1e-12:
                failures.append("longitudinal reinforcement exceeds 4%")
        except (ValueError, TypeError, KeyError): missing.append("reinforcement area")
    else: missing.append("section dimensions")
    sections = column.get("sections", ())
    if not sections: missing.append("fire design axial forces and eccentricities")
    for s in sections:
        N = _finite_pos(s.get("N_kN"))
        Mx = s.get("Mx_kNm"); My = s.get("My_kNm")
        if N is None or Mx is None or My is None:
            missing.append("fire action: " + str(s.get("id", "?")))
            continue
        try:
            if not all(map(math.isfinite, (float(Mx), float(My)))):
                raise ValueError()
            if h is not None and abs(float(Mx) / N) * 1000 > .15 * h + 1e-9:
                failures.append("major-axis eccentricity exceeds 0.15h: " + str(s.get("id")))
            if b is not None and abs(float(My) / N) * 1000 > .15 * b + 1e-9:
                failures.append("minor-axis eccentricity exceeds 0.15b: " + str(s.get("id")))
        except (ValueError, TypeError): missing.append("valid moments: " + str(s.get("id")))
    if not column.get("effective_length_provenance"):
        missing.append("effective_length_provenance")
    if not column.get("fire_action_provenance"):
        missing.append("fire_action_provenance")
    if not column.get("N_Rd_normal_temperature_kN"):
        missing.append("N_Rd_normal_temperature_kN for η=Nfi/NRd")
    status = "OUTSIDE_SCOPE" if failures else "INCOMPLETE" if missing else "SCOPE_CANDIDATE_UNQUALIFIED"
    return {"status":status, "failures":sorted(set(failures)),
            "missing": sorted(set(missing)), "reference":"СП 2.02.05-2026, 8.2.11, таблица 3",
            "normative_approval":False}


def audit_column(column: dict, route: str = "general_member") -> dict:
    """Build the frozen calculation contract and its blockers for one column.

    Only data proven by explicit input may satisfy a preflight input. The
    current R0.5 project model supplies no normative source for 2026 material
    tables, so a default column necessarily remains NOT_QUALIFIED.
    """
    selection = methods_for_route(route)
    issues = []
    def add(code, message, clause, severity="BLOCKER"):
        issues.append(Issue(code, severity, message, clause).as_dict())

    add("R060_CONTRACT_ONLY", "Нормативные методы заморожены как контракты, но не квалифицированы численно.",
        "R0.6.0; последующие этапы R0.6.1–R0.6.8")
    if not column.get("fire_action_provenance"):
        add("NO_FIRE_LOAD_SOURCE", "Не подтверждено происхождение пожарного сочетания усилий.",
            "СП 2.02.05-2026, 8.2.17; СН 2.01.03-2019, 4.3")
    if not column.get("exposed_faces"):
        add("ASSUMED_FOUR_SIDES", "Текущий движок не хранит явно фактические огреваемые грани.",
            "СП 2.02.05-2026, приложение К")
    if not column.get("concrete_aggregate") or not column.get("concrete_density_type"):
        add("MATERIAL_THERMAL_SCOPE_MISSING", "Не задан тип заполнителя и/или тип бетона для теплового метода.",
            "СП 2.02.05-2026, 8.2.21, приложение К")
    if not column.get("concrete_consistency_class") and not column.get("tested_Ecm_source"):
        add("E_CM_NOT_PROVEN", "Нельзя принимать Ecm из одного класса прочности.",
            "СП 5.03.01-2020, таблица 6.3")
    s = column.get("spalling") or {}
    if s.get("method") in ("sp468", "manual_k18", None):
        add("ANNEX_L_NOT_EVALUATED", "СП 468 и ручной К18 не заменяют приложение Л СП 2026.",
            "СП 2.02.05-2026, приложение Л")
    elif s.get("method") != "by2026_annex_l":
        add("UNKNOWN_SPALLING_METHOD", "Неизвестный метод оценки хрупкого разрушения.",
            "СП 2.02.05-2026, приложение Л")
    else:
        add("ANNEX_L_UNQUALIFIED", "Алгоритм приложения Л не квалифицирован в R0.6.0.",
            "СП 2.02.05-2026, приложение Л")
    if not column.get("member_support_model"):
        add("SUPPORTS_NOT_VERIFIED", "Два коэффициента μ без сведений об опорах не обосновывают второй порядок.",
            "СП 5.03.01-2020, 5.3, 8.1.6")
    if route == "table_3_column":
        scope = evaluate_tabular_column_scope(column)
        if scope["status"] == "OUTSIDE_SCOPE":
            add("TABLE_3_OUTSIDE_SCOPE", "; ".join(scope["failures"]),
                "СП 2.02.05-2026, 8.2.11, таблица 3")
        elif scope["status"] != "SCOPE_CANDIDATE_UNQUALIFIED":
            add("TABLE_3_INPUTS_MISSING", ", ".join(scope["missing"]),
                "СП 2.02.05-2026, 8.2.11, таблица 3")
    else:
        scope = select_critical_isotherm(column.get("concrete"), column.get("concrete_aggregate"),
                                        column.get("concrete_density_type"))
    if any(s.get("N_kN") is None or s.get("Mx_kNm") is None or s.get("My_kNm") is None
           for s in column.get("sections", ())):
        add("INCOMPLETE_SECTION_ACTIONS", "Не все усилия N, Mx и My заданы по сечениям.",
            "СП 5.03.01-2020, 8.1.2")
    return {
        "contract_version": CONTRACT_VERSION,
        "contract_sha256": contract_sha256(),
        "edition_fire": "СП 2.02.05-2026",
        "edition_rc": "СП 5.03.01-2020",
        "route":route,
        "method_ids":[m.id for m in selection],
        "method_qualification":"NONE_QUALIFIED_IN_R060",
        "status":"NOT_QUALIFIED",
        "normative_claim":False,
        "scope_check":scope,
        "issues":issues,
    }


def prevent_normative_claim(preflight: dict, claimed_label: str = "R90") -> None:
    """The only certification gate exported by R0.6.0 deliberately fails closed."""
    if preflight.get("normative_claim") is True or preflight.get("status") != "NOT_QUALIFIED":
        raise NormativeQualificationError("Attempt to bypass the R0.6.0 normative contract gate")
    raise NormativeQualificationError(
        f"{claimed_label}: нормативный вывод заблокирован (R0.6.0 contracts only); "
        f"{len(preflight.get('issues', []))} непроверенных условий")