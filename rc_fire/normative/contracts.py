"""R0.6.0 normative method registry and reproducible lock.

This module freezes OWNER / SOURCE / SCOPE / REQUIRED INPUT / DEPENDENCY
contracts. It does NOT implement the equations whose contracts are declared.
A registered method is not thereby a qualified method.

The two user-supplied Belarus codes are the only authoritative source editions.
The dated legacy TKP, Russian SP 468, and Mathcad are NEVER normative fallbacks.
Copyrighted PDFs and the original Mathcad file are intentionally not bundled.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from hashlib import sha256
import json
from typing import Literal

CONTRACT_VERSION = "BY-RC-FIRE-R0.6.0"
NORMATIVE_ROUTE = ("general_member", "table_3_column")

@dataclass(frozen=True)
class Source:
    id: str
    title: str
    edition: str
    role: Literal["primary_fire", "complementary_rc", "external_dependency", "historical_replay", "comparison_only"]
    effective_from: str | None
    file_sha256: str | None
    supplied: bool
    superseded_by: str | None = None

@dataclass(frozen=True)
class Method:
    id: str
    title: str
    owner: str
    primary_source: str
    clauses: tuple[str, ...]
    required_inputs: tuple[str, ...]
    produces: tuple[str, ...]
    depends_on: tuple[str, ...]
    route: Literal["both", "general_member", "table_3_column", "optional"]
    implementation: Literal["contract_only"] = "contract_only"

SOURCE_REGISTER = (
    Source("BY_SP_FIRE_2026", "СП 2.02.05-2026 — Пожарная безопасность зданий и сооружений",
           "2026", "primary_fire", "2026-11-01",
           "bbcbf459b89586d742db96a703f6e1b4af94030fef03ac18e4179eaf4621147e", True),
    Source("BY_SP_RC_2020", "СП 5.03.01-2020 — Бетонные и железобетонные конструкции",
           "2020 (предоставленное издание)", "complementary_rc", "2020-11-16",
           "bd7dc2fce046490614d208688c461fa36d73b2c44ede50a63c8237b177790678", True),
    Source("BY_SN_LOADS_2019", "СН 2.01.03-2019 — Пожарные воздействия и сочетания",
           "2019", "external_dependency", None, None, False),
    Source("BY_TKP_FIRE_2008", "ТКП 45-2.02-110-2008 — историческая методика К18",
           "2008", "historical_replay", None,
           "60fd9d7bac689d3a0d8bf1a25778d6963b47ddcc1d9f78acf572a2bbdd389bab", True,
           "BY_SP_FIRE_2026"),
    Source("RU_SP468", "СП 468.1325800.2019 (изм. 2023)",
           "2019+2023", "comparison_only", None, None, False),
    Source("XMCD_K18", "Mathcad XMCD К18 — архивный вычислительный эталон",
           "исходный файл пользователя", "historical_replay", None,
           "032bafbd7633a73286a8f64b19133abd6a6e9dd25182763ffddf019a66d8d0c6", True),
)

# Exactly one normative owner for each operation in each selected route.
# Each contract remains UNQUALIFIED through R0.6.0; the implementations will
# be supplied and tested by R0.6.1+ with explicit qualification records.
METHOD_REGISTER = (
    Method("FIRE_ACTIONS", "Пожарное сочетание и происхождение N, M, V", "actions",
           "BY_SN_LOADS_2019", ("4.3",),
           ("actions.fire_design_case", "actions.N_M_V_T", "actions.provenance"),
           ("actions.fire_effects",), (), "both"),
    Method("REBAR_GEOMETRY", "Реальная геометрия сечения и армирования", "geometry",
           "BY_SP_RC_2020", ("11.2", "11.4"),
           ("geometry", "reinforcement.bars", "reinforcement.stirrups", "reinforcement.cover"),
           ("section.geometry", "reinforcement.coordinates", "section.centroid", "section.inertias"), (), "both"),
    Method("NORMAL_MATERIALS", "Характеристики бетона и стали при нормальной температуре", "materials",
           "BY_SP_RC_2020", ("6.1.2", "6.1.3", "6.1.5", "6.2.2"),
           ("concrete.class", "concrete.consistency_or_tested_Ecm", "concrete.curing",
            "steel.grade", "concrete.material_provenance"),
           ("concrete.normal_diagram", "steel.normal_diagram"), (), "both"),
    Method("FIRE_EXPOSURE", "Нормативное огневое воздействие", "fire_exposure",
           "BY_SP_FIRE_2026", ("8.1",),
           ("fire.exposure_curve", "fire.exposed_faces", "fire.duration"),
           ("fire.boundary_temperature",), (), "general_member"),
    Method("THERMAL_MATERIALS", "Теплотехнические параметры бетона", "thermal_materials",
           "BY_SP_FIRE_2026", ("Приложение К", "К.1", "К.2"),
           ("concrete.aggregate", "concrete.dry_density", "concrete.moisture", "fire.temperature"),
           ("concrete.lambda_temperature", "concrete.heat_capacity", "concrete.a_red", "thermal.phi"),
           ("NORMAL_MATERIALS",), "general_member"),
    Method("THERMAL_FIELD", "Температуры бетона и каждого действительного стержня", "thermal",
           "BY_SP_FIRE_2026", ("8.2.19", "Приложение Ж", "Приложение К"),
           ("section.geometry", "reinforcement.coordinates", "fire.exposed_faces", "thermal.phi"),
           ("thermal.theta_concrete", "thermal.theta_bar"),
           ("REBAR_GEOMETRY", "THERMAL_MATERIALS", "FIRE_EXPOSURE"), "general_member"),
    Method("FIRE_MATERIALS", "Температурные характеристики бетона и арматуры", "temperature_factors",
           "BY_SP_FIRE_2026", ("8.2.18", "8.2.19", "Таблица 9", "Таблица 10", "Таблица 11", "Таблица 12"),
           ("concrete.class", "steel.grade", "thermal.theta_concrete", "thermal.theta_bar"),
           ("concrete.fire_diagram", "steel.fire_diagram", "materials.thermal_strains"),
           ("NORMAL_MATERIALS", "THERMAL_FIELD"), "general_member"),
    Method("SECTION_ULS", "Нормативная прочность сечения при N–Mx–My", "section_uls",
           "BY_SP_RC_2020", ("8.1.2",),
           ("actions.fire_effects", "section.geometry", "reinforcement.coordinates", "materials.fire_diagrams"),
           ("section.ultimate_surface", "section.uls_result"),
           ("FIRE_ACTIONS", "REBAR_GEOMETRY", "FIRE_MATERIALS"), "general_member"),
    Method("MEMBER_SECOND_ORDER", "Расчёт элемента, несовершенства и эффекты II порядка", "stability",
           "BY_SP_RC_2020", ("5.3", "5.4", "8.1.6"),
           ("member.supports", "member.length", "member.imperfections", "actions.fire_effects",
            "section.stiffness", "actions.section_envelope"),
           ("member.second_order_effects", "member.stability_result"),
           ("SECTION_ULS",), "general_member"),
    Method("CRITICAL_ISOTHERM", "Упрощённый метод критической изотермы с областью действия", "reduced_section",
           "BY_SP_FIRE_2026", ("8.2.21",),
           ("concrete.class", "concrete.aggregate", "section.symmetry",
            "actions.in_symmetry_plane", "reinforcement.near_extreme_faces"),
           ("thermal.critical_temperature", "section.reduced_geometry"),
           ("THERMAL_FIELD",), "optional"),
    Method("COLUMN_TABLE_3", "Табличная огнестойкость колонн с областью действия", "tabular_column",
           "BY_SP_FIRE_2026", ("8.2.11", "Таблица 3"),
           ("actions.fire_design_case", "member.eccentricity", "member.effective_length",
            "reinforcement.percentage", "section.width", "reinforcement.axis_distance"),
           ("column.tabulated_fire_resistance",),
           ("FIRE_ACTIONS", "NORMAL_MATERIALS", "REBAR_GEOMETRY"), "table_3_column"),
    Method("SPALLING_ANNEX_L", "Оценка и защитные меры от хрупкого разрушения", "spalling",
           "BY_SP_FIRE_2026", ("Приложение Л", "Л.1", "Л.2", "Л.6"),
           ("concrete.aggregate", "concrete.dry_density", "concrete.moisture", "concrete.porosity",
            "concrete.lambda_200_300", "concrete.Ecm", "concrete.mix"),
           ("spalling.F", "spalling.risk", "spalling.protection_required"),
           ("NORMAL_MATERIALS",), "both"),
    Method("FIRE_RESISTANCE", "Определение предела R(t) и обязательных проверок", "fire_resistance",
           "BY_SP_FIRE_2026", ("8.1", "8.2", "8.2.17", "8.2.22"),
           ("fire.design_duration", "all_applicable_checks", "materials.provenance"),
           ("result.R_duration", "result.compliance_evidence"),
           ("MEMBER_SECOND_ORDER", "SPALLING_ANNEX_L"), "general_member"),
    Method("TABULAR_COMPLIANCE", "Итог для разрешённого табличного пути", "fire_resistance",
           "BY_SP_FIRE_2026", ("8.2.11", "Таблица 3", "Приложение Л"),
           ("column.tabulated_fire_resistance", "spalling.protection_required", "table.scope_provenance"),
           ("result.compliance_evidence",),
           ("COLUMN_TABLE_3", "SPALLING_ANNEX_L"), "table_3_column"),
)


# A Mathcad block is a migration ticket, not permission to reuse its formula.
# 17 blocks identified in the 2026-11-06 XML audit. The archived XMCD hash is
# in SOURCE_REGISTER; no copyrighted or client-specific source is committed.
@dataclass(frozen=True)
class LegacyBlock:
    id: str
    name: str
    target_method: str
    current_status: str
    evidence: str

LEGACY_INVENTORY = (
    LegacyBlock("XMCD-01", "Входные усилия и варианты сечений", "FIRE_ACTIONS", "PARTIAL", "Верхнее сечение не завершает итоговую цепочку"),
    LegacyBlock("XMCD-02", "Единицы и размерности", "NORMAL_MATERIALS", "PARTIAL", "Ручные множители и π=3.14 в replay"),
    LegacyBlock("XMCD-03", "Таблицы ks(T), beta_s(T)", "FIRE_MATERIALS", "LEGACY_ONLY", "Перепроверка табл. 10 СП 2026 обязательна"),
    LegacyBlock("XMCD-04", "Температура при нагреве с четырёх сторон", "THERMAL_FIELD", "PARTIAL", "Фиксированные коэффициенты и ссылки на Ø25"),
    LegacyBlock("XMCD-05", "Температуры отдельных групп арматуры", "THERMAL_FIELD", "PARTIAL", "Ручные 597/355 и группировки"),
    LegacyBlock("XMCD-06", "Температурные эксцентриситеты", "MEMBER_SECOND_ORDER", "UNQUALIFIED", "Включены выключенные 0×e_t"),
    LegacyBlock("XMCD-07", "Свойства материалов при пожаре", "FIRE_MATERIALS", "PARTIAL", "Ecm=29 ГПа и неполное kc(theta)"),
    LegacyBlock("XMCD-08", "Сечение после исключения перегретого бетона", "CRITICAL_ISOTHERM", "PARTIAL", "Применимость 8.2.21 не проверяется"),
    LegacyBlock("XMCD-09", "Сжатая зона и MRd", "SECTION_ULS", "LEGACY_ONLY", "Ограничено конкретным К18"),
    LegacyBlock("XMCD-10", "Инерция реальной арматуры", "REBAR_GEOMETRY", "PARTIAL", "Встречаются фиктивные Ø0.001 и Ø0.01"),
    LegacyBlock("XMCD-11", "Номинальная жёсткость kc/phi_eff", "MEMBER_SECOND_ORDER", "PARTIAL", "Единый kc для разных осей"),
    LegacyBlock("XMCD-12", "Ncr и eta по двум осям", "MEMBER_SECOND_ORDER", "PARTIAL", "Нет общего квалифицированного расчёта элемента"),
    LegacyBlock("XMCD-13", "Совместное N–Mx–My", "SECTION_ULS", "MISSING_IN_XMCD", "Только раздельные проверки"),
    LegacyBlock("XMCD-14", "Несколько сечений по длине", "MEMBER_SECOND_ORDER", "PARTIAL", "Не выполнена полная цепочка верх-низ"),
    LegacyBlock("XMCD-15", "Индекс F, защитные меры", "SPALLING_ANNEX_L", "LEGACY_ONLY", "Старый текст отчёта; актуальное приложение Л"),
    LegacyBlock("XMCD-16", "Подстановка в динамический инженерный отчёт", "FIRE_RESISTANCE", "PARTIAL", "Нормативное происхождение формул не разделено"),
    LegacyBlock("XMCD-17", "Фактическая огнестойкость R(t)", "FIRE_RESISTANCE", "NOT_PRESENT", "Нет поиска первого отказа по времени"),
)

@dataclass(frozen=True)
class StructureCapability:
    id: str
    description: str
    stage: str
    route: str
    prerequisite: str

STRUCTURE_CAPABILITIES = (
    StructureCapability("column_rectangular", "ЖБ колонна прямоугольного сечения", "DIAGNOSTIC_ONLY", "general_member", "R0.6.1–R0.6.8 normative qualification"),
    StructureCapability("column_circular", "ЖБ колонна круглого сечения", "PLANNED", "general_member", "Heat field and axial/cross-section geometry"),
    StructureCapability("column_annular", "Полая и центрифугированная колонна", "PLANNED", "general_member", "Annex K special thermal solutions"),
    StructureCapability("beam_rect_t_i", "ЖБ балка прямоугольная, тавровая, двутавровая", "PLANNED", "general_member", "Bending/shear, exposed faces, section-ULS"),
    StructureCapability("bearing_wall", "Несущая железобетонная стена", "PLANNED", "general_member", "Combined R/E/I, slenderness, 1/2 sided heating"),
    StructureCapability("slab_solid_ribbed_hollow", "ЖБ монолитная, ребристая и пустотная плита", "PLANNED", "general_member", "R/E/I, flexure, 1 sided heating, voids"),
    StructureCapability("prestressed_rc", "Предварительно напряжённые элементы", "PLANNED", "general_member", "Prestressing thermal properties and bond"),
)

RESULT_PROVENANCE_FIELDS = (
    "source_id", "source_clause", "method_id", "backend_version",
    "input_sha256", "applicability", "qualification", "units",
)

def validate_normative_result_provenance(record: dict) -> None:
    """Validate complete evidence without accepting a claim of qualification."""
    missing = [k for k in RESULT_PROVENANCE_FIELDS if not record.get(k)]
    if missing:
        raise ValueError("Missing provenance: " + ", ".join(missing))
    sources = _sources_by_id()
    methods = _methods_by_id()
    source_id, method_id = record["source_id"], record["method_id"]
    if method_id not in methods or source_id != methods[method_id].primary_source:
        raise ValueError("Result's source / method owner mismatch")
    if sources[source_id].role in ("comparison_only", "historical_replay"):
        raise ValueError("A comparator cannot be normative result provenance")
    if record["qualification"] != "CONTRACT_ONLY":
        raise ValueError("No production-qualified calculation exists in R0.6.0")

def _sources_by_id() -> dict[str, Source]:
    return {s.id: s for s in SOURCE_REGISTER}

def _methods_by_id() -> dict[str, Method]:
    return {m.id: m for m in METHOD_REGISTER}

def methods_for_route(route: str) -> tuple[Method, ...]:
    if route not in NORMATIVE_ROUTE:
        raise ValueError(f"Unsupported normative route: {route}")
    # A route contains its direct methods and the transitive closure of their dependencies.
    methods = _methods_by_id()
    targets = {x.id for x in METHOD_REGISTER if x.route in (route, "both")}
    while True:
        expanded = targets | {d for m in targets for d in methods[m].depends_on}
        if targets == expanded:
            break
        targets = expanded
    return tuple(x for x in METHOD_REGISTER if x.id in targets)

def validate_contract_registry() -> None:
    sources = _sources_by_id()
    methods = _methods_by_id()
    if len(sources) != len(SOURCE_REGISTER) or len(methods) != len(METHOD_REGISTER):
        raise AssertionError("Duplicated normative source or method identifier")
    if len(LEGACY_INVENTORY) != 17 or len({x.id for x in LEGACY_INVENTORY}) != 17:
        raise AssertionError("Mathcad inventory must cover 17 audited blocks")
    for x in LEGACY_INVENTORY:
        if x.target_method not in methods:
            raise AssertionError(f"Orphaned Mathcad migration block: {x.id}")
    if len({x.id for x in STRUCTURE_CAPABILITIES}) != len(STRUCTURE_CAPABILITIES):
        raise AssertionError("Duplicate structure family")
    for m in METHOD_REGISTER:
        if m.primary_source not in sources:
            raise AssertionError(f"Unknown source: {m.id}")
        if not m.clauses or not m.required_inputs or not m.produces:
            raise AssertionError(f"Incomplete method contract: {m.id}")
        if m.implementation != "contract_only":
            raise AssertionError(f"R0.6.0 cannot qualify a normative algorithm: {m.id}")
        for d in m.depends_on:
            if d not in methods or d == m.id:
                raise AssertionError(f"Invalid dependency {d} for {m.id}")
        if sources[m.primary_source].role in ("historical_replay", "comparison_only"):
            raise AssertionError(f"Unapproved normative method source: {m.id}")
    visiting, visited = set(), set()
    def visit(mid):
        if mid in visiting: raise AssertionError(f"Cyclic contract dependency: {mid}")
        if mid in visited: return
        visiting.add(mid)
        for dep in methods[mid].depends_on: visit(dep)
        visiting.remove(mid)
        visited.add(mid)
    for mid in methods: visit(mid)
    for route in NORMATIVE_ROUTE:
        owners = {}
        for m in methods_for_route(route):
            if m.owner in owners and m.owner != "fire_resistance":
                raise AssertionError(f"Two normative owners {m.owner} in route {route}")
            owners[m.owner] = m.id
    if sources["BY_TKP_FIRE_2008"].superseded_by != "BY_SP_FIRE_2026":
        raise AssertionError("Historical fire code may not be current normative source")
    if sources["BY_SP_FIRE_2026"].effective_from != "2026-11-01":
        raise AssertionError("Incorrect 2026 edition effectiveness date")

def frozen_contract_manifest() -> dict:
    validate_contract_registry()
    return {
        "contract_version": CONTRACT_VERSION,
        "normative_routes": list(NORMATIVE_ROUTE),
        "sources": [asdict(s) for s in SOURCE_REGISTER],
        "methods": [asdict(m) for m in METHOD_REGISTER],
        "legacy_mathcad_inventory": [asdict(x) for x in LEGACY_INVENTORY],
        "structure_capabilities": [asdict(x) for x in STRUCTURE_CAPABILITIES],
        "result_provenance_fields": list(RESULT_PROVENANCE_FIELDS),
        "qualification": "NOT_QUALIFIED_CONTRACTS_ONLY",
        "source_policy": "BY_SP_FIRE_2026 + BY_SP_RC_2020; no implicit alternative engines",
    }

def contract_sha256() -> str:
    payload = json.dumps(frozen_contract_manifest(), sort_keys=True,
                         separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha256(payload).hexdigest()