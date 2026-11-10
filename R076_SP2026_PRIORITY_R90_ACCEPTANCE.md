# R0.7.6A — SP 2.02.05-2026 is the default method

**Decision (10 Nov 2026): SP 2.02.05-2026 takes priority.** The supplied official edition states an effective date of **1 Nov 2026** (p. 1); it permits TKP EN 1992-1-2 as an alternative under §8.1.11, not as a silent replacement of SP material coefficients.

## Mandatory method routing

A. **SP2026_TABLE3** — first production acceptance target. SP §§8.2.2–8.2.5 and §8.2.11, Table 3: assess R30/R60/R90/R120/R180 for columns within the published domain using actual width b, minimum reinforcement-axis cover c, fire utilization eta = N_Sd,fi / N_Rd, effective length, eccentricity, reinforcement ratio, concrete density and aggregate. Output a normative *class verdict* only when every scope condition and spalling check is closed. **Do not invent exact collapse time from a table.**

B. **SP2026_CALCULATED_R** — SP §§8.2.16–8.2.23, SP5.03.01-2020 and SP Tables 9–12; source-specific hot concrete/steel reduction, thermal deformation and spatial member resistance. The existing TKP heat/fibre model cannot be relabelled as an SP numerical calculation. SP Tables 9/10 only tabulate material factors through 800°C; above-domain behaviour must have an explicitly qualified basis. §8.2.21 critical-isotherm simplification has restricted reinforcement and in-plane loading scope.

C. **TKP_EN1992_AS_SP_8_1_11_ALTERNATIVE** — allowed only with explicit method declaration and its distinct materials and National Annex. Preserve as a separate validated calculation route, not mixed with SP 2026 Tables 9/10.

## Conditional Table 3 R90 prospect for actual K1

Known data: 600×600 mm, concrete C30/37, siliceous aggregate, density 2200 kg/m³, 8Ø20 bars, cover 20 mm to outer face of Ø10 stirrup, 3 m length, mu_x=mu_y=1, N=50 kN, Mx=2 kNm, My=0 at the entered section.

- Minimum rebar axis distance = 20 + 10 + 20/2 = **40 mm**.
- Reinforcement ratio = 8*pi*20²/4 / (600*600) = **0.698%**, below 4%.
- Entered section eccentricity = 2 kNm / 50 kN = **40 mm**, below 0.15 * 600 = **90 mm**.
- Effective length = **3 m** only if the stated mu=1 accurately represents actual restraints.
- Table 3 at eta=0.7, **R90** offers b/c = **450/40 mm**, so actual 600/40 meets that DIMENSIONAL option; SP §8.2.4 density/aggregate domain is 1800–2600 kg/m³ siliceous concrete, encompassing the supplied 2200.

**This is not yet an R90 PASS.** Needed before output: verified SP5.03.01 normal-temperature NRd and fire eta; supported effective length and worst actual member eccentricity/load distribution; actual c including cover and tolerances; spalling / Appendix L closure, not just assumed natural sand; every additional method-table condition. The Table 3 ×1.2 bonus applies only with the documented additional welded mesh, NOT ordinary longitudinal bars. Do not extrapolate the eta rows or other prescribed limits.

## Stage acceptance order

1. **SP Table 3 production method** with source-specific input-gating, SP5 normal resistance, actual eta, every geometry/support/load/cover restriction, Appendix L closure, PASS/FAIL/NOT_ESTABLISHED, and exact_tR = null. Use the user's fire-design loads directly; do not recombine them.
2. **SP §§8.2.16–23 numerical route** with Tables9–12 and SP5 RC failure conditions; heat-transfer and material convergence, including source-defined handling beyond the 800°C table range.
3. **Actual whole-column R(t) and U(t)** with strain-compatible N–Mx–My resistance, second-order member model, end restraints, imperfections and distributed loads, physical first-failure search, independent benchmark experiments and applicability qualification.
4. Full Word report with clause/table identifiers, input provenance and verification status, without an invented normative certificate.

## Normative source notes

- SP §8.2.1 makes R depend on static scheme, loads, materials and section.
- SP §8.2.11 expressly limits Table 3 to eccentricity <=0.15h/b, effective length <=3m and longitudinal steel <=4%. Its eta is N_Sd,fi / N_Rd.
- SP §8.2.16 defines fire resistance by actual loss of load-carrying capacity.
- SP §8.2.17 separately references SN 2.01.03 §4.3 for fire loading ratio eta_fi, which must NOT be conflated with Table 3 eta.
- SP §8.2.23 permits unsteady thermal finite-difference/finite-element modelling and Annex K simplification for simple shapes.
- SP §8.2.24 and Appendix L concern concrete spalling, which is not solved by a purely structural section calculation.
- The historical Mathcad workbook is a source-specific arithmetic comparison, not a legal or scientific certification benchmark.

**Normative status today: NOT_ESTABLISHED.** Software CI green proves code regression consistency only. **Earlier audit priority implying full advanced experimental qualification before any R90 verdict is superseded for columns legitimately in Table 3 scope.**
