# R0.6.9C — Fire-Time N–Mx–My Action-Path Capacity Diagnostics

## Scope and governing sources

СП 2.02.05-2026 §8.2.16–8.2.23 and tables 9–12; СП 5.03.01-2020 §§6.2.2, 8.1.2; analytical thermal method of Appendix K.

**This stage does NOT establish normative bearing capacity R(t), N_Rd, M_Rd or fire class R90.** It makes an existing N–Mx–My fibre equilibrium solver usable in a fully time-dependent, proportional fire-design action scan, and separately exposes the already implemented nonlinear 2-axis member P–Δ mechanics under an explicitly defined, independent N+q loading model. The source standards do not qualify the current numerical heated constitutive model, the linear temperature interpolation/integrated thermal-free-strain convention, or continuous second-order fire ULS. Neither positive equilibrium nor solver nonconvergence is a normative pass/fail.

## Numerical method

For each requested fire exposure time t:

1. Recompute the **original** Appendix K thermal field at this t; never reuse a field from a different time or column.
2. Validate every actual design action section: actual coordinate z, positive compressive N, finite Mx/My, distinct section ID. N, Mx and My are *already* fire-design combinations.
3. Prepare the strict full-section fibre inventory. Reject *any* boundary, concrete fibre or rebar material temperature exceeding the last 800 °C tabulation. **No** extrapolation. Continue reporting separately the valid Appendix K.27 area where available; K.27 area is not silently substituted into the full fibre model.
4. Select the literal §8.2.18 reference strength convention (fck/fyk).
5. At each specified section and fixed loading direction, solve independent fibre equilibrium for
   
   \[ {\boldsymbol F}_{\rm int}(\boldsymbol\varepsilon,t)
         = \lambda (N_{\mathrm{fi,Ed}},M_{x,\mathrm{fi,Ed}},M_{y,\mathrm{fi,Ed}}). \]
   
   Use the existing R0.6.3 simultaneous 3-variable nonlinear fibre solver, actual bar positions and 2D concrete temperatures. Every lambda starts from the solver's canonical seeds; no prior-lambda warm start.
6. Classify each lambda as **sampled equilibrium within reference strain limits**, **sampled equilibrium exceeding reference strain limits**, or **unknown**. **Unknown includes** Newton nonconvergence, nonpositive tangents and invalid domains. Never infer failure from unknown.
7. Include **lambda=1** explicitly in the scale grid. Observe all grid factors, not just the first upper threshold; multiple crossings and nonmonotonicity may exist. Subdivide a *within → exceeded* interval only while observed equilibrium classifications remain available. Every refinement interval is diagnostic, never \`lambda_Rd\`.
8. If requested and properly configured, rebuild all **explicit beam-node and Gauss-point thermal laws** and scan the *separate* 2-axis nonlinear beam with P–Δ, supports and user-specified N+qx+qy. All lambda trials deep-copy the fibre law state, preserving deterministic trial independence. Audit strains at Gauss points and both sides of member nodes. **N+q is NOT the same as the independently entered N+Mx+My.** User-provided section M fields are not converted into distributed/nodal forces, and no matching of the resulting section bending distribution is claimed. The member scan does **not** verify the separately entered section M demand when those moments are nonzero.
9. For the time history collect numerical reference-state classifications, individual section factor brackets, optionally separately configured beam factor brackets and analytical K.27 area. Only *adjacent known within → known exceeded* section reference states form a sampled time interval; UNKNOWN breaks continuity. **Never** report numerical nonconvergence, unknown material state or optimistic axial ceiling as structural failure or survival.

### Models are deliberately separate

| Output | Loads represented | Thermal/eigenstrain model | Second order | Qualification |
|---|---|---|---|---|
| Section action-path | Every entered N, Mx, My independently per section | Appendix K full-section temperatures; R0.6.3 fibre law; free thermal strain **not included** | No | Research diagnostic |
| Member load-path | Explicit N, qx, qy, supports; user confirms uniform temperature along z | Appendix K at every Gauss/node station; integrated free-strain *assumption* | Nonlinear P–Δ | Research diagnostic; no proof of correspondence to entered Mx/My |
| K.27 reduced area | Square, 4-side heating, analytic K.20–K.28 | Analytic isotherm | No | Geometry only, §8.2.21 scope restrictions remain |
| Normative R(t) | Full member fire-design loads and thermal history | Must be independently qualified | Must be qualified | **NOT IMPLEMENTED** |

### Explicit remaining blockers to real R(t)

- A qualified, whole-temperature-range heated constitutive model and free/induced thermal strain history, including material outside the 800 °C table where applicable; validated spalling and creep.
- Numerically and normatively established heated section N–Mx–My interaction with all limiting strain criteria and global second-order stability with real imperfections, restraint and boundary conditions.
- Transfer/reconciliation of actual fire-design longitudinal Mx/My diagrams with the end loads, distributed loads and restraint moments used by the FE beam; the design sections are not a unique transverse load history.
- Reliable full longitudinal thermal distribution (or an engineer-supported uniform assumption) and proof of continuous member failure criteria.
- A validated method for first-failure time, branch loss and continuous time interval; neither sampled load factors nor coarse heating-time brackets establish this.
- The relevant provisions of СП 5.03.01 and СП 2.02.05 are necessary, not sufficient, for the program to issue a project-level R90 statement.

## Runtime controls and acceptance

The R0.6.9C Streamlit expander is **opt-in**. Defaults: fire-time step 30 min, maximum 12 time points; factor grid increment 0.5 to lambda=2; 4 midpoint refinements. The second-order beam scan must be explicitly enabled, and additionally requires the R0.6.7 support/thermal/load configuration. Run-time and memory scale with number of sections, time points and factor samples.

Targeted:

\`\`\`bash
python -m unittest discover -s tests -p 'test_r069c_capacity.py' -v
python -m unittest discover -s tests -v
\`\`\`

**Release gate:** full existing calculation/Streamlit/Word contract tests and R0.6.4D integrated tests must pass, with changes confined to a PR; do not merge without user authorization.
