# R0.6.9B — Critical Isotherm Section Route & Explicit Applicability Gate

**Implementation type:** Normative formula provenance for Annex K.27 **geometry**, conservative physical/action applicability screening under СП 2.02.05-2026 §8.2.21, and a separately marked *non-normative* axial ceiling diagnostic. **NOT** a qualified N–Mx–My bearing-capacity solver or calculated resistance time R(t).

## Verified normative basis (user-supplied СП 2.02.05-2026 PDF)

- §8.2.16 (PDF p.38): define R by loss of carrying ability; solve thermal history first, then static resistance at each selected time.
- §8.2.18, tables 9/10 (PDF pp.38–39): concrete and rebar strength-modifier values through **800 °C**, no higher-temperature coefficients given. No extrapolation.
- §8.2.20 (PDF p.39): permits selected SP 5.03.01–2020 concrete and steel stress–strain relationships with temperature modification; it does **not** independently establish the whole-member ULS.
- §8.2.21 (PDF pp.39–40): critical-isotherm reduced area is permitted only for **simple symmetric cross sections**, with reinforcement concentrated at the **most compressed and most tensioned faces**, and **actions in a symmetry plane**. The section's permitted reduced area is not blanket permission for an arbitrary biaxial N+Mx+My interaction.
- Appendix K §K.3.4 (PDF p.153), Eq. K.27: exact analytical `F1 = psi * (h - 2 lc,cr)^2` for a **square section heated on four sides**, using Eqs. K.20–K.28 and the K.28 upper cap `psi <= 1`.

## What this implementation does

1. Reuse the already independently unit-tested analytical K.27 implementation from R0.6.2, including all its out-of-domain guards; no pixel-count area is substituted for K.27.
2. Separate `K27_ANALYTIC_AREA_ONLY` from the stricter §8.2.21 check for section-action and reinforcement layout. Four heated faces, square shape, actual material and thermal scope are required for the candidate branch.
3. Reject incomplete section actions; treat all entered `N, Mx, My` as **already fire-design efforts** and never recombine them. Require a **single** nonzero bending axis across *all* supplied design sections; reject biaxial, mixed-axis and zero-axis cases as outside this deliberately narrow implementation.
4. Require actual bar positions in exactly **two** bar-centre layers along the bending axis, symmetrical about that section's centreline, and diameter/position symmetry about both coordinates. This is a **conservative computational admission rule**, not a newly invented normative tolerance for the words "at the extreme faces".
5. Inspect all individual actual Annex K bar temperatures. Above **800 °C**, no material coefficients are extrapolated. The analytical K.27 area can still be reported independently while the strength-related diagnostic remains unavailable.
6. If supported for the diagnostic only, report an intentionally **optimistic upper ceiling for axial force**:
   
   `N_optimistic_upper = 1000 * F_K27 * fck + 1000 * sum(As_i * fyk * ks(theta_i))` (kN; MPa, m²).

   This is a *necessary-condition screening ceiling*, **NOT** the actual `N_Rd`. It deliberately overcounts reinforcement-displaced concrete, allows all contributions to attain maxima simultaneously, ignores bending interaction, second-order effects and temperature-induced forces, and is never issued as a positive safety/strength conclusion. Using `fck` and `fyk` follows the literal strength-reference of §8.2.18 as a non-normative idealized ceiling. Between steel table nodes and from 20–200 °C there are explicitly identified engineering interpolation conventions.
7. The opt-in Streamlit panel computes one specified time or a sampled history (fresh Annex K evaluation at every timestamp) and exports the raw audit. `R_t_minutes=None`, `N_Rd_kN=None`, `normative_claim=False`, `fire_resistance_status=not_demonstrated` remain immutable.

## Deliberately excluded / not solved in R0.6.9B

- Biaxial (N + M_x + M_y) capacity and all reinforcement topologies not matching §8.2.21.
- Mechanics for a square 4-sided reduced isotherm, including first-order N–M interaction with strain compatibility; K.27 provides **area only**, not the required distribution of first and second moments.
- Global member ULS, actual restraints/initial imperfections, slenderness and second-order critical strength.
- Fire material law for (>800\,^{\circ}\mathrm{C}) outside the removed concrete layer, or steel above 800 °C.
- Non-square and other heating configurations: require their **own explicitly verified** reduced-area geometric methods and limitation checks.
- Normative interpolation of tabulated material properties; continuity and first-failure time proof.
- Independently qualified Annex L spalling and fire exposure/protection scope.

**Do not promote an area reduction or N_upper > N_Ed to a positive R90 verdict.** R0.6.9A's diagnostic time scan remains unchanged; this stage cannot replace its member ULS with an optimistic section ceiling.

## Acceptance commands

```bash
python -m unittest tests.test_r069b_critical_isotherm -v
python -m unittest tests.test_r069_time_history -v
python -m unittest discover -s tests -v
```

Only merge after both GitHub Actions workflows are green. Do not copy the purchased standards PDF into the public repository.
