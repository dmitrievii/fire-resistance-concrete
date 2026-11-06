"""R0.6.4C: explicitly selected reference strengths for SP 2.02.05-2026 8.2.18.

Separates a literal text-based implementation from the historical R0.6.3
accidental-design reference. This is NOT a complete qualified heated law.
"""
from __future__ import annotations
from dataclasses import replace
import math
import numpy as np

from rc_fire.materials.normative import C_CLASSES, FCK
from .normative import PreparedSection

LITERAL = 'literal_8_2_18_normative_strength'
HISTORIC = 'legacy_accidental_design_diagnostic'


def select_fire_reference_strength(prepared: PreparedSection, *, mode: str):
    """Copy the prepared section without modifying caller data.

    With literal mode, concrete reference is fck instead of fcd. Each already
    resolved temperature coefficient kc(theta) is preserved. fyk and fyd are
    compared as well; for the current 8.2.18 accidental gamma_s=1 they match.
    This operation does NOT repair hot ultimate strains, steel 20..200 or
    initial tangent, and never grants a normative fire ULS status.
    """
    if not isinstance(prepared, PreparedSection):
        raise TypeError('R0.6.3C PreparedSection required')
    if mode not in (LITERAL, HISTORIC):
        raise ValueError('explicit recognized fire strength reference required')
    sd = prepared.strength_data
    cls = sd['concrete_class']
    fck = float(FCK[C_CLASSES.index(cls)])
    fcd = float(sd['f_cd_MPa'])
    fyk = float(sd['f_yd_MPa']) * float(sd['gamma_s'])
    fyd = float(sd['f_yd_MPa'])
    if not all(math.isfinite(x) and x > 0 for x in (fck, fcd, fyk, fyd)):
        raise ValueError('invalid reference strength')
    rc = fck/fcd if mode == LITERAL else 1.
    rs = fyk/fyd if mode == LITERAL else 1.
    out = replace(prepared,
        concrete_fcd_MPa=np.asarray(prepared.concrete_fcd_MPa)*rc,
        bar_displaced_concrete_fcd_MPa=np.asarray(prepared.bar_displaced_concrete_fcd_MPa)*rc,
        bar_fyd_MPa=np.asarray(prepared.bar_fyd_MPa)*rs,
        strength_data={**sd, 'reference_strength_mode':mode,
            'reference_concrete_MPa': fck if mode == LITERAL else fcd,
            'reference_steel_MPa':fyk if mode == LITERAL else fyd,
            'fire_strength_source':'СП 2.02.05-2026 §8.2.18, табл.9-10',
            'normative_fire_uls_qualified':False})
    return out, {'mode': mode, 'ambient_fck_MPa':fck, 'ambient_fcd_MPa':fcd,
       'ambient_fyk_MPa':fyk, 'ambient_fyd_MPa':fyd,
       'concrete_strength_factor':rc, 'steel_strength_factor':rs,
       'effect_on_modulus':'none; beta Ecm unchanged; heated stress-strain remains unqualified',
       'normative_claim':False, 'source':'СП 2.02.05-2026 §8.2.18'}
