# SP-R8B — Annex K direct analytical thermal-mechanical coupling

Draft, stacked on SP-R8. No production route change or normative R(t) claim.

## Source decisions
SP 2.02.05-2026 §8.2.23 explicitly directs simple sections to Annex K. K.11's printed lower-bound wording conflicts with its no-contribution sentence and K.6–10; retain upper cap as an explicit engineering interpretation pending official correction. K.5 does not explicitly define clear/centre distance; keep legacy clear convention and compare centre alternative. Both use exact K.4–K.12 point evaluation; no interpolation of FVM cells and no 500°C reduction. Density interpolation remains flagged. K.6's one-face depth restriction means the analytical route cannot supply a full-section field for that exposure; reject with a clear reason instead of extrapolating or silently falling back.

## Implementation
- Distinct SP2026_ANNEX_K_ANALYTICAL snapshot, profile matching, direct fibre temperature sampling and separate K.5 steel vs K.4 surrounding concrete temperature.
- Reuse existing SP5 design section and SP-R7 coupled nominal member mechanics. FVM and legacy TKP provenance retained; full nonlinear FVM member/first-limit time history not switched.
- Explicit t=0 analytical snapshot supported. Above 800°C concrete user rule and steel domain guard unchanged.
- Cross comparison holds inputs/actions and moisture fixed; compares K clear/centre and FVM steel, concrete, stiffness, Euler loads and second-order moments. Boundary parameters remain unqualified FVM assumptions.
- Five targeted tests include source scalar reference, actual member coupling, provenance mismatch, one-face scope, ambient initial state and real cross-route computation (CI pending).

## Remaining
Prior SP-R8 CI still queued at audit. No independent execution result claimed. Source authority clarification of K.5/K.11, full time-history route and global failure, fire-duration convergence, broader Annex Zh comparison and hot constitutive qualification remain open. No merge without user approval.
