# SP-R8D — Spatial convergence recovery and strain-classification localization

Draft stacked on #36. No change to production dispatch or legal R.

## Actual prior evidence
SP-R8B run 46071236822: 654 tests, 653 pass, 1 skip. At 10 min for 600 mm square, both analytical conventions give all bars 20 C; FVM gives 118.686 C corner and 73.244 C middle bars. First nominal Euler 28227.514 vs 27167.226 kN; both section checks exceeded. This is not physical failure. SP-R8C run still queued at audit.

## Implementation
- Correct convex interpolation floating-point overshoot/undershoot, including exact ambient 20 C. Material domains unchanged; this is a roundoff guard on the local four-node hull, not temperature clipping to an arbitrary material limit.
- Vectorize conservative internal FVM face assembly with identical harmonic conductance, symmetric flux contributions and original nonlinear boundary law. Energy residual limits unchanged; numerical equivalence regression required. Makes finer thermal grid study feasible.
- Independent fixed physical probe lattice, two nested resolutions, actual bar tensile strains and sampled 800 C isotherm crossings on active side. Exclude probe points strictly inside steel; equilibrium displaced-concrete subtraction remains unchanged. Record governing x/y, temperature, thermal strain, mechanical strain and ratio. Existing classification not overwritten; no continuum maximum guarantee.
- Separate local sampling from changes in solved generalized strains by replaying the same fine-grid root across mechanical grids. Record original critical ratio, fibre/boundary/steel ratios, residual, Ncrit and fixed-probe classifications.
- Actual targeted 5/10 min campaign: FVM 16/32/64, dt 1 min; mechanical 8/16/24; probe divisions 20/40; both K and FVM diagnostics. Fixed physical temperature sample locations, worst point and bar differences, energy and critical-force checks; same numerical tolerances 10 C and 3%. No tuning or relaxed acceptance. Early-time only, not full fire duration.
- Three new tests emit measured evidence in CI. No assertion that the convergence campaign must pass; a failing acceptance condition is retained explicitly.

## Remaining
CI pending. Determine actual root/sampling sensitivity and whether a further grid or graded mesh is necessary. Validate the constitutive thermal strain history, including restraint and shrinkage; fixed probes are a finite diagnostic and do not resolve physical failure. If unresolved, continue targeted branch; do not merge without approval.
