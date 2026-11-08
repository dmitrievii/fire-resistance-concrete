# R0.6.9A — independent thermal–mechanical time scan (diagnostic)

**Status: IMPLEMENTED TIME-SAMPLING INFRASTRUCTURE, NOT A QUALIFIED R(t) OR R90.**
This stage must never be merged or advertised as a normative determination of fire-resistance time. The inputs N, Mx and My remain authoritative **fire-design actions**; no repeated combination/provenance gate is introduced.

## Standards and calculation chain

- СП 2.02.05-2026 §8.2.16 requires sequential time-dependent thermal and static checks; §8.2.17 concerns the load level; §8.2.18–8.2.20 supply heated-material and stress–strain routes. Their text does not warrant inventing material coefficients above the last tabulated 800 °C.
- СП 5.03.01-2020: stress/strain and member strength requirements remain the references for the structural check.
- This is a **sampled numerical observer** of the existing R0.6.4C member solver and R0.6.7 explicit uniform-longitudinal model, **not** a newly qualified ULS method.

At each actual time point the code:
1. Copies the column inputs without modifying the saved project or recombining actions.
2. Recomputes the Annex K field for that time; no transfer of previous temperatures.
3. Constructs distinct nodal and Gauss material stations by the *existing explicit user-authorized longitudinal uniformity assumption*.
4. Repeats coupled N–Mx–My + second-order equilibrium and local sampled strain checks.
5. Labels the time point **within sampled strain limits**, **observed sampled exceedance**, or **unresolved**. Nonconvergence, missing thermal information and outside-table material temperatures are **unresolved**.

A sampled *adjacent* within/exceeded transition is recorded as an observation interval only. An unresolved point between observations breaks that bracket. No interpolation, dichotomy, or monotonicity inference is made across missing states.

The structural stability model, the hot-material stress/strain assumptions, support idealisation and finite sample locations are still diagnostic. The module sets `R_t_minutes=null`, `normative_claim=false`, and `fire_resistance_status=not_demonstrated` in **every** result.

## Main known blocker for R90

Concrete strength/modulus coefficients in СП 2.02.05-2026 table 9, and reinforcement coefficients in table 10, end at 800 °C. A typical four-sided 90-minute exposure reaches temperatures above that table range near the heated boundary. The existing full-fibre constitutive branch rejects such stations. This is correct fail-closed behaviour, not evidence that the member failed at that time.

The §8.2.21 critical-isotherm reduced-area alternative can be used **only within its specific restrictions**, including the appropriate simple symmetric section, reinforcement location and load plane. It is not a general automatic substitute for arbitrary biaxial bending. A separate scoped implementation and independent verification are required before using it to qualify R(t).

Other open qualifications: material interpolation and heated ultimate strains, thermal eigenstrain integration, initial imperfections, actual structural restraints, continuous-member ULS, and Annex L spalling assumptions.

## UI

In the R0.6.7 expander, provide an admissible **uniform** thermal/member model, select the time increment and run the R0.6.9A scan on demand. The table shows exact simulated minutes and the status of each point. The audit JSON contains the input signature and unresolved time points; no unsupported resistance time is displayed.

## Acceptance

```bash
python -m unittest tests.test_r069_time_history -v
python -m unittest discover -s tests -v
```

Require full green GitHub Actions prior to merge. Do not merge into main until verified.
