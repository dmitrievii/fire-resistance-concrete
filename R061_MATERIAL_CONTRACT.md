# R0.6.1 — Belarus RC material contracts

## Primary sources

- СП 5.03.01-2020 (user-provided official PDF), table 6.1 (classes, strengths, strains),
  table 6.3 (Ecm by concrete consistency, curing and specific aggregate application),
  §6.2.2.13 (reinforcement elastic modulus).
- СП 2.02.05-2026 (user-provided official PDF), §8.2.18 and tables 9/10
  (temperature resistance/stiffness reduction); §8.2.19 tables 11/12,
  eq. (6) (concrete expansion/shrinkage and steel expansion).

## Executable material contract

- Concrete: `ConcreteMix` + `normal_concrete` + `concrete_at_temperature`.
- Reinforcement: `Reinforcement` + `normal_reinforcement` + `reinforcement_at_temperature`.
- Thermal strain: `concrete_thermal_strain_coefficients` and `steel_thermal_expansion`.
- Project binding: `material_spec` per column, `resolve_materials`, material editor in column page.
- Mandatory provenance: source clauses, interpolation mode and non-qualified numeric engine flag.
- No extrapolation of data from table 9 beyond 20–800 °C, table 10 beyond 800 °C.
- **Missing data**: C30/37 alone does not provide Ecm; consistency, curing,
  aggregate class and fine-grained status are explicit inputs; special aggregate
  needs independently measured/tested Ecm. A printed dash in table 6.3 remains unavailable.
- **High-strength beta**: table 9 does not publish a high-strength concrete modulus
  beta line; returned as `None`, never copied from normal concrete.
- Steel table 10 starts at 200 °C. For 20–200 °C the software exposes a
  **non-normative engineering bridge** by linear interpolation from room temperature
  (coefficient 1) to 200 °C. This must not be used to claim normative R(t).
- Temperature interpolation between discrete table ordinates is explicitly recorded
  as `linear_between_tabulated`. No assertion that normative text prescribes
  a particular interpolation method is made.
- Calculated catalog properties are independent from historic K18 worksheet values.

## Integration boundary

R0.6.1 does **not** promote the experimental R0.5.6 N–Mx–My solver to a
normative engine; even a completely resolved material catalog means property
lookup only. Results and report must continue to state `not_demonstrated` for R90.

The existing historical Mathcad regression remains unchanged. Later mechanical
and thermal integration stages must explicitly consume the catalog's provenance,
use the complete material stress-strain laws and pass independent numerical tests.