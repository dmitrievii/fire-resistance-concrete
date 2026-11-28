import json
import math
import copy
import unittest
import numpy as np
from rc_fire.member import sp2026_r11a_history_member as m
from rc_fire.member.coupled import EndSupport
from rc_fire.thermal.sp2026_heat import solve_sp2026_2d_heat,select_sp2026_snapshot,reference_sp2026_boundary
from test_sp_r3_member import make_explicit_spec
from test_sp_r10a_history_section import fixture

def spec_for(c,n,amp=.003,load=(.02,.01)):
    s=make_explicit_spec(c);z=np.linspace(0,c["length_m"],n);L=z[-1]
    s["z_m"]=z.tolist();s["distributed_load_kNpm"]=[list(load)]*n;s["nodal_forces"]=[0.]*(4*n)
    d=[]
    for a in (amp,amp/2):
        for x in z:d.extend((a*math.sin(math.pi*x/L),a*math.pi/L*math.cos(math.pi*x/L)))
    s["initial_imperfection"]=d;s["imperfection_source"]="synthetic half-sine"
    s["transverse_action_source"]="explicit synthetic distributed load; not a reconstruction of actual entered moments"
    return s

class TestR11A(unittest.TestCase):
 def test_mixed_linear_euler_and_biaxial_amplification(self):
    from scipy.linalg import eigvalsh
    L=3.;D=np.array([[1000.,120.],[120.,700.]])
    S=np.array([.3,.3]);Q=np.zeros((3,3));Q[0,0]=1e6
    Q[1:,1:]=D/np.outer(S,S)
    Ncr=math.pi**2*np.linalg.eigvalsh(D)[0]/L**2
    v=np.linalg.eigh(D)[1][:,0];amp=.003;rows=[]
    for n in (5,9,17):
        z=np.linspace(0,L,n);imp=[]
        for a in v*amp:
            for x in z:imp.extend([a*math.sin(math.pi*x/L),a*math.pi/L*math.cos(math.pi*x/L)])
        beam=m.Beam(z,.5*Ncr,EndSupport("pinned"),EndSupport("pinned"),np.zeros((n,2)),np.zeros(4*n),imp,S)
        law=lambda i,q:(Q@q,Q,None)
        r,K,_=beam.assemble(beam.zero(),law)
        T=beam.condensed(K)
        lat=[k for k in range(beam.nd) if k not in beam.fixed]
        G=beam.G[np.ix_(lat,lat)]
        computed=eigvalsh(T+beam.N*G,G)[0]
        self.assertLess(abs(computed/Ncr-1),.005)
        solved,report=beam.solve(beam.zero(),law)
        self.assertEqual(report["status"],"EQUILIBRATED_RESEARCH_MEMBER")
        x=solved[0];physical=(x[:beam.nd]+beam.initial)*beam.scale
        mid=np.array([physical[2*(n//2)],physical[2*n+2*(n//2)]])
        ratio=float(mid@v/amp)
        self.assertLess(abs(ratio-2),.005)
        rows.append({"nodes":n,"Euler_exact_kN":Ncr,"Euler_FE_kN":float(computed),"amplification":ratio})
    print("SP_R11A_LINEAR_EVIDENCE",json.dumps(rows))
 def test_actual_history_and_rollback(self):
    c=fixture();s=spec_for(c,3)
    heat=solve_sp2026_2d_heat(c,boundary=reference_sp2026_boundary(moisture_mass_pct=1.5),
        cell_count_x=16,cell_count_y=16,max_step_minutes=1.,sample_times_minutes=[0.,2.,5.,10.])
    fields=[select_sp2026_snapshot(heat,t) for t in (0.,2.,5.,10.)]
    a=m.initial(c,s,fields[0],grid=8);b,r=m.advance(a,c,s,fields[0])
    self.assertEqual(r["status"],"EQUILIBRATED_RESEARCH_MEMBER")
    self.assertEqual(len(b.sections),6);self.assertEqual(a.time_s,0.)
    self.assertTrue(all(v.time_s==1. for v in b.sections))
    n,r=m.advance(b,c,s,fields[1],max_iterations=1)
    self.assertIs(n,b);self.assertNotEqual(r["status"],"EQUILIBRATED_RESEARCH_MEMBER")
    self.assertTrue(all(v.time_s==1. for v in b.sections))
    results=[]
    for nn in (3,5):
        h=m.history(c,spec_for(c,nn),fields,grid=8)
        self.assertEqual(h["rows"][0]["status"],"EQUILIBRATED_RESEARCH_MEMBER")
        for row in h["rows"]:
            if row["status"]=="EQUILIBRATED_RESEARCH_MEMBER":
                self.assertLessEqual(row["max_axial_residual_kN"],1e-6)
                self.assertLessEqual(row["scaled_free_residual_kNm"],1e-6)
        self.assertIsNone(h["actual_t_R_minutes"])
        results.append({"nodes":nn,**h})
    print("SP_R11A_HEATED_EVIDENCE",json.dumps(results,allow_nan=False))
 def test_global_tangent_finite_difference(self):
    c=fixture();s=spec_for(c,3)
    from rc_fire.thermal.sp2026_annex_k_field import build_annex_k_snapshot
    # Actual FVM ambient to keep uniform route contract.
    heat=solve_sp2026_2d_heat(c,boundary=reference_sp2026_boundary(moisture_mass_pct=1.5),
        cell_count_x=8,cell_count_y=8,max_step_minutes=1.,sample_times_minutes=[0.,1.])
    f=select_sp2026_snapshot(heat,0.)
    a=m.initial(c,s,f,grid=8);b,r=m.advance(a,c,s,f)
    self.assertEqual(r["status"],"EQUILIBRATED_RESEARCH_MEMBER")
    beam=m.make_beam(c,s);p,A,C,B,E,fy=m.sec._prepare(a.sections[0],c,f)
    def law(i,q):
        z=m.sec._trial(a.sections[i],p,A,C,B,E,fy,1.,q)
        return z[0],z[1],None
    x=np.asarray(b.x);R,K,_=beam.assemble(x,law)
    v=np.zeros(beam.total);v[beam.free]=np.linspace(.1,.8,len(beam.free))
    eps=1e-9
    fd=(beam.assemble(x+eps*v,law)[0]-beam.assemble(x-eps*v,law)[0])/(2*eps)
    self.assertTrue(np.allclose(fd[beam.free],(K@v)[beam.free],rtol=1e-5,atol=.1))
    wrong=copy.deepcopy(s);wrong["uniform_exposure_confirmed"]=False
    with self.assertRaises(ValueError):m.initial(c,wrong,f)
