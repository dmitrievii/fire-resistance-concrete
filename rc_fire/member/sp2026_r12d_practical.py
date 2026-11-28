"""SP-R12D engineering-resolution policy. Research-only, fail closed.

Whole-minute observation targets; default five-minute coarse steps,
one-minute recovery/near-limit steps. This does not loosen equilibrium
tolerances, prove absence of failure between observations, or authorize
normative U/R. Thermal integration has its own independent time step.
"""
import math
from rc_fire.member import sp2026_r11c_continuation as c

VERSION="SP-R12D-practical-v1"
GATES={
 "SP_8_2_16_GLOBAL_FAILURE":"OPEN_PHYSICAL_AND_FIRST_THRESHOLD",
 "SP_8_2_17_FIRE_ACTIONS":"USER_SUPPLIED_PRECOMBINED_ACTIONS",
 "SP_8_2_18_STRENGTH":"OPEN_DEFAULT_ACCIDENTAL_VS_LITERAL_CHARACTERISTIC",
 "SP_8_2_19_THERMAL_STRAIN":"OPEN_IRREVERSIBLE_PATH_VALIDATION",
 "SP_8_2_20_SP5_DIAGRAMS":"OPEN_HOT_ULTIMATE_STRAIN_AND_HISTORY_LAW",
 "SP_8_2_21_ISOTHERM":"OPTIONAL_NOT_SELECTED",
 "SP_8_2_22_REDISTRIBUTION":"SCOPE_STAT_INDETERMINATE_FLEXURAL_MEMBERS",
 "SP_8_2_23_THERMAL":"OPEN_FVM_BOUNDARY_SPATIAL_TIME_AND_MASS_TRANSFER",
 "SP5_8_1_2_SECTION":"OPEN_HOT_ULTIMATE_STRAINS_AND_MEMBER_FAILURE",
 "SP5_8_1_6_STIFFNESS":"OPEN_NONUNIFORM_HOT_STIFFNESS_ADJUDICATION",
 "STEEL_ABOVE_800":"OPEN_UNSUPPORTED",
 "CONCRETE_ABOVE_800":"USER_ZERO_POLICY_NOT_SOURCE_EXTRAPOLATION",
 "EXPERIMENTS":"OPEN_INDEPENDENT_MEMBER_VALIDATION",
 "SECTION_NUMERICS":"OPEN_R10E_F"}
def minute(x):
    if type(x) not in (int,float) or not math.isfinite(x) or x<0 or int(x)!=x:
        raise ValueError("nonnegative whole-minute target required")
    return int(x)

def schedule(end,*,near_start=None,coarse=5):
    end=minute(end);coarse=minute(coarse)
    if end<1 or coarse<1:raise ValueError("positive duration and step required")
    near=end if near_start is None else minute(near_start)
    if near>end:raise ValueError("near-start after requested end")
    return sorted(set(range(0,near,coarse))|set(range(near,end+1))|{0,end})

def run(initial,advance,*,end,near_start=None,coarse=5,max_attempts=200):
    """Practical fire replay with ordered one-minute recovery after a stop.
    A successful coarse increment is not proof of every intervening state.
    Only real accepted states commit; no subminute attempts.
    """
    targets=schedule(end,near_start=near_start,coarse=coarse)
    state=initial;rows=[];attempts=[];stop=None;fine=False
    def trial(t):
        nonlocal state,stop
        lo=state.thermal_minutes
        if len(attempts)>=max_attempts:
            stop={"last_accepted_minute":lo if rows else None,"unresolved_minute":t,
                  "status":"UNRESOLVED_ATTEMPT_BUDGET"};return False
        try:new,r=advance(state,float(t))
        except c.ERRORS as exc:new=state;r={"status":"UNRESOLVED_MEMBER_INPUT_OR_DOMAIN","reason":str(exc)}
        attempts.append({"from_minute":lo,"to_minute":t,"status":r["status"]})
        if r["status"]==c.OK:
            if new is state or new.thermal_minutes!=t:raise ArithmeticError("invalid accepted state")
            state=new;rows.append({**r,"time_minutes":t});return True
        if new is not state:raise ArithmeticError("rejected trial changed committed state")
        stop={**r,"last_accepted_minute":lo if rows else None,"unresolved_minute":t}
        return False
    if trial(0):
        while state.thermal_minutes<end:
            lo=minute(state.thermal_minutes)
            t=lo+1 if fine else next(k for k in targets if k>lo)
            if trial(t):continue
            if t-lo<=1 or stop["status"]=="UNRESOLVED_ATTEMPT_BUDGET":break
            # Revisit from last accepted state in chronological integer
            # steps, not bisection into seconds. Stay fine thereafter.
            fine=True;stop=None
    interval=None
    if stop and rows:interval=[rows[-1]["time_minutes"],stop["unresolved_minute"]]
    return state,{"status":"UNRESOLVED_HISTORY_STOP" if stop else "DIAGNOSTIC_COMPLETE",
        "accepted":rows,"attempts":attempts,"stop":stop,"computational_stop_interval_min":interval,
        "last_accepted_minute":rows[-1]["time_minutes"] if rows else None,
        "observation_resolution_min":1,"no_subminute_observations":True,
        "physical_failure_bracket_min":None,"actual_U_t":None,"actual_t_R_minutes":None,
        "normative_claim":False}

def member_history(column,spec,fields,*,end,near_start=None,grid=8,quadrature=None,
                   strength_basis="SP_CHARACTERISTIC_FCK"):
    """Opt-in literal-strength research route; no automatic production switch.
    Caller supplies actual thermal snapshots at every integer minute.
    """
    from rc_fire.member import sp2026_r11a_history_member as m
    end=minute(end)
    if set(fields)!=set(range(end+1)):
        raise ValueError("actual complete integer-minute thermal snapshot inventory required")
    s=m.initial(column,spec,fields[0],grid=grid,quadrature=quadrature,strength_basis=strength_basis)
    def advance(state,t):return m.advance(state,column,spec,fields[int(t)])
    last,result=run(s,advance,end=end,near_start=near_start)
    result["strength_basis"]=strength_basis
    result["admission_gates"]=dict(GATES)
    return last,result

def review_archived(evidence):
    """Evidence-only assessment: no second-level numerical rerun.
    An observed threshold pair or unresolved bracket cannot yield t_R.
    """
    stop=evidence.get("computational_stop_interval_min")
    width=None
    if stop is not None:
        if len(stop)!=2 or not all(type(x) in (int,float) and math.isfinite(x) for x in stop) or not 0<=stop[0]<stop[1]:
            raise ValueError("invalid computational stop interval")
        width=stop[1]-stop[0]
    return {"source_run":evidence.get("source_run"),"computational_stop_interval_min":stop,
        "stop_width_min":width,"engineering_time_resolution_met":width is not None and width<=1.,
        "last_accepted_whole_minute_diagnostic":math.floor(stop[0]) if stop else None,
        "further_time_localization_needed":width is not None and width>1.,
        "observed_sampled_crossing":evidence.get("observed_sampled_crossing"),
        "physical_failure_bracket_min":None,"actual_t_R_minutes":None,"normative_U":None,
        "normative_claim":False,"admission_gates":dict(GATES)}
