"""R0.6.4 separate *diagnostic* member-stability calculations."""
from .stability import (MemberInputError, NominalStiffnessInput, nominal_stiffness,
    effective_length, imperfection_eccentricity, slenderness_screen, amplify_moment,
    second_order_pin_pin, evaluate_member_diagnostic, section_checks_at_stations)
__all__ = ['MemberInputError','NominalStiffnessInput','nominal_stiffness',
           'effective_length','imperfection_eccentricity','slenderness_screen','amplify_moment',
           'second_order_pin_pin','evaluate_member_diagnostic','section_checks_at_stations']

# R0.6.4B — optional coupled beam-column diagnostic (no R90 certification)
from .coupled import (
    CoupledMemberError, EndSupport, LinearSectionLaw, FiberSectionLaw,
    integrated_free_strains_diagnostic, linear_laws_at_gauss,
    fibre_laws_at_gauss, heated_laws_from_explicit_thermal_stations,
    solve_coupled_beam,
)
__all__ += ['CoupledMemberError','EndSupport','LinearSectionLaw','FiberSectionLaw',
            'integrated_free_strains_diagnostic','linear_laws_at_gauss',
            'fibre_laws_at_gauss','heated_laws_from_explicit_thermal_stations',
            'solve_coupled_beam']

# R0.6.4C: sampled ULS evidence; never a certified R90 result.
from .uls import audit_heated_member_uls
__all__ += ['audit_heated_member_uls']
from .full_uls import run_heated_member_uls_evidence
__all__ += ['run_heated_member_uls_evidence']
from .limit_scan import scan_diagnostic_load_factor
__all__ += ['scan_diagnostic_load_factor']
