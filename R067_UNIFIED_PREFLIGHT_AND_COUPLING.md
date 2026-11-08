# R0.6.7 — Unified Normative Preflight & Automatic Thermal–Member Coupling

## Input-actions policy (R0.6.8.3)

All user-entered N, Mx and My values in every section are **already
design actions for the fire situation**. The software must never require
a second fire load combination, a separate source reference for those
actions, or an additional СН 2.01.03-2019 upload before accepting them.

- The origin of the design-action *values* is the user's project input
  convention, explicitly represented by
  `R0.6.8.3-user-supplied-fire-design-actions-v1`.
- Empty or incomplete action components still block calculations that need
  them. An absent source comment does not.
- A set of section actions does **not** automatically establish an FE
  member load diagram. R0.6.7 still needs the structural model required
  to calculate effects of second order: supports and, when applicable,
  transverse loading or nodal forces.
- Acceptance of N/M as fire-design inputs neither validates a section's
  strength nor certifies R90. Other normative blockers are unaffected.

## Scope

**Diagnostic implementation only.** Neither convergence nor a calculated
reduced-section area proves R90. The normative contract remains
`status=NOT_QUALIFIED`, `normative_claim=false`,
`fire_resistance_status=not_demonstrated`.

### Single-owner resolution

The column calculator resolves `material_spec` via R0.6.1 and
`thermal_spec` via R0.6.2 before invoking the normative preflight.
The audit uses these actual resolver outputs rather than deprecated
top-level `concrete_aggregate`, `exposed_faces`, etc.

Configured exposure is **not** verified physical exposure, and an identified
fire-actions source does **not** certify the applicable fire load combination.
Both remain separate issues. Ambiguous fine-grained versus coarse-aggregate
descriptions are reported for review.

### Opt-in uniform thermal route

For a rectangular column with the same material, geometry, heating faces,
fire exposure time and heat-transfer environment along its full length,
the user may explicitly choose:

1. `member_spec.thermal_longitudinal_mode=uniform_assumed` with an
   explanatory `uniform_fire_basis`.
2. Both actual support models (`pinned`, `fixed` or `guided`) and their
   engineering provenance. Spring and displaced support models remain
   accessible via the independent JSON route.
3. Either `axial_only` with **all Mx=My=0** or an explicit
   `uniform_transverse_load` with numeric `q_x_kNpm`/`q_y_kNpm`.
   Only complete, consistent section values of N can supply the solver's
   constant axial force. Mx/My do not infer bending load distributions.
4. An optional `fire_actions_source` note is retained for legacy
   JSON compatibility. Its absence is never a blocker: all N/M are
   already fire-design values by the project input contract.
5. A discrete FE node count (2–21).

R0.6.2 is evaluated once for the selected column. Its actual coefficients,
exposure and temperature/time are checked, then the computed temperature
object is reproduced at **each independent node and each 3-point Gauss
station**, with a unique auditable source hash and the recorded longitudinal
uniformity assumption. This is an explicit modeling *assumption*, not a
claim that the Annex K formulation independently verifies uniformity in z.

When heating is not uniform over z, the user must supply independent
computed stations via the original R0.6.4D JSON workflow.

### Fail-closed behavior

| Condition | Result |
|---|---|
| No uniformity authorization or basis | `BLOCKED_INPUT` |
| Missing supports / source/load mode | `BLOCKED_INPUT` |
| Incomplete or inconsistent axial load | `BLOCKED_INPUT` |
| Single-section nonzero moment but `axial_only` | `BLOCKED_INPUT` |
| Temperature/time mismatch | `BLOCKED_INPUT` |
| Hot boundary above material tables (>800 °C) | `BLOCKED_MATERIAL_OR_TEMPERATURE_INPUT` |
| Admissible numerical equilibrium | Diagnostic ULS evidence only |
| Any output | `normative_claim=false`, R90 not demonstrated |

### Known limitations

- Material response above 800 °C remains unqualified. R0.6.7 never
  extrapolates or quietly sets hot concrete to zero strength.
- Thermal eigenstrains and nonlinear mechanics still contain research
  assumptions, even when algebraic residuals converge.
- A column with varying N(z), unsupported end constraints, unequal
  heating along z, unknown load geometry or a nonuniform transverse
  load requires a separately authored model.
- The separate Annex L spalling route, fire load combination according
  to the governing Belarus code, full R(t) and continuous member ULS
  remain unqualified.
- The historical R0.5.6 diagnostic utilization is not a member fire
  resistance factor.

Run tests with:

```bash
python -m unittest discover -s tests -v
python -m unittest tests.test_r067_unified_coupling -v
```
