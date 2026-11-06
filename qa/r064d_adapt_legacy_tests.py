#!/usr/bin/env python3
"""Adapt two historical positive fixtures to the R0.6.3A hot-boundary policy.

Run ONLY after R0.6.4D is overlaid on a disposable CI checkout.
Original main-branch tests are unchanged; never relax the production safety gate.
"""
from pathlib import Path

def replace_exact(path: str, old: str, new: str):
    p = Path(path)
    content = p.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one historical fixture, found {count}")
    p.write_text(content.replace(old, new, 1), encoding="utf-8")

replace_exact("tests/test_r063_mechanics.py",
    """        c['fire_minutes']=30.
        p30=self.pre(c)
        f30,_,_=p30.response([.001,0.,0.])
        self.assertLess(f30[0],f0[0])
        self.assertGreater(max(p30.concrete_temperature_C),20)""",
    """        c['fire_minutes']=10.
        p10=self.pre(c)
        f10,_,_=p10.response([.001,0.,0.])
        self.assertLess(f10[0],f0[0])
        self.assertGreater(max(p10.concrete_temperature_C),20)
        # R0.6.3A explicitly rejects 30-min unqualified hot boundary.
        c['fire_minutes']=30.
        t30=evaluate_rectangular_column(c,grid=20)
        with self.assertRaisesRegex(SectionMechanicsError,'800'):
            prepare_section(c,t30,grid=20)""")

replace_exact("tests/test_streamlit_ui.py",
    "        update_column(proj,'c1',{'fire_minutes':30.})",
    """        # Positive plot fixture must remain inside the material-table range.
        # The 30-minute hot-boundary case is checked fail-closed separately.
        update_column(proj,'c1',{'fire_minutes':10.})""")

print("R0.6.4D historical regression fixtures adapted without weakening guards")
