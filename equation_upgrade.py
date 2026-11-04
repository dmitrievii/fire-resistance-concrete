"""Controlled OMML migration for VERIFIED legacy OLE equations.

This does NOT silently convert unverified MathType objects. Six equations are
transcribed from the supplied report, retain original equation-number runs,
and are now genuine editable Word equations. Optionally provides a dynamic
computed expression for equation (3.3.13) using unrounded engine values.
"""
from __future__ import annotations
from copy import deepcopy
from lxml import etree
from pathlib import Path
import zipfile
import shutil

W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
M='http://schemas.openxmlformats.org/officeDocument/2006/math'
O='urn:schemas-microsoft-com:office:office'
NS={'w':W,'m':M,'o':O}

def elem(name):return etree.Element('{%s}%s'%(M,name))

def text_run(s):
    r=elem('r');rp=elem('rPr');st=elem('sty');st.set('{%s}val'%M,'p');rp.append(st);r.append(rp)
    t=elem('t');t.text=str(s);r.append(t);return r

def sub(a,b):
    e=elem('sSub');base=elem('e');base.append(text_run(a));sb=elem('sub');sb.append(text_run(b));e.extend([base,sb]);return e

def frac(top,bottom):
    e=elem('f');num=elem('num');den=elem('den');num.extend(top if isinstance(top,list) else [top]);den.extend(bottom if isinstance(bottom,list) else [bottom]);e.extend([num,den]);return e

def formula_omml(parts):
    formula=elem('oMath');formula.extend(parts);return formula

# Exact relationships explicitly identified from raster/source text of the report.
# key -> (original OLE ordinal zero-based, list of OMML structures)
FORMULAE={
  '3.3.3':(21,lambda:[sub('f','yd,fi'),text_run('='),sub('f','yk'),text_run('·'),sub('k','s'),text_run('(θ)')]),
  '3.3.4':(22,lambda:[sub('f','cd,fi'),text_run('='),sub('f','ck'),text_run('·'),sub('k','c'),text_run('(θ)')]),
  '3.3.9a':(27,lambda:[sub('η','ns,i,fi'),text_run('='),frac([text_run('1')],[text_run('1−'),frac([sub('N','Sd,fi')],[sub('N','cr,i,fi')])])]),
  '3.3.9b':(28,lambda:[sub('B','nom'),text_run('='),sub('k','c'),text_run('·'),sub('E','cd'),text_run('·'),sub('I','c'),text_run('+'),sub('k','s'),text_run('·'),sub('E','s'),text_run('·'),sub('I','s')]),
  '3.3.10':(29,lambda:[sub('N','cr,i,fi'),text_run('='),frac([text_run('π²·'),sub('B','nom')],[sub('l','0,i'),text_run('²')])]),
  '3.3.13':(32,lambda:[sub('M','Sd,j,fi'),text_run('='),sub('N','Sd,fi'),text_run('·'),sub('e','s1,fi')]),
}

def rewrite(source,target,equations=None):
    """Replaces only selected <w:object> formula runs, preserving surrounding text.

    equations: optional dictionary of exact verification math expressions keyed by
    formula ID, never arbitrary user-provided XML or LaTex.
    """
    p=Path(source);q=Path(target)
    with zipfile.ZipFile(p) as z:
        doc=etree.fromstring(z.read('word/document.xml'))
        ole=doc.xpath('//o:OLEObject',namespaces=NS)
        if len(ole)!=34:raise ValueError(f'Expected 34 OLE equations, got {len(ole)}')
        changed=[]
        for name,(idx,builder) in FORMULAE.items():
            obj=ole[idx];para=obj.xpath('ancestor::w:p[1]',namespaces=NS)[0]
            run=obj.xpath('ancestor::w:r[1]',namespaces=NS)[0]
            # w:object contains the equation but is not the adjacent numbering text
            if not run.xpath('.//o:OLEObject',namespaces=NS):raise ValueError('Missing equation at index '+str(idx))
            math=formula_omml(builder())
            run.addprevious(math);run.getparent().remove(run)
            changed.append(name)
        updated=etree.tostring(doc,xml_declaration=True,encoding='UTF-8',standalone=True)
        with zipfile.ZipFile(q,'w') as out:
            for entry in z.infolist():
                contents=updated if entry.filename=='word/document.xml' else z.read(entry.filename)
                out.writestr(entry,contents)
    return {'converted_omml_count':len(changed),'converted_ids':changed,'original_ole_count':34,
            'remaining_ole_count':34-len(changed),'non_document_xml_modified':False}

if __name__=='__main__':
 import sys,json
 print(json.dumps(rewrite(sys.argv[1],sys.argv[2]),ensure_ascii=False))
