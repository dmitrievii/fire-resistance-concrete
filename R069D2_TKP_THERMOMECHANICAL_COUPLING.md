# R0.6.9D2 — thermomechanical fibre interaction with TKP EN 1992-1-2

**Primary sources:** official user-provided `ТКП EN 1992-1-2-2009` with Belarus National Annex, EN 1992-1-2:2004 (IDT), and existing SP 2.02.05-2026 Annex K heat method. The licensed texts are not reproduced here. **Dependency:** R0.6.9D1 PR #15. This feature does not require or modify the user-input JSON schema.

## Calculation implemented

1. Independently compute all concrete cell-centre temperatures and **real surface-corner maxima** via the existing Annex K analytical temperature field. Build actual reinforcement cross-sections with individual bar temperatures, concrete temperatures at bar centres, correct bar area replacement and 2D fibre coordinates.
2. Resolve source material strengths from the already installed material catalog; **concrete siliceous/calcareous aggregate and thermal field must match**. The user must explicitly declare hot-rolled/cold-worked processing and reinforcement ductility A/B/C. Belarus National Annex specifies Class N and fire factor γM,fi=1.
3. Calculate positive tensile free thermal elongations for all concrete fibres, concrete at rebar centres and individual reinforcing bars (TKP §3.3.1, §3.4). With compression-positive strain convention, mechanical strain equals total compression strain **plus** positive free thermal elongation. Thus freely expanding hot concrete can attain zero stress with a negative total compression strain.
4. At each fibre compute the TKP concrete Fig. 3.1 stress/derivative and the Fig. 3.3 rebar nonlinear stress/derivative. Sum N, Mx, My and full 3×3 consistent tangent from actual concrete/stainless-rebar positions; subtract displaced concrete for each bar. **Unlike the old solver, the ultimate compressive strain varies with temperature for every fibre.**
5. Perform independent three-unknown nonlinear equilibria at the actual **fire-design** N, Mx, My in each input section. Numerically scan the fixed proportional action vector. Incomplete equations, nonconvergence, nonpositive tangents or unknown material data are **UNKNOWN, not failure**. Source-recorded strain exceedance is a *sampled diagnostic*, not proof of whole-column fire failure.
6. Provide an optional N+explicit-q second-order P–Δ member adapter from the 2×2 Schur-complement of the full three-dimensional section tangent. Repeat real thermal sections at every independent member Gauss/node station only if the user explicitly selects uniform heating in the member spec; do not infer q from a single user Mx/My entry. A failed Newton solution is not a physical collapse proof.
7. Provide optional Streamlit time histories and full JSON evidence, always keeping R_t_minutes=null, normative_claim=false.

## Critical source-domain rule at 1100–1200 °C

TKP Table 3.1 explicitly gives a concrete **strength reduction k_c** at 1200 °C (zero), but no peak or ultimate strain at 1200 °C. Interpolating these deformation endpoints from 1100 to 1200 would invent missing data. In **reject** mode, any actual heated boundary or concrete fibre in that range blocks a full law; this affects the user's K1 after 90 minutes (corner temperature about 1132 °C). In opt-in **zero_tail_diagnostic** mode the unsupported hot concrete is numerically assumed to carry zero stress; physical classification is forcibly **UNKNOWN**, even after numerical equilibrium converges. These are research bounds, not normatively certified strengths.

## Remaining high-priority engineering gates

- Implement a **consistent** EN/TKP §4.3.2 heat-transfer solver with National Annex lower conductivity, density, humidity-dependent heat capacity, emissivity and prescribed fire boundary conditions, and verify mesh/time convergence. Current section uses SP Annex K as a **labelled mixed-source diagnostic**, not a verified TKP thermal solution.
- Verify the actual material and member stress–strain law through source §4.3.4 laboratory fire tests, including transient thermal creep, spalling and cyclic/history-dependent effects. The material functions are implemented, but **not experimentally validated** as a coupled member tool.
- Obtain **ТКП EN 1992-1-1 with National Annex** and **ТКП EN 1991-1-2** for relevant room-temperature/detailing and thermal action conditions; the user's current section action inputs are accepted as already fire-design values and must not be recombined.
- Obtain **actual bar production route and ductility class**. The user's S500 and weldable_bar fields alone are insufficient.
- Obtain actual mechanical end supports, the end moments/transverse load distribution, restraint and initial imperfections for the column. The existing `mu_x=mu_y=1` is not a substitute. The single reference section with N=50kN and Mx=2kNm does not uniquely define these.
- Resolve the 1100–1200 concrete deformation gap by an explicitly substantiated method; do not silently extrapolate or call numerical conservative assumptions normative.
- Check mesh/time convergence, stable postpeak branches, curvature, full-member equilibrium and loss-of-stability criterion. Only then can an evidence-backed calculated t_R be stated.

## Release gates

```bash
python -m unittest discover -s tests -p 'test_r069d2_tkp_fibres.py' -v
python -m unittest discover -s tests -v
```

Check both GitHub workflows; do not merge without explicit user request. The current source files from the user remain private, and old SP production results are not overwritten.
