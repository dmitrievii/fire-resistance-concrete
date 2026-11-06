"""Normative heat-transfer subpackage (stage R0.6.2)."""
from .normative import (VERSION,SOURCE,FACE_NAMES,CONCRETE_FAMILIES,MODEL_CHOICES,TABLE_K1,TABLE_K2,
    ThermalError,ThermalProfile,RectangularExposure,resolve_profile,property_K1,
    heating_depth_m,temperature_rectangle,critical_temperature_C,
    square_four_face_reduced_section,evaluate_rectangular_column)