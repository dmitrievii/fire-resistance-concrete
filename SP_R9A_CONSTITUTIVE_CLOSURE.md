# SP-R9A — Source-exact constitutive adjudication and strict-domain comparisons

Draft stacked on #38. No production material change or normative R.

## Actual SP-R8E evidence, run 46076249087
666 tests, 665 pass, one skip. 10 min signed integral free/loaded strain ratios K 1.40134/1.41207; FVM 1.00511/1.01637. Without eigenstrain loaded ratios ~0.0021. Zero external N: gross concrete compression K 474.67 kN, FVM 532.46 kN, balanced by steel tension (displaced concrete negligible here). Endpoint interpretation changes loaded FVM to 0.92433, K remains 1.20185. These are model results, not experimental stresses. The later within states cannot prove recovery after irreversible damage.

## Original sources
- SP 2.02.05-2026 §§8.2.16,18–20: ambient-like failure, SP5, hot strength/modulus factors, thermal expansion/shrinkage, permitted parabola. The reviewed provisions contain no explicit hot peak/ultimate strain functions. §8.2.22 redistribution is specifically for statically indeterminate flexural members; it is not itself a general column failure algorithm.
- SP5 §6.1.5.2 Eqs6.13–16 use mean fcm, nonlinear Ecm,n and peak strain; §6.1.5.4 Eqs6.17–18 use design fcd and Table6.1 strains; the plateau ends at eps_cu2. §8.1.2.1 separates nonlinear eps_cu/eps_ud from section check eps_cu2/10‰. No stress extrapolation beyond SP strain domain in the new evaluator.
- §8.2.18 wording refers to normative strengths; SP5 §6.1.2.11 and Table4.6 accidental design fcd are separately reported; do not silently select reference strength. Mean fcm is a distinct nonlinear strength basis, not interchangeable with fcd/fck. The full SP curve uses Ecm,n, not Table6.3 Ecm. Applying SP beta to Ecm,n and kc to fcm is explicit engineering extension.
- TKP EN1992-1-2-2009 Table3.1/Fig3.1 and §3.2.3 Fig3.3/Table3.2a, Belarus NA: independent full constitutive material comparison, no import of hot strain ordinates into SP. TKP linear descending concrete branch allowed; only ordinary concrete fck<=50 admitted here.

## Implemented
Strict SP section parabola, full rational ambient-strain candidate, SP-only constant-k hypothesis and independent TKP envelope. Rational admissibility checks peak/ultimate ordering, k>1, denominator and nonnegative stress over complete declared interval. Constant-k scaling multiplies both strains by kc/beta, preserves ambient dimensionless shape and initial reduced nonlinear tangent; it is a hypothesis, NOT a source-defined hot ultimate strain. No fitting. SP >800 concrete inactive by user policy, not TKP. Out-of-domain SP returns unresolved, not fictitious zero or plateau. Steel comparison preserves own strength/modulus/ductility data. Actual 24x24 Annex K 10-minute equilibrium strain replay measures unsupported concrete quadrature area; alternatives not re-equilibrated, TKP replay uses SP strain history only, not a full TKP solver. Four targeted tests and CI output.

## Remaining
Numerical results pending CI. No normative hot ductility closure is possible from reviewed clauses alone; need source clarification or independent hot stress-strain data/validated model, consistent strength basis, creep/damage history and global member limit. Do not select favorable hypothesis on R alone. Production remains unchanged.
