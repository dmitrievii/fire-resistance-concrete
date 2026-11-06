"""R0.6.3 coupled N-Mx-My section mechanics (non-certifying facade)."""
from .normative import (VERSION, SectionMechanicsError, alpha_cc, design_strengths,
    concrete_parabolic_linear, steel_bilinear, PreparedSection, prepare_section,
    solve_load, evaluate_column_mechanics)
__all__=['VERSION','SectionMechanicsError','alpha_cc','design_strengths',
         'concrete_parabolic_linear','steel_bilinear','PreparedSection',
         'prepare_section','solve_load','evaluate_column_mechanics']

from .capacity import approximate_biaxial_capacity