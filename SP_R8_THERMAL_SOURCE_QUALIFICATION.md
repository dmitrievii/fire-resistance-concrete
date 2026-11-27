# SP-R.8 — Thermal source audit and targeted qualification

Stacked on SP-R.7 (ddf2e8f). Draft only; no merge or regulatory claim.

## Original-source audit (SP 2.02.05-2026)
- §8.2.23 (PDF p.40) prescribes the simplified Annex K method for simple symmetric planar, rectangular and circular sections; the general nonlinear heat-transfer calculation is separately described. SP-R2 FVM is a comparison branch, not the sole normative thermal path. FVM is not literally a finite-difference or finite-element formulation.
- Annex K, printed pp.145–146, Table K.1, K.1–K.12: existing siliceous/calcareous A/B/D/E, Wc and a_red inventory matches the original. The K.5 bar distance convention and the contradictory K.11 phrase “не менее 1” versus its zero-contribution rule and K.6–10 still require source adjudication. Existing upper cap is exposed explicitly; no silent normative claim. The analytical route is a temperature calculation, not a tabulated R rating.
- Annex Zh.3, Zh.5–8 (printed pp.120–122): independent selected concrete-temperature points, square four-sided 200/400 mm sections, five geometry/time combinations. Annex Zh.4 and Zh.6 have apparent anomalies (asymmetric entries and a symmetric nonmonotonic spike); preserve provenance and exclude disputed anchors rather than invent corrections. No full licensed matrices or source PDFs are published.
- The table captions do not establish matched aggregate, density, moisture or external exchange coefficients. FVM h=25 and eps=.7 remain TKP comparison inputs; unheated adiabatic faces, no steel thermal feedback and effective moisture heat capacity remain modeling assumptions. Corner reconstruction is not an independently solved corner node.
- K.1 effective heat capacity does not establish coupled moisture transport.

## Executable evidence
rc_fire/verification/sp2026_r8_thermal.py: pointwise K/FVM/Annex Zh residuals separated into interior, surface and corner classes. Five geometry/time cases, 29 selected anchors. Separate four-solve heat mesh/time and fifth mechanical quadrature comparison at constant thermal snapshot. Compare actual bars, centre, surface maximum, principal Euler loads, full bending matrix and magnified moments; unresolved states cannot pass. All tolerances are numerical research thresholds, not SP prescriptions.

tests/test_sp_r8_thermal_qualification.py: independent K scalar formula, explicit K.5 interpretation, real 200/400 mm heat computations, real SP-R7 coupled section grid/thermal convergence. Evidence emitted to CI log, not fabricated in this report. Test execution pending until CI confirms.

## Remaining work
No production route switch: existing SP-R7 mechanics accepts only SP-R2 FVM fields; a separate, provenance-safe Annex K-to-mechanics adapter is needed. Verify K.5/K.11 against normative source and original K18 case, including any official corrigenda; expand Annex Zh point coverage and independent heat mesh/time runs to fire-relevant times. Resolve boundary physics and validate moisture/spalling where applicable. No U(t), t_R or R certification.
