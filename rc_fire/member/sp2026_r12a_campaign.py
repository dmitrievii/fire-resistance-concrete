"""Targeted SP-R12A resistance history; uses same immutable fire anchor
for each independent isothermal path. Fixed-predecessor endpoint scans
are reported separately. No claimed physical first crossing.
"""
import copy
from rc_fire.member import sp2026_r11d_sequential as d
from rc_fire.member import sp2026_r11c_continuation as c
from rc_fire.member import sp2026_r11a_history_member as m
from rc_fire.member import sp2026_r11b_extended_member as b
from rc_fire.member import sp2026_r11e_reconciliation as e
from rc_fire.member import sp2026_r12a_resistance as r
from rc_fire.mechanics import sp2026_r10c_quadrature as quad
from rc_fire.mechanics.sp2026_nominal_member import prepare_sp2026_design_section
from rc_fire.thermal.sp2026_heat import solve_sp2026_2d_heat,select_sp2026_snapshot

def campaign(column,boundary):
    col=copy.deepcopy(column);col["fire_minutes"]=90.
    ints=[float(i) for i in range(91)]
    ts=sorted(set(ints)|{75.+i*.25 for i in range(61)})
    heat=solve_sp2026_2d_heat(col,boundary=boundary,cell_count_x=16,cell_count_y=16,
                             max_step_minutes=1.,sample_times_minutes=ts)
    fields={t:select_sp2026_snapshot(heat,t) for t in ts}
    p=prepare_sp2026_design_section(col,fields[0.],grid=8)
    mesh=quad.build(p,[fields[t] for t in (2.,5.,10.,30.,60.,90.)],base_grid=8,max_level=1,delta_C=100.)
    cc,spec=b.fixture_spec(col,length=12.,N=1500.,nodes=5,support="pinned")
    start=m.initial(cc,spec,fields[0.],grid=8,quadrature=mesh)
    states={}
    def advance(s,t):
        n,v=m.advance(s,cc,spec,fields[t],max_iterations=30)
        if v["status"]==c.OK:states[t]=(n,v)
        return n,v
    last,h=c.adaptive(start,[0.,2.,5.,10.,20.,30.,45.,60.,75.,90.],ints,advance,min_step=1.,max_attempts=65)
    fine={"stop":h["stop"],"rows":[],"status":"NO_ACCEPTED_ANCHOR"}
    if h["accepted"]:
        last,fine=d.refine_interval(last,h["stop"],ts,advance)
    history=[]
    # Earlier points are sparse diagnostic probes, not complete capacity history.
    for t,(s,v) in sorted(states.items()):
        row={"t":t,"status":"ACCEPTED_FIRE_EQUILIBRIUM","U_sample":None,
             "normative_U":None}
        if t in (60.,75.) or t==last.thermal_minutes:
            w=1000*v["total_w_x_m"][len(v["total_w_x_m"])//2]
            path=d.trace_member(s,cc,spec,fields[t],steps=12,ds=.03)
            row["sequential"]=r.sequential(path,w,N=1500.,expected_steps=12)
            row["U_sample"]=row["sequential"]["U_sample"]
        history.append(row)
    # Scan at two future temperatures from a common predecessor, on the
    # same displacement window. This changes temperature AND increment
    # duration; it is a one-increment sensitivity, not fire-path continuation.
    endpoint=[];pair=None;stop=fine["stop"]
    if stop and states:
        end=stop["unresolved_minute"];prior=[t for t in sorted(states) if t<last.thermal_minutes]
        if prior and end>last.thermal_minutes:
            base=states[prior[-1]][0]
            offsets=[-4.+i*2. for i in range(19)]
            for t in (last.thermal_minutes,end):
                try:
                    env=e.endpoint_envelope(base,cc,spec,fields[t],offsets_mm=offsets)
                    ev=r.endpoint(env,N=1500.,expected_count=len(offsets))
                    endpoint.append({"t":t,"anchor_minute":base.thermal_minutes,**ev,"scan_stop":env["stop"]})
                except c.ERRORS as exc:endpoint.append({"t":t,"status":"UNRESOLVED_ENDPOINT","reason":str(exc)})
            if all("family" in v for v in endpoint):
                pair=r.sampled_threshold_pair(endpoint[0],endpoint[1],t0=endpoint[0]["t"],t1=endpoint[1]["t"],same_anchor_and_scan=True)
    return {"history":history,"endpoint_sensitivity":endpoint,"sampled_threshold_pair":pair,
        "computational_stop":stop,"thermal_grid":16,"quadrature":mesh.evidence(),
        "physical_failure_bracket_min":None,"actual_t_R_minutes":None,"normative_claim":False}
