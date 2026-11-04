"""Engineering reinforcement layout for rectangular sections.

Inputs are dimensions in **mm**; the calculation engine always receives explicit
bar centres in **m**. All coordinates are measured from the left/bottom faces.
A bar-centre edge offset is NOT the concrete clear cover (offset - diameter/2).

The perimeter pattern contains nx positions along each horizontal face and ny
positions along each vertical face, with corner bars counted exactly once.
"""
from __future__ import annotations

from math import hypot, isfinite, pi

from calculation_engine import ModelError


def _finite(name: str, value: object) -> float:
    try:
        val = float(value)
    except (ValueError, TypeError) as exc:
        raise ModelError(f'{name}: enter a number') from exc
    if not isfinite(val):
        raise ModelError(f'{name}: must be finite')
    return val


def _int_count(name: str, value: object) -> int:
    val = _finite(name, value)
    if val != int(val) or not 2 <= val <= 33:
        raise ModelError(f'{name}: must be an integer from 2 to 33')
    return int(val)


def _spec_geometry(b_mm: float, h_mm: float, spec: dict) -> dict:
    """Resolve the two positioning bases into four centre-edge offsets.

    spacing: symmetric -> edge distances derived on both sides;
             asymmetric -> far-side edge distance derived, near-side entered.
    edges: all four offsets entered, spacing derived.
    """
    nx = _int_count('nx', spec['nx'])
    ny = _int_count('ny', spec['ny'])
    if 2*nx + 2*ny - 4 > 64:
        raise ModelError('The current solver supports at most 64 bars per variant')
    phi = _finite('Bar diameter', spec['diameter_mm'])
    if not 6 <= phi <= 50:
        raise ModelError('Bar diameter must be 6–50 mm')
    b_mm = _finite('Section width b', b_mm)
    h_mm = _finite('Section height h', h_mm)
    if b_mm <= 0 or h_mm <= 0:
        raise ModelError('Section dimensions must be positive')

    symmetric = bool(spec.get('symmetric', True))
    basis = spec.get('basis', 'edges')
    if basis not in ('edges', 'spacing'):
        raise ModelError('Positioning basis must be edges or spacing')
    if basis == 'edges':
        left = _finite('Left edge-to-centre distance', spec['left_mm'])
        bottom = _finite('Bottom edge-to-centre distance', spec['bottom_mm'])
        right = left if symmetric else _finite('Right edge-to-centre distance', spec['right_mm'])
        top = bottom if symmetric else _finite('Top edge-to-centre distance', spec['top_mm'])
        sx = (b_mm - left - right) / (nx-1)
        sy = (h_mm - bottom - top) / (ny-1)
    else:
        sx = _finite('Centre-to-centre spacing sx', spec['spacing_x_mm'])
        sy = _finite('Centre-to-centre spacing sy', spec['spacing_y_mm'])
        if symmetric:
            left = right = (b_mm-(nx-1)*sx)/2
            bottom = top = (h_mm-(ny-1)*sy)/2
        else:
            left = _finite('Left edge-to-centre distance', spec['left_mm'])
            bottom = _finite('Bottom edge-to-centre distance', spec['bottom_mm'])
            right = b_mm-left-(nx-1)*sx
            top = h_mm-bottom-(ny-1)*sy

    # Reject impossible layouts rather than silently clipping bars or moving them
    # outside the concrete, a defect visible in the earlier 400x600 screenshot.
    for title, val in (('Left',left),('Right',right),('Bottom',bottom),('Top',top)):
        if val <= phi/2 + 0.1:
            raise ModelError(f'{title} edge-to-bar-centre distance must exceed Ø/2 + 0.1 mm')
    if sx < phi-1e-9 or sy < phi-1e-9:
        raise ModelError('Centre-to-centre spacing cannot be smaller than bar diameter')
    return {'mode':'perimeter','basis':basis,'symmetric':symmetric,'nx':nx,'ny':ny,
            'diameter_mm':phi,'left_mm':left,'right_mm':right,
            'bottom_mm':bottom,'top_mm':top,'spacing_x_mm':sx,
            'spacing_y_mm':sy,'bar_count':2*nx+2*ny-4,
            'area_mm2':(2*nx+2*ny-4)*pi*phi**2/4,
            'clear_cover_left_mm':left-phi/2,
            'clear_cover_right_mm':right-phi/2,
            'clear_cover_bottom_mm':bottom-phi/2,
            'clear_cover_top_mm':top-phi/2}


def generate_perimeter(b_mm: float, h_mm: float, spec: dict) -> tuple[list[dict], dict]:
    """Generate bottom, intermediate side, then top bars; no duplicated corners."""
    p = _spec_geometry(b_mm,h_mm,spec)
    xs = [p['left_mm']+i*p['spacing_x_mm'] for i in range(p['nx'])]
    ys = [p['bottom_mm']+j*p['spacing_y_mm'] for j in range(p['ny'])]
    centres = ([(x,ys[0]) for x in xs] +
               [(xx,y) for y in ys[1:-1] for xx in (xs[0],xs[-1])] +
               [(x,ys[-1]) for x in xs])
    bars = [{'id':str(i+1),'x_m':round(x/1000,12),
             'y_m':round(y/1000,12),'diameter_mm':p['diameter_mm']}
            for i,(x,y) in enumerate(centres)]
    assert len(bars) == p['bar_count']
    return bars, p


def infer_perimeter(b_mm:float,h_mm:float,bars:list[dict], tolerance:float=1e-5) -> dict|None:
    """Identify only true regular perimeter patterns, never guess custom ones."""
    if not 4 <= len(bars) <= 64:
        return None
    try:
        diameters=[_finite('diameter',z['diameter_mm']) for z in bars]
        if max(diameters)-min(diameters)>tolerance:
            return None
        xs=sorted({round(_finite('x',z['x_m'])*1000,6) for z in bars})
        ys=sorted({round(_finite('y',z['y_m'])*1000,6) for z in bars})
        if len(xs)<2 or len(ys)<2 or 2*len(xs)+2*len(ys)-4 != len(bars):
            return None
        sx=(xs[-1]-xs[0])/(len(xs)-1)
        sy=(ys[-1]-ys[0])/(len(ys)-1)
        if any(abs(xs[i]-(xs[0]+i*sx))>tolerance for i in range(len(xs))):
            return None
        if any(abs(ys[i]-(ys[0]+i*sy))>tolerance for i in range(len(ys))):
            return None
        expected={(round(x,6),round(ys[0],6)) for x in xs}
        expected|={(round(x,6),round(ys[-1],6)) for x in xs}
        expected|={(round(xs[0],6),round(y,6)) for y in ys}
        expected|={(round(xs[-1],6),round(y,6)) for y in ys}
        actual={(round(z['x_m']*1000,6),round(z['y_m']*1000,6)) for z in bars}
        if expected!=actual:return None
        left=xs[0];right=float(b_mm)-xs[-1]
        bottom=ys[0];top=float(h_mm)-ys[-1]
        spec={'mode':'perimeter','basis':'edges',
              'symmetric':abs(left-right)<=tolerance and abs(bottom-top)<=tolerance,
              'nx':len(xs),'ny':len(ys),'diameter_mm':diameters[0],
              'left_mm':left,'right_mm':right,'bottom_mm':bottom,'top_mm':top,
              'spacing_x_mm':sx,'spacing_y_mm':sy}
        _spec_geometry(b_mm,h_mm,spec)
        return spec
    except (ValueError,TypeError,KeyError,ModelError):
        return None


def active_definition(data:dict,index:int) -> dict:
    """Return saved UI definition, infer it for legacy JSON, or use custom."""
    v=data['variants'][index]
    saved=v.get('reinforcement')
    if isinstance(saved,dict) and saved.get('mode')=='custom':
        return {'mode':'custom'}
    if isinstance(saved,dict) and saved.get('mode')=='perimeter':
        return dict(saved)
    return infer_perimeter(data['geometry']['b_m']*1000,
                           data['geometry']['h_m']*1000,v['bars']) or {'mode':'custom'}


def definition_rows(data:dict,index:int) -> list[tuple[str,str]]:
    """Engineering schedule for both print outputs. Values reflect actual bars."""
    b=float(data['geometry']['b_m'])*1000
    h=float(data['geometry']['h_m'])*1000
    bars=data['variants'][index]['bars']
    spec=active_definition(data,index)
    # Use the geometrically inferred pattern rather than stale, unverified metadata.
    inferred=infer_perimeter(b,h,bars)
    if inferred and spec['mode']=='perimeter':
        p=_spec_geometry(b,h,inferred)
        return [('Layout','Rectangular perimeter'),
                ('Bars along x / y',f"{p['nx']} / {p['ny']}"),
                ('Nominal diameter',f"Ø{p['diameter_mm']:g} mm"),
                ('Centre distances, left / right',f"{p['left_mm']:g} / {p['right_mm']:g} mm"),
                ('Centre distances, bottom / top',f"{p['bottom_mm']:g} / {p['top_mm']:g} mm"),
                ('Centre spacing sx / sy',f"{p['spacing_x_mm']:g} / {p['spacing_y_mm']:g} mm"),
                ('Clear cover L / R / B / T',
                 f"{p['clear_cover_left_mm']:g} / {p['clear_cover_right_mm']:g} / "
                 f"{p['clear_cover_bottom_mm']:g} / {p['clear_cover_top_mm']:g} mm"),
                ('Total bars',str(p['bar_count'])),
                ('Total steel area',f"{p['area_mm2']:.2f} mm²")]
    return [('Layout','Custom bar coordinates'),
            ('Number of bars',str(len(bars))),
            ('Steel diameters',', '.join(f"Ø{d:g}" for d in sorted({float(z['diameter_mm']) for z in bars}))),
            ('Total steel area',f"{sum(pi*(float(z['diameter_mm']))**2/4 for z in bars):.2f} mm²")]
