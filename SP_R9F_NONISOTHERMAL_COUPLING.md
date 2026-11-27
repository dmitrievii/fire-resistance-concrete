# SP-R9F — Non-isothermal damage–plasticity–creep coupling

Draft stacked on #43. R9E CI run 46082733393: 689 tests, 688 pass, 1 skip. All 12 isothermal synthetic cases reproduce 5 N/mm postpeak external work; unloading and crushing retained. No experimental calibration.

## Implementation
Independent plastic strain and scalar damage retained through temperature changes, not rederived from new p_peak/soft. SP Table9 maximum-temperature strength/modulus (cooling hypothesis); R9A peak scaling kc/beta; R9E effective yield and explicit softening work, temperature-specific p_peak and soft increment. Mechanical return at end T. Damage evolves only with new postpeak plastic increment. Full crushing retained. R9D first-heating LITS quadrature, affine in endpoint stress; optional declared synthetic Maxwell dashpot with backward-Euler increment dt*sigma/eta (not qualified basic creep). No implicit TKP addition. Scope 20–550 C; rejected increments do not mutate state.

Scalar root m + A sigma(m)=u+eth-old_tr-old_cr-B. A nonnegative from LITS and dashpot, B from old stress history. Sufficient monotonicity 1-A fc/soft > 0; reject otherwise, no arbitrary softening branch. Consistent local tangent C/(1+A C). R9E isothermal endpoint parity with creep disabled.

## Energy limitations
Discrete split-path ledger: modulus transfer, eigenstrain shift, external strain shift, LITS shift, dashpot shift, plastic/damage correction at fixed final mechanical strain. Independently integrate correction dissipation using Gaussian quadrature; verify potential-energy balance and nonnegative split dissipation. This is not a continuous actual-path mechanical work proof, not a heat/entropy or full thermodynamic qualification. Record endpoint trapezoid external work and affine LITS / endpoint dashpot work separately; investigate split-path discrepancy under refinement. No energy generation claim beyond discrete split path. Thermal model not coupled to dissipative heat.

## Campaign
9 synthetic path runs, K=0/no dashpot, K=2.35/no dashpot, K=2.35/eta=1e8 MPa s; 4/16/64 subdivisions of identical strain-temperature paths (restraint, mechanical loading at 400 C, cooling/unloading, reheating). Six tests, no fitted parameters. Actual CI pending. No new experimental data or production switch. Upper temperature 550 C is a material-domain blocker for realistic fire sections, not a global collapse criterion.

## Next
Review refinement and energy evidence; independently qualify transient creep continuation above 550 C, actual hot instantaneous and unloading/softening parameters and viscosity/creep law, strength basis, thermal transfer, dissipation/entropy; only then history-dependent section integration. No physical t_R or regulatory R.
