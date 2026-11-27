# SP-R8C — Unified analytical/FVM fire-duration history and sampled event qualification

Draft stacked on #35. No production dispatch or normative R(t) change.

## Prior evidence (actual SP-R8 CI, run 46070442972)
649 tests, 648 passed, 1 skipped. Annex Zh interior RMSE (FVM / K, C):
Zh.3 20.51 / 77.15; Zh.5 74.25 / 19.79; Zh.6 44.09 / 38.85;
Zh.7 32.82 / 45.20; Zh.8 28.52 / 44.91.
Coarse 5-minute coupled test: 4→6 and 6→8 thermal mesh changes 169.31
and 140.05 C, 5.70% and 5.44% Ncrit. 2→1 min timestep 2.59 C and
0.10% Ncrit. 8→12 mechanical grid changed classification despite
0.12% Ncrit. Not converged. These are diagnostics, not calibrated validation.

## Implemented
- FVM stores the actual initial field at t=0 when requested. Mechanical input checks that this field is 20 C.
- Unified explicit route history, K clear/centre or FVM, starts at zero and evaluates every exact observation through the full declared fire duration; no thermal interpolation in time.
- Sampled event states distinguish initial limit, known within→limit interval, unknown preceding limit, no observed limit, unresolved history. No physical first-loss certification. Ambiguous nominal amplification absence is UNKNOWN unless a finite positive Euler threshold is demonstrably reached.
- Independent FVM thermal space, integration timestep, mechanical quadrature; same fine output schedule in all solves; reuse fine thermal field for mechanical refinement. K quadrature, K.5 sensitivity, K/FVM comparison and nested output observation comparisons for all three final routes. Common 25 concrete points and individual bar temperatures. Compare Ncrit, D and M2 where defined, same resolved classifications and sampled event intervals. No claim that sample convergence proves continuous history or true U(t).
- Real 90-minute test at 0,15,...,90 min, thermal 8→16, dt 3→1.5 min, mechanical 8→12; 0,30,60,90 min subset; provisional 15-minute event criterion for this smoke campaign. CI emits actual numerical evidence. No fitting.
- Limits: K.6 one-face full-section gap, K.5/11 official clarification, external FVM assumptions, hot materials, SP5 nominal matrix extension, physical failure/experimental validation. FVM solver failure yields unresolved schedule, no replacement. Analytical fields can be unavailable at individual times. Existing positive-temperature legacy routines retain separate scope.

CI pending at publication. No merge or certification.
