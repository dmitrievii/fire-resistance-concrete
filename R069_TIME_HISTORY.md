# R0.6.9 — Fire-time member calculation

Base: R0.6.8.3, `800a4cdc4d513984edc3a3f6dced88aacc6b82b4`.

## Implemented behavior

The former member calculation evaluated one time only. This release adds a
driver from the ambient state at t=0 through the requested standard-fire
duration (up to the inherited Annex K limit of 240 minutes). Entered fire-design
N, Mx, My and the explicitly supplied member load pattern remain unchanged.
No additional fire-combination source or confirmation is requested.

At every time, including every refinement midpoint, the driver recomputes:

1. Annex K temperatures for the selected geometry, materials and heating faces.
2. Explicit node and three-point Gauss laws, under the previously accepted
   assumption of longitudinally uniform heating.
3. Two-axis member equilibrium and the geometric tangent.
4. Concrete/steel strain checks at every Gauss point and both sides of
   every member node, using the existing diagnostic constitutive model.

The first observed non-admitted state stops the coarse scan. Bisection with
fresh physical calculations narrows the observed transition to the chosen
time tolerance. No temperatures, strain ratios or events are interpolated.
The exact requested end time is included even when it is not a step multiple.
An overloaded or unresolved ambient state cannot start an admitted interval.

This follows the thermal/static/time decomposition of the user-supplied
СП 2.02.05-2026 §8.2.16 (PDF p.38). It does **not** independently qualify the
inherited hot constitutive assumptions or the whole member model.

## Interpretation

| Outcome | Returned evidence |
|---|---|
| All sampled times admitted | Sampled horizon completed; no assertion between samples |
| Equilibrated states exceed a local strain limit | Observed strain-event interval |
| Nonpositive global tangent at an equilibrium state | Observed diagnostic stability-event interval |
| Nonpositive tangent at an unbalanced Newton trial | Unresolved numerical solution, no physical failure time |
| Material/temperature range unavailable | Model-domain boundary, no physical failure time |
| Missing inputs or incomplete node/Gauss checks | Incomplete calculation, no physical failure time |
| Refinement budget exhausted | Interval retained with `tolerance_reached=false` |

`observed_limit_bracket_minutes` is supplied only for a strain or equilibrated
stability event whose interval meets the requested tolerance. The bracket
describes sampled model states. Finite time sampling cannot exclude earlier
unobserved excursions; `continuous_lower_bound_proven=false` always.

The plotted value is max(εc/εcu, εs/εsu) over assessed samples, **not** a load
capacity multiplier or a normative utilization. No unsupported scalar R is
fabricated: `fire_resistance_minutes=null`, `normative_claim=false`,
`fire_resistance_status=not_demonstrated`.

## Real limitations retained

- Tables 9/10 stop at 800 °C. The existing boundary-inclusive range check
  remains active; no extrapolation or zero-strength cutoff is introduced.
- Hot concrete ultimate strains, stiffness consistency and the integration
  convention for eigenstrains retain their qualification blockers.
- Each time is an independent quasistatic state; no creep, transient history,
  axial frame restraint or spalling damage evolution is newly modeled.
- The R0.6.7 zero-imperfection convention remains diagnostic and is explicitly
  included in the output limitations. No normative column safety follows.
- Longitudinally nonuniform histories are not inferred from a single profile.
- A finer time tolerance only narrows the numerical event bracket; it does
  not establish physical accuracy or normative qualification.

Consequently this release completes the **time-search implementation**. It
does not close normative R(t) qualification, and it does not supply a curve of
maximum load capacity versus time. Removing the load-combination blocker in
R0.6.8.3 cannot resolve the independent material/member limitations above.

## Interface and reproducibility

On a column page, configure the existing uniform-heating/member model, then
open **R0.6.9 · Несущая способность во времени R(t)**. Choose the end time,
coarse step and boundary tolerance, and click **Рассчитать R(t)**. Heavy
calculations run only on request. Results appear in the overview and in
single/combined Word reports, with JSON/CSV downloads and ZIP entries under
`time_history/`. Unrequested histories add no report section.

JSON includes the complete frozen source column, controls, time samples,
critical strain sample, residuals, tangent evidence, limitations and SHA-256.
Source edits and deleted columns invalidate cached histories and exports.
Changing the time controls clears the old result until recalculated.

```python
from rc_fire.integration.r069 import evaluate_uniform_fire_history
result = evaluate_uniform_fire_history(column, end_minutes=90.,
    step_minutes=5., tolerance_minutes=.25)
repeated = evaluate_uniform_fire_history(result['input_column'], **result['controls'])
assert repeated == result
```

## Verification

The independent Euler benchmark prescribes EI(t)=EI0(1−t/100) and
N=π²EI0/(2L²) for a pinned member. Its analytical instability occurs at
50 minutes. The actual FE solver and time driver must recover it to 0.02 min
with eight elements, while the reported bracket width is at most 0.01 min.
This checks the time/stability algorithm, not concrete material validation.

Other tests cover a known strain crossing, exact horizon, initial failure,
domain stops, Newton failure, missing node evidence, nonpositive local node
tangent, nonfinite output, exhausted refinement, actual Annex K–fibre coupling,
source immutability, signed actions, deterministic replay, Streamlit operation,
cache invalidation and Word/JSON/CSV/ZIP export.

```bash
python -m unittest discover -s tests -v
python -m tools.validate_constitutive_r064d
```
