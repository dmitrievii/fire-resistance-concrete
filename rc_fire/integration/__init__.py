"""Optional R0.6.4D integration: fire-resistance verdict always unqualified."""
from .r064d import (VERSION, pending_member_evidence, evaluate_explicit_member_bundle,
                    attach_member_evidence, sample_station_bundle)
__all__ = ['VERSION','pending_member_evidence','evaluate_explicit_member_bundle',
           'attach_member_evidence','sample_station_bundle']
