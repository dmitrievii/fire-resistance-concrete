# SP-R8E — Thermal eigenstrain, self-equilibrated stress and strain-limit adjudication

Draft stacked on #37. No production dispatch/material law change or regulatory R.

## Actual SP-R8D evidence (run 46074848319)
661 tests, 660 passed, 1 skipped. R8C initial FVM ambient failure resolved by R8D interpolation hull correction. At 5/10 min, FVM 32→64 max point ΔT=23.75/21.94 C; Ncrit relative Δ=0.35/0.59%. Spatial criterion still not met.
At 10 min (600 mm square, 50 kN), mechanical grid 8/16/24 strain ratios K=1.6733/1.5486/1.4121, FVM64=1.3069/1.1179/1.0164. Same fine-root replay and fixed probes agree: hot concrete corner governs; K 657.57 C, mechanical strain 4.942‰; FVM 575.45 C, mechanical strain 3.557‰. Both compared against ambient 3.5‰. R8C histories show sampled exceedance at 15 min and later within states; instantaneous model is memoryless and cannot establish irreversible failure.

## Original normative audit
SP 2.02.05-2026 printed pp.34–36 (§8.2.16 destruction analogous to normal temperatures, SP5; §8.2.18 strength and modulus factors; §8.2.19 Tables11/12 reversible expansion and irreversible shrinkage, steel Eq6; §8.2.20 allows SP5 parabolic-linear diagrams with heating-dependent characteristics; §8.2.22 redistribution for statically indeterminate flexural members and whole-element stress-strain state). Reviewed provisions do not supply explicit hot peak/ultimate strain functions or a unique temperature-coefficient integration/irreversible evolution law. Do not equate signed shrinkage with a validated cooling path.
SP 5.03.01-2020 §6.1.5.4 Eq6.17/18 and Table6.1 use eps_c2, eps_cu2; §8.1.2.1 distinguishes section check eps_cu2 / steel 10‰ from nonlinear analysis eps_cu / eps_ud. Eq6.18 plateau only up to eps_cu2; current continued plateau beyond limit is a numerical diagnostic extension, not source-valid capacity. No deletion of strain checks. SP §8.2.18 characteristic-to-fire strength wording vs SP5 partial-factor choice remains a separate source adjudication task.
TKP EN1992-1-2-2009 §3.2.2.1 Table3.1 contains explicit temperature-dependent peak and descending-branch ultimate strains; e.g. at 600 C 25‰ and 35‰. They are not equivalent to SP5 section-check eps_cu2, and are not imported into SP. Comparative constitutive branch only in a future separately declared analysis.

## Implementation
- Decompose concrete signed integral into reversible expansion and signed shrinkage; independent endpoint-coefficient sensitivity, not a normative choice.
- Linear elastic affine compatibility projection reference: exact stress-free compatible expansion and zero-resultant incompatible self-stress. Compression-positive mechanical strain = compatible compression + positive free expansion.
- Real nonlinear free section (N=Mx=My=0) and fixed loaded actions, with four diagnostic variants: existing signed integral, no eigenstrain, expansion only, endpoint coefficient. No nonlinear superposition. Steel temperature law unchanged except in explicit no-eigenstrain control.
- Actual gross concrete, displaced concrete and steel force/moment reconstruction, stress ranges, governing point and strain ratio, residual, explicit flag if numerical plateau used outside check domain. Compare source beta Ecm and parabola initial slope without conflating them.
- 5/10/30/45 min K and FVM64 histories, mechanical 24, 1 min heat step. Five tests; actual CI evidence pending. No new acceptance criterion or source substitution; no modification to existing production solver.
- Remaining: quantify actual thermal self-stress and root/path sensitivity, qualify material strain law and irreversible thermal creep/damage, further spatial convergence, global physical first-limit criterion, experiment.
