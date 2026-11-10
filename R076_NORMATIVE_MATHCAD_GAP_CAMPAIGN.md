# R0.7.6 — Belarus fire design / Mathcad K18 / Python code audit

**Date:** 2026-11-10. **Baseline:** main after PR #24.
**Verdict:** NOT NORMATIVELY VERIFIED for a reinforced-concrete whole-column fire limit R(t) or public R90 PASS/FAIL.

## Evidence sources (not redistributed)

1. Original user K18 Mathcad XMCD, parsed from XML saved values (the original Mathcad program was **not rerun**).
2. Original user report Пример.docx, including the variant 1/2 strength and demand tables.
3. Belarus СП 2.02.05-2026 §§8.1.11, 8.2.16–8.2.24 and Appendix Л.
4. Belarus СП 5.03.01-2020 for concrete and rebar reference material and RC checks.
5. Belarus ТКП EN 1992-1-2-2009 with National Annex: §§2.3,3.2,3.3,4.3.2–4.3.4,4.5.

This audit tests source math and implementation. It does **not** constitute independent professional certification.

## Three-way benchmark: never confuse original K18 with newer K1

| Data | Original K18 | Current public K1 |
|---|---|---|
| b×h | 600×600 mm | 600×600 mm |
| L, μx, μy | 13.7 m, 0.8, 1.2 | 3 m, 1, 1 |
| Section inputs | bottom N527.16 kN, Mx6.5 kNm, My0; top N1134, Mx16, My−38.9 | midspan N50, Mx2, My0 |
| Reference Ecm | 29 GPa | 41 GPa per chosen SP input catalog |
| Main bars | historical Ø20/Ø25 alternative variants | eight Ø20 at exact perimeter positions |
| Time | fixed 90-minute verification | sampled hourly fire-time diagnostic |

Original K18 saved lower-section variant2: Mrd,x=421.350648996 kNm; Med,x=162.675668214 kNm; Mrd,y=421.350649392 kNm; Med,y=175.023905603 kNm; Ncr,x≈3098.90 kN; Ncr,y≈1376.72571 kN. Report variants: v1 Mrd,x≈338.4, Med,x≈153.9, Med,y≈183.2; v2 421.3/162.6/175.0. Original R90 is **conditional on spalling control** and does not produce physical first-failure time >90 minutes.

The archived calculation_engine.py reproduces part of this original arithmetic; it has hardcoded 90-minute source choices and is not an independently qualified general fire solver.

## Mathcad source limitations to correct, not reproduce as normatively valid

- Geometry error: y12=0.6375m for b=0.6m; embedded drawing depicts another 400×600 section.
- Hand-entered steel temperatures are not automatically dependent on computed θr fields; source changes can leave stale strength reductions.
- Upper N/Mx/My defined in Mathcad but not used in final strength ratios.
- k2ax reused for the y stiffness calculation despite a different k2ay.
- Effective residual area and rectangular stiffness moment of inertia are based on inconsistent sections.
- Artificial 0.001mm/0.01mm pseudo-bars instead of real empty bar sets.
- Separate X and Y moment utilization ratios do not establish arbitrary biaxial N–Mx–My interaction.
- One R90 check is not the exact physical collapse history R(t).

## Normative source choices — never hybridize silently

At 500°C: СП 2.02.05-2026 Table9 siliceous concrete kc=0.80 and Table10 S500 ks=0.60; Belarus ТКП EN 1992-1-2 Tables3.1/3.2a siliceous kc=0.60, hot-rolled N-class S500 ks=0.78. The source-specific methods differ legitimately. In the TKP code Belarus NA selects gamma_M,fi=1, Class N rebar, and the lower conductivity formula. The original report cites older СН 2.02.05-2020 / ТКП45-2.02-110, so historical exact parity and current normative validity are distinct acceptance tasks.

## Clause traceability and blockers

| Requirement and source | Current implementation | Qualification |
|---|---|---|
| Standard fire, SP §8.2.16 | TKP 2D finite-volume solver with standard gas curve | Formula implemented; thermal boundary h=25 W/m²K, epsilon=0.7 and moisture are scenario assumptions |
| TKP §§3.2–3.4, Belarus NA | Material strength/deformation, thermal expansion, hot/cold S500, gamma=1, lower thermal conductivity | Source-formula unit tests; concrete strain law unsupported for 1100–1200°C |
| TKP §4.3.2 | 2D transient FVM, rod-centre temperatures, energy balance | Numerical energy closure verified; grid/time convergence and thermocouple benchmark NOT passed |
| TKP §4.3.3; SP §8.2.16 | Fibre N–Mx–My equilibrium at sampled time | Only section equilibrium, not full strain-compatible ultimate capacity and failure surface |
| TKP §4.3.3(4), SP §8.2.1 | Optional P–Δ member solver exists | Public input makes only one section; member_spec load_mode=not_defined, assess_member=False; supports/initial imperfections/full N,Mx,My(z) absent |
| TKP §4.3.4 | Unit/integration tests and CI | **Required external experimental validation of advanced numerical RC-column fire model absent** |
| SP §8.2.21 | Critical 500°C isotherm and historical Mathcad method | Strict scope for simple symmetric geometry, reinforcement and bending plane; cannot approve arbitrary perimeter8 biaxial geometry |
| SP §8.2.24/Appendix Л; TKP §4.5 | Spalling F index | Moisture conversion uncertainty, natural-sand assumption, spalling dynamics/protection not physically qualified |
| Real U(t) | 3-DOF Newton + LP upper capacity bound | LP lower bound on use is NOT exact member utilization or normative PASS |
| First physical R(t), R90 verdict | r07_public.py | R_t_minutes=None, regulatory_result=NOT_ESTABLISHED by construction |
| True normative report | Historical Word generator + public JSON | Public formal source-traceable Word verification not delivered |

## Acceptance campaign and priorities

**P0 blockers before a normative R rating:**
1. Freeze one applicable design edition/source route and fire-action/load design requirements. Obtain project-specific actual material/steel quality and moisture; clarify whether older SP or TKP method is being used.
2. Provide input for true whole-column support fixity, sway/imperfections, actual full-load and end-moment distributions, heated longitudinal length. Couple real N/Mx/My(z) to member; do not infer it from a single midspan moment or μ alone.
3. Verify heat-transfer and temperature-to-mechanics mesh/time convergence (especially 8×8→12×12 steel corner discrepancy ~64.43°C) and independent reference temperatures under matched boundary conditions.
4. Compute strain-compatible N–Mx–My ultimate load surface and combined member second-order loss under actual supports; prove which physical limit/bifurcation fails, not merely solver divergence.
5. Implement physically qualified R(t) time search including nonmonotone/unknown states and suitable time/mesh error interval.
6. Close spalling/protection according to the chosen code and actual composition.
7. **Experimental model validation** under TKP §4.3.4 with loaded RC-column fire-test histories (section/bar temperatures, displacement, load, supports and failure times). Independent validation set, documented uncertainty and applicability domain.
8. Make normative output conditional on all gates, including independent engineering review and auditable report.

**P1 follow-on:** corrected original K18 source fixture (real geometry, both ends, no pseudo-bars), independent current-code benchmarks and standalone professionally traceable Word report. **P2:** wider geometry, higher R class and material domains.

### Software tests vs normative evidence

Last merged full CI had **503 tests, 502 passed and one skipped**. The new, executed audit added **18 source-based regression/qualification tests**. **R0.7.6 PR #25 CI completed both workflows successfully: 521 tests executed, 520 passed, 1 skipped.** This is proof of a repeatable implementation regression campaign, NOT a fire-test validation or a code-qualification certificate.

The printed machine-readable audit digest confirms, for the current *K1 R30 demonstration* (N50/Mx2/My0), **22 thermal samples, 11 mechanical time points, eight unresolved normative blockers, member load mode not_defined, unconfirmed steel, and R_t_minutes=null, regulatory_result=NOT_ESTABLISHED**. The historical Mathcad v2 x capacity is reproduced as 421.350648996387 kN·m. The saved Mathcad output is checked, but licensed Mathcad has not been recalculated with changed geometry and no new physical fire tests have been conducted.

The new tests/test_r076_normative_mathcad_campaign.py verifies source saved outputs, Belarus source distinction, and fail-closed fire qualification.

To reproduce:

    python -m unittest discover -s tests -p 'test_r076_normative_mathcad_campaign.py' -v
    python -m unittest discover -s tests -v

**Conclusion:** Source equations and test scaffolding are real. **Normative R(t), whole-column U(t) and Rrequired PASS/FAIL remain unverified.** Do not promote the diagnostic result automatically.