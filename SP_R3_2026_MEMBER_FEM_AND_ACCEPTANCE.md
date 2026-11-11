# SP-R.3 — nonlinear member coupling, numerical evidence, normative acceptance gates

**Scope and priorities.** СП 2.02.05-2026 §§8.2.16–8.2.23 has priority; static cross-section mechanics is supplemented by СП 5.03.01-2020 §§8.1.2, 8.1.6. No tabulated fire rating, Eurocode 500 °C isotherm shortcut, or TKP mechanical properties are used for the SP member law. This is a **draft diagnostic implementation**, not an SP-certified R(t) methodology.

## Mechanical equations and physical meaning

At every finite-element integration point and fire time, take the **same-source** SP-R.2 temperature field and SP-R.1 concrete and steel stress/thermal-strain laws. Use compression-positive strain `e_mech=e0+kappa_x*y+kappa_y*x+eps_th` with dimensionally consistent curvature and actual rebar locations. The section equilibrium is:

`F_sec = integral_Ac sigma_c(e_mech,T) [1,y,x] dA + sum_b As (sigma_s - sigma_c_displaced) [1,y_b,x_b]`.

At fixed prescribed physical curvatures, solve `F_sec[0]=N_fi`. Then condense the 3×3 compatible section tangent to the two bending directions:

`D_member = (J_MM - J_MN J_NN^-1 J_NM) diag(h/2,b/2)`

because the source section J differentiates moments with respect to **normalised** curvatures. Symmetry and positive eigenvalues are required for the numerical equilibrium branch; a rejected tangent is **UNKNOWN**, not proof of collapse. This code never imports TKP concrete/steel stress diagrams.

The existing full member two-axis Euler–Bernoulli beam-column integrates these laws at **3 Gauss points per element**, includes geometric stiffness (P–Δ), nodal load vector, distributed loads, end constraints and user-entered initial imperfections. Nodal sections are checked on **each adjacent side** using the actual node temperature law, not an interpolated Gauss estimate. The section checked at a selected time is **not** equivalent to a column ultimate-limit capacity.

## Mandatory input contract (no default physics invented)

For `evaluate_sp2026_member_at_time(column,thermal_snapshot,member_spec,grid=...)`:

- `load_mode="explicit_sp2026_beam"`, `fire_design_action_source` declared (actions are **already fire-design**; no duplicate combination);
- `z_m`: 3–25 strictly increasing nodes, starting at 0 and ending at actual `length_m`, full physical finite-element length;
- `N_kN>0`: constant compression, matching entered section N;
- `left_support`, `right_support`: dictionaries with **both** `x` and `y`, each pinned/fixed/guided/free; no hidden inference from `mu_x/mu_y`;
- `axial_restraint_mode="free_axial_expansion"`; axially fixed thermal reaction requires a separately modelled global axial problem;
- `distributed_load_kNpm` shape `(node_count, 2)`; `nodal_forces` and `initial_imperfection` shape `(4*node_count,)`; vectors follow [w_x0,theta_x0,w_x1,theta_x1,...,w_y0,theta_y0,...] and corresponding transverse forces/moments;
- `transverse_action_source`, `imperfection_source` declared, including if either vector consists entirely of explicitly assessed zeros;
- `entered_section_moments_reconciled=true` is required for nonzero separately input Mx/My. This is **only a user assertion**, not proof of independently verified moment compatibility; a future model must compute and compare the full longitudinal moment diagram.
- `longitudinal_thermal_mode="explicit_uniform_full_length"` with `uniform_exposure_confirmed=true`, **or** `longitudinal_thermal_mode="explicit_per_station"` and explicitly time-matched `node_snapshots` (n values) plus `gauss_snapshots` ((n-1)×3 values). A lone heated midspan section does **not** define the temperature of all beam stations.

The program checks SP-R.2 provenance, geometry, concrete family, exposed faces and exact temperature time. TKP fields, unknown times, unsupported axial restraints and absent beam load patterns are rejected. Concrete **above** 800 °C uses the explicitly user-directed zero strength/modulus assumption, never a false SP Table 9 value. Steel above 800 °C remains blocked until its material branch is justified.

The public Streamlit form now also exposes a **restricted opt-in** member scenario: explicitly confirmed pinned–pinned support along both axes, a uniform full-length fire field, first-order midspan Mx/My declared to come solely from a constant distributed transverse load (qx=8Mx/L², qy=8My/L²), and **user-entered** two-axis half-sine initial imperfection amplitudes. No activation or load conversion is automatic; if the user confirms only one of these assumptions the form fails closed. The conversion is valid only for the selected static first-order scheme, not a generic member or a frame. Other supports, end moments and arbitrary action diagrams remain accessible through the full explicit programmatic API and need fuller UI support. Initial imperfection values, including zero, remain explicitly acknowledged numerical scenarios, not automatically compliant SP5 imperfections. The UI displays the resulting member numerical limit index separately from (unknown) normative U(t) and R(t).

The `fire_assessment` public facade only activates SP-R.3 when a complete `column["member_spec"]["load_mode"]=="explicit_sp2026_beam"` is supplied. Otherwise SP-R.3 is **INPUT_REQUIRED**; earlier first-order calculations remain separately labelled and the public conclusion stays NOT_ESTABLISHED.

## Outputs and limits

- Actual `member` equilibrium, total x/y deflections, FE tangent eigenvalue, Gauss and nodal moment/strain evidence, numerical section strain index at the requested time.
- Optional separately requested and stored multi-time history `scan_sp2026_member_history`, with observed adjacent numerical strain-limit brackets only when both times are known.
- Explicit **not calculated**: `U_member_t=None`, `R_t_minutes=None`, `regulatory_result="NOT_ESTABLISHED"`, `normative_claim=false`.

**Critical distinction:** `member_model_strain_limit_index` is the maximum available *sampled strain ratio*, **not** `E_d/R_d`, a column fire utilisation ratio, or a physically proven collapse criterion. Equilibrium solver failure/nonpositive tangent is UNKNOWN; it cannot be relabelled as mechanical loss of resistance. Sampled strain-limit exceedance is not, without further material and stability proof, first global failure.

## Remaining P0 requirements before actual t_R and U(t)

1. **SP-R.1 material stiffness:** verify the role of SP Table 9/10 reduction factor beta in the adopted full nonlinear `sigma(eps,T)` relation. The current concrete parabolic-linear stress law is based on reduced strength but its initial tangent is not independently calibrated to `beta Ecm`; a numerical equilibrium is not proof that the explicit SP modulus condition is satisfied. Reconcile the SP5 parabolic law, strain parameters and temperature-reduced modulus without an invented hybrid curve.
2. **Irreversible thermal deformation:** develop time-dependent signed shrinkage/thermal creep and heating/cooling loading history from an admissible source; instantaneous integration of Tables 11–12 is explicitly provisional.
3. **Thermal boundary and transport:** source-proven convective/radiative coefficients, moisture transport, steel heat capacity effects, concrete spalling and SP Appendix Ж.7 thermocouple/reference agreement (current eight-point RMSE about 42 °C under unmatched assumptions).
4. **Frame mechanics:** complete/support real 3D member end forces, longitudinal N(z), thermal axial restraint and second-order effects, geometric imperfections, first-order moment distribution and end connection stiffness. SP5 §8.1.6 scope, biaxial coupling and shear must be judged for each project. The current solver is a small-rotation two-axis Euler–Bernoulli **single column** (not frame redistribution).
5. **Limit-state search:** distinguish physical loss of sustainable load path from numerical iteration failure. Establish a fully qualified structural `U(t)`, monitored at all critical sections and repeated under mesh/time refinement; bracket its **first** verified crossing and refine within a prescribed temporal error tolerance, checking for multiple/non-monotone branches.
6. **Independent qualification:** compare with analytical stable Euler buckling and ambient benchmarks, other FE meshes, experimental structural fire tests and independently documented material properties. Numerical Gauss-station tests or GitHub CI do not certify Belarusian R30–R180.
7. **Public inputs:** the current UI contains only the specifically confirmed pinned–pinned constant-q scheme described above; arbitrary end conditions, frame interactions, and independently entered load diagrams require additional UI and reconciliation. The existing single-section Mx/My alone cannot define such a full model. Do not silently synthesize a first-order member bending pattern from that single Mx/My.

## Verification campaign

See `tests/test_sp_r3_member.py`. It explicitly exercises the SP-R.2→SP-R.1→SP-R.3 chain, physically stable axial equilibrium and Schur tangent, full Gauss/nodal coverage, coupled two-axis imperfection and transverse loading, missing supports/restraints/temperatures rejection, per-station fields, source time mismatch and time history. All accepted results preserve `t_R=None` until the P0 gates are closed.

**Merge order:** PR #26 SP-R.1 → PR #27 SP-R.2 → PR #28 SP-R.3. Each requires green CI, review, and explicit user approval. Never merge automatically.

**SP5 steel check limit:** the R3 section fibre code now separately records the SP 5.03.01-2020 §8.1.2.1 **10‰ tensile steel verification limit** (for the section-check branch). It does not pretend to have qualified a nonlinear §6.1.5.2 or steel epsilon_ud full-member constitutive failure law. The beta-vs-parabola audit in `rc_fire/mechanics/sp2026_stiffness_audit.py` quantifies the distinct hot elastic-modulus and design-parabola tangent quantities before adopting a final member stiffness.
