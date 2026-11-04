"""Physical, dimensioned rectangular reinforcement section.

Interactive Plotly and self-contained SVG print views use bar-centre coordinates
in millimetres. Circle radii are geometrically true, not sized by bar count.
"""
from __future__ import annotations

from html import escape
import math


def _geometry(data: dict, variant_index: int):
    g=data['geometry'];v=data['variants'][variant_index]
    b=float(g['b_m'])*1000;h=float(g['h_m'])*1000
    bars=[{'id':str(bar['id']),'x':float(bar['x_m'])*1000,
           'y':float(bar['y_m'])*1000,'diameter':float(bar['diameter_mm'])}
          for bar in v['bars']]
    return b,h,bars,v


def steel_legend(data: dict, index: int):
    _,_,bars,_=_geometry(data,index)
    counts={}
    for bar in bars:
        d=bar['diameter']; counts[d]=counts.get(d,0)+1
    return ' · '.join(f'{count} × Ø{d:g} mm' for d,count in sorted(counts.items()))


def bar_schedule(data: dict, index: int, result: dict|None=None) -> list[dict]:
    b,h,bars,v=_geometry(data,index)
    output=[]
    for bar in bars:
        d=bar['diameter'];r=d/2
        row={'Bar':bar['id'], 'X [mm]':round(bar['x'],2),
             'Y [mm]':round(bar['y'],2),'Ø [mm]':round(d,2),
             'Cover left [mm]':round(bar['x']-r,2),
             'Cover right [mm]':round(b-bar['x']-r,2),
             'Cover bottom [mm]':round(bar['y']-r,2),
             'Cover top [mm]':round(h-bar['y']-r,2)}
        if result:
            if result['engine']=='k18-parametric-experimental':
                rv=result['variants'][v['id']]
                match=next((z for z in rv['bars'] if z['id']==bar['id']),None)
                if match:row['T [°C]']=round(float(match['temperature_C']),1)
            elif result['engine']=='independent-k18-python':
                # Reference report: corners are 597°C; centre-of-face 355°C.
                th=result['thermal']['reported_steel_temperatures_C']
                corner=bar['x'] != b/2 and bar['y'] != h/2
                row['T [°C]']=float(th[0] if corner else th[1])
        output.append(row)
    return output


def dimensioned_figure(data: dict, index: int=0, result:dict|None=None,
                       show_dimensions:bool=True,show_ids:bool=True):
    import plotly.graph_objects as go
    b,h,bars,v=_geometry(data,index)
    fig=go.Figure()
    fig.add_shape(type='rect',x0=0,y0=0,x1=b,y1=h,
                  line={'color':'#334155','width':2.5},fillcolor='#f1f5f9',layer='below')
    # Dashed physical section centrelines.
    for x0,y0,x1,y1 in ((b/2,0,b/2,h),(0,h/2,b,h/2)):
        fig.add_shape(type='line',x0=x0,y0=y0,x1=x1,y1=y1,
                      line={'color':'#94a3b8','width':1,'dash':'dot'},layer='below')
    schedule=bar_schedule(data,index,result)
    by_id={row['Bar']:row for row in schedule}
    for bar in bars:
        r=bar['diameter']/2
        fig.add_shape(type='circle',x0=bar['x']-r,y0=bar['y']-r,
                      x1=bar['x']+r,y1=bar['y']+r,
                      line={'color':'#1e3a5f','width':1.4},
                      fillcolor='#27618d')
        if show_ids and len(bars)<=24:
            fig.add_annotation(x=bar['x'],y=bar['y']+r+11,
                   text=f"<b>{escape(bar['id'])}</b> Ø{bar['diameter']:g}",
                   showarrow=False,font={'size':10,'color':'#0f172a'},
                   bgcolor='rgba(255,255,255,0.72)',borderpad=1)
    custom=[]
    for bar in bars:
        row=by_id[bar['id']]
        s=(f"<b>Bar {escape(bar['id'])} — Ø{bar['diameter']:g} mm</b>"
           f"<br>X = {bar['x']:g} mm; Y = {bar['y']:g} mm"
           f"<br>Clear cover L/R/B/T = {row['Cover left [mm]']:g} / "
           f"{row['Cover right [mm]']:g} / {row['Cover bottom [mm]']:g} / "
           f"{row['Cover top [mm]']:g} mm")
        if 'T [°C]' in row:s+=f"<br>Temperature = {row['T [°C]']:g} °C"
        custom.append(s)
    fig.add_trace(go.Scatter(x=[bar['x'] for bar in bars],
                             y=[bar['y'] for bar in bars],
                             mode='markers',marker={'size':14,'color':'rgba(0,0,0,0.01)'},
                             text=custom,hovertemplate='%{text}<extra></extra>',
                             showlegend=False,name='Rebar'))
    def h_dim(y,positions,overall=False):
        positions=sorted(set(round(x,5) for x in positions))
        if len(positions)<2:return
        fig.add_shape(type='line',x0=positions[0],y0=y,x1=positions[-1],y1=y,
                      line={'color':'#475569','width':1.2})
        for x in positions:
            fig.add_shape(type='line',x0=x-4,y0=y-5,x1=x+4,y1=y+5,
                          line={'color':'#475569','width':1.2})
        for a,c in zip(positions,positions[1:]):
            if c-a>=28:
                fig.add_annotation(x=(a+c)/2,y=y+11,text=f'{c-a:g}',showarrow=False,
                        font={'size':10,'color':'#0f172a'})
    def v_dim(x,positions):
        positions=sorted(set(round(y,5) for y in positions))
        if len(positions)<2:return
        fig.add_shape(type='line',x0=x,y0=positions[0],x1=x,y1=positions[-1],
                      line={'color':'#475569','width':1.2})
        for y in positions:
            fig.add_shape(type='line',x0=x-5,y0=y-4,x1=x+5,y1=y+4,
                          line={'color':'#475569','width':1.2})
        for a,c in zip(positions,positions[1:]):
            if c-a>=28:fig.add_annotation(x=x-14,y=(a+c)/2,text=f'{c-a:g}',
                      showarrow=False,textangle=-90,font={'size':10,'color':'#0f172a'})
    if show_dimensions:
        if len(bars)<=16:
            h_dim(-43,[0,b]+[bar['x'] for bar in bars])
            v_dim(-43,[0,h]+[bar['y'] for bar in bars])
        h_dim(-91,[0,b],True)
        v_dim(-96,[0,h])
        fig.add_annotation(x=b/2,y=-113,text=f'<b>b = {b:g} mm</b>',
                           showarrow=False,font={'size':12})
        fig.add_annotation(x=-119,y=h/2,text=f'<b>h = {h:g} mm</b>',
                           textangle=-90,showarrow=False,font={'size':12})
    fig.update_layout(height=570,margin=dict(l=10,r=10,t=65,b=15),
             title={'text':f"Variant {escape(v['id'])} · {b:g} × {h:g} mm · {steel_legend(data,index)}",
                    'font':{'size':16}},
             xaxis={'title':'x [mm]', 'range':[-max(150,b*.20),b+max(65,b*.10)],
                    'zeroline':False,'gridcolor':'#edf2f7'},
             yaxis={'title':'y [mm]', 'range':[-max(150,h*.20),h+max(65,h*.10)],
                    'scaleanchor':'x','scaleratio':1,'zeroline':False,
                    'gridcolor':'#edf2f7'},
             showlegend=False,dragmode='pan',paper_bgcolor='white',plot_bgcolor='white',
             hoverlabel={'bgcolor':'white','font_size':12})
    return fig


def section_svg(data:dict,index:int=0,show_labels=True) -> str:
    """Offline SVG for the downloadable printable report; no external assets."""
    b,h,bars,v=_geometry(data,index)
    margin=125;vwidth=b+2*margin;vheight=h+2*margin
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-margin} {-margin} {vwidth:g} {vheight:g}" '
         'style="width:100%;max-width:165mm;height:auto;display:block;margin:8px auto">',
         f'<rect x="0" y="0" width="{b:g}" height="{h:g}" fill="#f1f5f9" stroke="#26374b" stroke-width="3"/>',
         f'<line x1="{b/2:g}" x2="{b/2:g}" y1="0" y2="{h:g}" stroke="#94a3b8" stroke-dasharray="6 6"/>',
         f'<line x1="0" x2="{b:g}" y1="{h/2:g}" y2="{h/2:g}" stroke="#94a3b8" stroke-dasharray="6 6"/>']
    for bar in bars:
        xx=bar['x'];yy=h-bar['y'];rad=bar['diameter']/2
        out.append(f'<circle cx="{xx:g}" cy="{yy:g}" r="{rad:g}" fill="#27618d" stroke="#153655" stroke-width="1"/>')
        if show_labels and len(bars)<=16:
            out.append(f'<text x="{xx:g}" y="{yy-rad-8:g}" text-anchor="middle" '
                       f'font-size="13" fill="#17253b">{escape(bar["id"])} Ø{bar["diameter"]:g}</text>')
    out.append(f'<line x1="0" x2="{b:g}" y1="{h+66:g}" y2="{h+66:g}" stroke="#475569" stroke-width="2"/>')
    for xx in [0,b]:out.append(f'<line x1="{xx-5:g}" y1="{h+58:g}" x2="{xx+5:g}" y2="{h+74:g}" stroke="#475569" stroke-width="2"/>')
    out.append(f'<text x="{b/2:g}" y="{h+100:g}" text-anchor="middle" font-size="17">b = {b:g} mm</text>')
    out.append(f'<line x1="-64" x2="-64" y1="0" y2="{h:g}" stroke="#475569" stroke-width="2"/>')
    for yy in [0,h]:out.append(f'<line x1="-72" y1="{yy-5:g}" x2="-56" y2="{yy+5:g}" stroke="#475569" stroke-width="2"/>')
    out.append(f'<text x="-100" y="{h/2:g}" transform="rotate(-90 -100 {h/2:g})" text-anchor="middle" font-size="17">h = {h:g} mm</text>')
    out.append('</svg>')
    return ''.join(out)
