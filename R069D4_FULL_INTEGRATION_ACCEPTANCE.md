# R0.6.9D4 — integration acceptance & honest time-to-limit reporting

## Integrated release components (merged in this order)

- PR #14 — original user K18 source-input audit and actual Annex L/K conditions, cache fingerprint.
- PR #15 — independent TKP EN 1992-1-2-2009 Belarus National Annex fire material equations.
- PR #16 — N–Mx–My concrete/rebar finite fibres with explicit thermal eigenstrains and optional 2-axis P–Δ adapter.
- PR #17 — independent conservative TKP 2D heat transfer, humidity-dependent cp, lower thermal conductivity per Belarus NA, true boundary flux/energy audit, actual-temperature coupling.

**This stage is not a new fire classification.** It connects these four in a single merged source state and tests the exact user K18 conditions end-to-end.

## Engineering interpretation

There are three distinct concepts:

1. **Numerical equilibrium at a sampled fire minute:** solve the three section force conditions at the given temperatures. The algorithm may converge within strain limits, converge above a reference strain limit, or fail to identify an equilibrium. A solver nonconvergence is an **unknown state**.
2. **Observed section strain transition:** two adjacent, separately solved known states, *within* at time \(t_a\) and *exceeded* at \(t_b\), form a diagnostic bracket \([t_a,t_b]\). Optional midpoint refinement performs an entirely fresh thermal integration from 20 °C and new nonlinear mechanics at each midpoint. Unknown states stop refinement; decreasing strain demand later is retained, not suppressed. No monotonicity or first physical failure is asserted.
3. **Normative whole-column fire limit \(t_R\):** must involve actual load/imperfection/support conditions, instability and material/thermal validity, source fire action, and §4.3.4 validation. **Neither (1) nor (2) constitutes (3).** The official output remains \`R_t_minutes=null\` and \`normative_claim=false\`.

## K18 (user-provided actual source case)

- Concrete C30/37, natural sand and siliceous aggregate, dry density 2200 kg/m³, b=h=600 mm, L=3000 mm.
- Eight S500 Ø20 at exact coordinates from the user JSON, cover to stirrup 20 mm, stirrup Ø10.
- Four-sided standard fire, 90 min, user-entered **fire-design** \(N=50\) kN, \(M_x=2\) kN·m, \(M_y=0\) at mid-length. No second combination.
- Thermal FVM uses a **clearly labelled reference case** at initial mass moisture 1.5%, h=25 W/m²K and epsilon=0.7. These are NOT asserted to be the actual K18 material moisture or measured surface properties; the user's 44% ambient RH is not equated to mass moisture.
- Since the user's input says S500/weldable only, an actual product manufacturing process and ductility class are **unknown**. For numerical integration acceptance alone the test uses an explicitly labelled **hypothetical** hot-rolled, ductility B scenario. It does not write those assumptions back into the user's input, or certify any real design outcome.
- The original \`member_spec\` has no actual load distribution, restraints and longitudinal temperature assumption. The 2-axis member route must remain blocked; an isolated user Mx does not identify the full moment field.
- The reference fire gas is \(20+345\log_{10}(8t+1)\). At 90 min the gas is ~1006 °C. The independent TKP heat solver checks the maximum principle and detailed boundary/section/bar temperatures.

## Evidence and tests

One combined acceptance test creates the actual source-equivalent K18 model and compares the standalone K18 audit with the TKP history. It checks no mutation of input, material provenance, un-recombined fire actions, 2D thermal-to-rebar consistency, energy balance, member block and no false fire class.

The same test **prints a JSON scenario digest in GitHub Actions logs** for subsequent manual engineering review, explicitly labelled as a scenario; this provides actual K18 temperatures and diagnostics rather than uncomputed or guessed numbers. New independent tests cover within→exceeded intervals, unknown interruptions, nonmonotone recoveries and independent midpoint evaluation.

## Required future closure for normative t_R

- Reconcile actual official design standard (TKP EN 1992-1-2 with Belarus NA), fire actions EN 1991-1-2 and normal-temperature reference EN 1992-1-1 where applicable.
- Document actual reinforcing bar manufacturing process and ductility class, initial concrete mass moisture and mechanical material quality.
- Specify actual longitudinal heating/thermal axial restraint, member end conditions, initial imperfections, fire-design action distributions and compatibility to entered section N/M.
- Verify thermal **mesh and time convergence** for this geometry, qualified boundary convection/radiation, and appropriate measured temperature histories. Conservation is necessary but not sufficient for validity.
- Validate heated material response and whole-member large deformation/instability relative to appropriate physical fire tests under §4.3.4. Consider spalling, transient creep, heat-moisture coupling and initial construction imperfections.
- Implement and validate a model-dependent physical first-loss-of-capacity criterion with continuation or bifurcation/stability tracking; a scalar strain threshold or Newton failure is not a substitute.

Until these are addressed, a project-level statement "R90 confirmed" or an exact physical \(t_R\) would be unsupported. The program records this distinction and provides all diagnostic evidence for the necessary engineering work.

### Acceptance

\`\`\`bash
python -m unittest discover -s tests -p 'test_r069d4_full_integration.py' -v
python -m unittest discover -s tests -v
\`\`\`

All existing workflows must pass. The source K18 user JSON is not committed. Do not merge this PR without green checks.
