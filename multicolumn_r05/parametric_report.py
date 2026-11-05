"""Parametric diagnostic DOCX based on the supplied K18 Word visual master.

Reuses the original's actual footer/frame/stamp OOXML and page geometry without
modifying them. Keeps the section order; replaces *inapplicable* K18-specific
content, equations, tables and diagrams with transparent numerical model output.
All mathematical equations are genuine editable OMML; no fake editable OLE images.

IMPORTANT: This report is an EXPERIMENTAL model diagnostic, not a certification
of fire resistance or compliance with Belarusian design rules.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
import io
import json
import math
import textwrap

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
import numpy as np
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, Cm

from multicolumn_r05.parametric_engine import GeneralInput

M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
MNT = '{'+M+'}'


def number(v, digits=3):
    if isinstance(v, str):return v
    if isinstance(v, bool): return 'да' if v else 'нет'
    if not math.isfinite(float(v)):
        return '∞' if float(v)>0 else '−∞'
    return f'{float(v):.{digits}f}'.replace('.', ',')


def clean_num(v, digits=3):
    if isinstance(v, str):return v
    if not math.isfinite(float(v)):return number(v,digits)
    if digits == 0: return f'{float(v):.0f}'
    return (f'{float(v):.{digits}f}'.rstrip('0').rstrip('.')).replace('.',',')


def omml_text(text):
    r=OxmlElement('m:r')
    rp=OxmlElement('m:rPr')
    sty=OxmlElement('m:sty');sty.set(qn('m:val'),'p');rp.append(sty)
    r.append(rp)
    t=OxmlElement('m:t');t.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
    t.text=str(text);r.append(t)
    return r


def omml_subscript(base,sub):
    x=OxmlElement('m:sSub')
    for name, val in (('e',base),('sub',sub)):
        el=OxmlElement('m:'+name); el.append(omml_text(val));x.append(el)
    return x


def omml_fraction(numer,denom):
    f=OxmlElement('m:f')
    for name,val in (('num',numer),('den',denom)):
        child=OxmlElement('m:'+name)
        child.append(omml_text(val))
        f.append(child)
    return f


def add_equation(doc,label,nodes):
    p=doc.add_paragraph()
    p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before=Pt(4)
    p.paragraph_format.space_after=Pt(5)
    eq=OxmlElement('m:oMath');
    for node in nodes:
        if isinstance(node,str): eq.append(omml_text(node))
        else: eq.append(node)
    p._p.append(eq)
    if label:
        run=p.add_run('    '+label);run.italic=True;run.font.size=Pt(9)
    return p


def add_heading(doc,text,level=1):
    p=doc.add_paragraph()
    p.alignment=WD_ALIGN_PARAGRAPH.CENTER if level==1 else WD_ALIGN_PARAGRAPH.LEFT
    r=p.add_run(text);r.bold=True;r.font.name='Times New Roman';r.font.size=Pt(13 if level==1 else 12)
    p.paragraph_format.space_before=Pt(14 if level==1 else 10)
    p.paragraph_format.space_after=Pt(8)
    p.paragraph_format.keep_with_next=True
    return p


def add_text(doc,text,bold=False):
    p=doc.add_paragraph()
    p.paragraph_format.space_after=Pt(6)
    p.paragraph_format.line_spacing=1.15
    r=p.add_run(text);r.font.name='Times New Roman';r.font.size=Pt(11);r.bold=bold
    return p


def add_table(doc,headers,rows,widths=None):
    t=doc.add_table(rows=1, cols=len(headers))
    t.style='Table Grid'
    t.alignment=WD_TABLE_ALIGNMENT.CENTER
    t.autofit=False
    for i,v in enumerate(headers):
        c=t.cell(0,i);c.text=str(v);c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
    for row in rows:
        cells=t.add_row().cells
        for i,v in enumerate(row):cells[i].text=str(v)
    for i,row in enumerate(t.rows):
        for j,c in enumerate(row.cells):
            for p in c.paragraphs:
                p.paragraph_format.space_after=Pt(0)
                for r in p.runs:
                    r.font.name='Times New Roman';r.font.size=Pt(9 if len(headers)<=5 else 8)
                    if i==0:r.bold=True
            c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
    # Header row repeats on multi-page schedules.
    trPr=t.rows[0]._tr.get_or_add_trPr()
    repeat=OxmlElement('w:tblHeader');repeat.set(qn('w:val'),'true');trPr.append(repeat)
    doc.add_paragraph().paragraph_format.space_after=Pt(0)
    return t


def _figure(s:GeneralInput,v,width=6.8):
    # Bar-centre coordinates are reported as supplied; do not infer concrete cover.
    fig,ax=plt.subplots(figsize=(7.1,4.7),dpi=150)
    b,h=s.b_m*1000,s.h_m*1000
    ax.add_patch(Rectangle((0,0),b,h,facecolor='#F5F6F8',edgecolor='black',linewidth=2))
    from matplotlib import cm, colors
    ts=[]
    for bar in v.bars:
        radius=bar.diameter_mm/2
        xx=bar.x_m*1000;yy=bar.y_m*1000
        ax.add_patch(Circle((xx,yy),radius,facecolor='#344F6D',edgecolor='#ffffff',lw=.7))
        ax.annotate(bar.id,(xx,yy),xytext=(5,5),textcoords='offset points',fontsize=7,color='black')
    ax.set_xlim(-b*.12,b*1.12);ax.set_ylim(-h*.13,h*1.13)
    ax.set_aspect('equal');ax.set_xlabel('x, мм');ax.set_ylabel('y, мм')
    ax.set_title(f'Вариант {v.id}: {int(round(b))}×{int(round(h))} мм; стержней {len(v.bars)}',fontsize=11)
    ax.grid(alpha=.14,linestyle=':')
    fig.tight_layout()
    stream=io.BytesIO();fig.savefig(stream,format='png',dpi=150,facecolor='white');plt.close(fig)
    stream.seek(0);return stream


def _prune_document(doc):
    # Critical: the first (body-internal) section is where the original engineering
    # stamp/footer is anchored. The last section inherited that footer by reference.
    # Keeping only the last sectPr would silently remove the frame.
    root=doc.element.body
    first=deepcopy(doc.sections[0]._sectPr)
    for el in list(root):root.remove(el)
    root.append(first)
    doc.sections[0].different_first_page_header_footer=False


def create_report(template, input_data, results, target, verbose=False):
    s=GeneralInput.from_dict(input_data)
    doc=Document(template)
    _prune_document(doc)
    # Keep the original page size and exact engineering frame, but reserve a safe
    # lower body area so long dynamic schedules cannot overlap the fixed stamp.
    doc.sections[0].bottom_margin=Cm(3.2)
    # Use the original's page dimensions, frame VML and stamp.
    add_heading(doc,'РАСЧЁТ ЖЕЛЕЗОБЕТОННОЙ КОЛОННЫ ПРИ ПОЖАРЕ',1)
    add_heading(doc,'Параметрическая диагностика. Не является подтверждением R90.',2)
    add_text(doc,'Исходный графический образец: предоставленный отчёт К18. Рамка, штамп, формат страницы и порядок основных разделов наследуются от эталона. Расчётная модель для произвольного армирования отличается от исходного Mathcad.')
    add_text(doc,'ПРЕДУПРЕЖДЕНИЕ: численная модель экспериментальная; она не обеспечивает нормативную проверку совместного действия N–Mx–My и температурную нелинейность бетона; расчёт критерия хрупкого разрушения F при наличии исходных коэффициентов приведён отдельно в приложении R0.5.6. Заключение о классе огнестойкости не выдаётся.',bold=True)

    add_heading(doc,'Содержание')
    sections=['Введение','Общие положения','1. Подходы и методы, используемые для оценки огнестойкости строительных конструкций', '2. Нагрузки и воздействия',
              '3. Оценка огнестойкости железобетонных конструкций','3.1 Описание железобетонных колонн, подлежащих расчету',
              '3.2 Теплотехнический расчет','3.3 Статический расчет сжатых железобетонных элементов',
              '3.4 Оценка хрупкого разрушения','Выводы','Литература']
    for x in sections:add_text(doc,x)

    add_heading(doc,'Введение')
    add_text(doc,'Цель: воспроизводимый расчёт температурного поля и диагностических показателей напряжённо-деформированного состояния прямоугольного железобетонного сечения с индивидуальными координатами стержней. Значения, приведённые далее, получены новым Python-вычислителем.')
    add_heading(doc,'Общие положения')
    add_text(doc,f'Модель: прямоугольное сечение {clean_num(s.b_m*1000,0)} × {clean_num(s.h_m*1000,0)} мм; длина {number(s.length_m,2)} м; продолжительность пожара {clean_num(s.fire_minutes,0)} мин; нагрев: четыре грани. Разделы отчёта повторяют эталонный документ; неподходящие заключения из исходного отчёта не переносятся.')

    add_heading(doc,sections[2])
    add_text(doc,'Использован численный волоконный метод в предположении плоских сечений. Бетон при растяжении не учитывается; при сжатии принята упруго-идеально-пластическая диаграмма с ограничением 3,5‰, арматура — упруго-идеально-пластическая с температурными коэффициентами из восстановленной таблицы Mathcad. Расчёт не является применением утверждённой расширенной нормативной модели.')
    add_text(doc,'Сечения рассматриваются отдельно в плоскостях X и Y. Индексы использования двух плоскостей не объединяются в нормативную поверхность взаимодействия. Численный поиск максимального момента выполняется по конечному набору кривизн, что обуславливает погрешность дискретизации.')

    add_heading(doc,sections[3])
    loadrows=[]
    for v in s.variants:
        loadrows.append((v.id,number(v.N_kN,2),number(v.M_x_kNm,2),number(v.M_y_kNm,2),str(len(v.bars))))
    add_table(doc,['Вариант','N, кН','Mx, кН·м','My, кН·м','Стержней'],loadrows)
    add_text(doc,f'Коэффициенты расчётной длины: μx={number(s.mu_x,3)}, μy={number(s.mu_y,3)}. Начальные эксцентриситеты по каждому направлению учитываются через ℓ0/400 и не менее 20 мм. Знаки моментов сохраняются при определении направления кривизны.')

    add_heading(doc,sections[4])
    add_heading(doc,sections[5],2)
    add_text(doc,f'Сечение: b = {number(s.b_m,3)} м, h = {number(s.h_m,3)} м, длина = {number(s.length_m,2)} м. Материалы: fck={clean_num(s.f_ck_MPa,1)} МПа, Ec={number(s.E_cm_GPa,2)} ГПа; fyk={clean_num(s.f_y_MPa,0)} МПа, Es={clean_num(s.E_s_GPa,0)} ГПа.')
    for v in s.variants:
        p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER
        p.add_run(f'Рисунок 3.1.{v.id} — расположение арматуры, вариант {v.id}').bold=True
        pic=doc.add_paragraph();pic.alignment=WD_ALIGN_PARAGRAPH.CENTER
        pic.add_run().add_picture(_figure(s,v),width=Cm(12.4))
        add_table(doc,['№','x, мм','y, мм','Ø, мм','As, мм²'],[
            (b.id,number(b.x_m*1000,1),number(b.y_m*1000,1),number(b.diameter_mm,1),number(math.pi*b.diameter_mm**2/4,2)) for b in v.bars
        ])

    add_heading(doc,sections[6],2)
    add_text(doc,'Температура рассчитывается из исходного четырёхстороннего выражения Mathcad на основе относительных расстояний от нагретых поверхностей. Поверхности считаются симметрично нагретыми; при других условиях эта реализация не применима.')
    t=s.fire_minutes/60
    ell=math.sqrt(12*s.a_red_m2_h*t)
    add_equation(doc,'(3.2.7)',[omml_subscript('ℓ','тепл'),' = √(12 · ',omml_subscript('a','red'),' · τ) = √(12 · ',number(s.a_red_m2_h,5),' · ',number(t,2),') = ',number(ell,4),' м'])
    add_equation(doc,'(3.2.12)', ['θ(x,y) = 1220 − 1200 · [1 − (1−r₁)² − (1−r₂)²] · [1 − (1−r₃)² − (1−r₄)²]'])
    add_text(doc,f'Параметры: ared={number(s.a_red_m2_h,5)} м²/ч; φ1={number(s.phi_1,2)}; φ2={number(s.phi_2,2)}; порог температуры бетона {number(s.critical_concrete_C,0)} °C. Область эффективного бетонного сечения определяется сеточным отсечением ячеек с превышением порога.')
    C=results['concrete']
    add_table(doc,['Геометрический параметр','Расчётное значение'],[
        ('Площадь эффективного бетона, м²',number(C['effective_area_m2'],6)),
        ('Ix, м⁴',number(C['Ix_m4'],7)),('Iy, м⁴',number(C['Iy_m4'],7)),
        ('Число сохранённых конечных ячеек',str(C['effective_cells'])),
        ('Размер шага сетки, м',number(C['grid_m'],5))])
    for vid,v in results['variants'].items():
        add_text(doc,f'Температуры и коэффициенты арматуры — {vid}',bold=True)
        add_table(doc,['Стержень','T, °C','k(T)','β(T)','As, мм²'],[
            (b['id'],number(b['temperature_C'],1),number(b['k'],3),number(b['beta'],3),number(b['area_m2']*1e6,2)) for b in v['bars']])

    add_heading(doc,sections[7],2)
    add_text(doc,'Параметрическая схема рассчитывает равновесие продольных внутренних усилий при заданной кривизне в каждой главной плоскости. Для каждого расчётного сечения определяется максимум сопротивления изгибу на вычисленной дискретной сетке кривизн. Это не замена нормативной поверхности взаимодействия.')
    add_equation(doc,'(3.3.1*)',['σc = min(max(Ec·εc, 0), fck);    σs = clip(Es(T)·εs, −fyk(T), +fyk(T))'])
    add_equation(doc,'(3.3.2*)',[omml_subscript('N','int'),' = Σ(σc·Ac) + Σ(σs·As) = ',omml_subscript('N','Ed')])
    add_equation(doc,'(3.3.3*)',[omml_subscript('M','int'),' = Σ(σ·A·z);    ',omml_subscript('M','Rd'),' = maxκ |Mint(κ)|'])
    add_equation(doc,'(3.3.9*)',[omml_subscript('N','cr,i'),' = ',omml_fraction('π² Bi','ℓ0,i²'),';    ηi = ',omml_fraction('1','1−N/Ncr,i')])
    add_equation(doc,'(3.3.13*)',[omml_subscript('M','Ed,i'),' = (|M0,i| + N · max(ℓ0,i/400, 0,02)) · ηi'])
    for vid,v in results['variants'].items():
        add_text(doc,f'Расчётные характеристики — вариант {vid}',bold=True)
        row=[]
        for axis in ('x','y'):
            a=v['axes'][axis]
            row.append((axis,number(a['l0_m'],3),number(a['I_c_m4'],6),number(a['N_cr_kN'],2),
                number(a['eta'],3),number(a['M_Rd_kNm'],2),number(a['M_Ed_kNm'],2),number(a['utilization'],3)))
            add_equation(doc,f'{vid}/{axis}',[
                omml_subscript('N','cr,'+axis),' = π² × ',number(a['B_Nm2'],0),' / (',number(a['l0_m'],3),'² × 1000) = ',number(a['N_cr_kN'],2),' кН'
            ])
            add_equation(doc,f'{vid}/{axis}',[
                omml_subscript('η',axis),' = 1 / (1 − ',number(v['N_kN'],2),' / ',number(a['N_cr_kN'],2),') = ',number(a['eta'],3)
            ])
            add_equation(doc,f'{vid}/{axis}',[
                omml_subscript('M','Ed,'+axis),' = (',number(abs(a['M0_kNm']),2),' + ',number(v['N_kN'],2),' · ',number(a['imperfection_e_m'],4),') · ',number(a['eta'],3),' = ',number(a['M_Ed_kNm'],2),' кН·м'
            ])
        axx=v['axes']['x']; ayy=v['axes']['y']
        add_table(doc,['Параметр','Плоскость X','Плоскость Y','Размерность'],[
          ('Расчётная длина ℓ₀',number(axx['l0_m'],3),number(ayy['l0_m'],3),'м'),
          ('Момент инерции бетона Ic',number(axx['I_c_m4'],7),number(ayy['I_c_m4'],7),'м⁴'),
          ('Номинальная жёсткость B',number(axx['B_Nm2'],0),number(ayy['B_Nm2'],0),'Н·м²'),
          ('Критическая сила Ncr',number(axx['N_cr_kN'],2),number(ayy['N_cr_kN'],2),'кН'),
          ('Коэффициент η',number(axx['eta'],3),number(ayy['eta'],3),'—'),
          ('Сопротивление MRd',number(axx['M_Rd_kNm'],2),number(ayy['M_Rd_kNm'],2),'кН·м'),
          ('Действующий момент MEd',number(axx['M_Ed_kNm'],2),number(ayy['M_Ed_kNm'],2),'кН·м'),
          ('MEd / MRd',number(axx['utilization'],3),number(ayy['utilization'],3),'—')])
        diagnostics=v.get('biaxial_diagnostic_sum')
        if diagnostics is not None:
            add_text(doc,f'Диагностическая сумма двух осевых коэффициентов: {number(diagnostics,3)}. Это НЕ нормативное условие двухосного предельного состояния.')

    add_heading(doc,sections[8],2)
    add_text(doc,'Расчёт хрупкого разрушения (spalling) в параметрическом вычислителе не реализован. В отсутствие исходных физических параметров, влажности, пористости и подтверждённой модели численное заключение о предотвращении хрупкого разрушения не формируется.')
    add_heading(doc,sections[9])
    add_text(doc,'Итоги численного расчёта (НЕ заключение о подтверждении R90):',bold=True)
    concluding=[]
    for vid,v in results['variants'].items():
        for axis,a in v['axes'].items():
            concluding.append((vid,axis,number(v['N_kN'],2),number(a['M_Rd_kNm'],2),number(a['M_Ed_kNm'],2),number(a['utilization'],3)))
    add_text(doc,'Для таблицы ниже u = MEd / MRd (диагностический коэффициент, не нормативный критерий).')
    add_table(doc,['Вар.','Ось','N, кН','MRd, кН·м','MEd, кН·м','u'],concluding)
    add_text(doc,'Значения являются диагностическими выходными данными экспериментального решателя. Они не подтверждают нормативную огнестойкость, устойчивость от полного совместного действия N–Mx–My или соответствие требованиям проектирования. Применение в инженерном заключении допускается только после независимого аудита и верификации расчётного метода.',bold=True)
    add_heading(doc,sections[10])
    add_text(doc,'Расчётная логика перенесена из предоставленных Mathcad К18 и отчёта «Пример.docx», но параметрический волоконный решатель является новым экспериментальным модулем. Перечень нормативов в оригинальном отчёте не следует интерпретировать как документальную аттестацию этого нового алгоритма.')
    add_text(doc,'Исходные данные и все рассчитанные показатели сохранены в JSON-файле, формулы документа созданы в редактируемом формате OMML.')
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    doc.save(target)
    restore_exact_original_footer(template,target)
    from multicolumn_r05.clean_unused import prune_unused_template_assets
    pruned_assets = prune_unused_template_assets(target)
    from lxml import etree
    with ZipFile(target) as z:
        tree=etree.fromstring(z.read('word/document.xml'))
        eqn_count=len(tree.xpath('//*[local-name()="oMath"]'))
    return {'report_path':str(target),'variants':len(s.variants),'bars_total':sum(len(v.bars) for v in s.variants),
      'equations_omml':eqn_count,
      'footer_parts_unchanged':verify_footer_unchanged(template,target),
      'report_class':'experimental-diagnostic-not-normative', 'pruned_assets':pruned_assets}


def verify_footer_unchanged(template, target):
    with ZipFile(template) as before,ZipFile(target) as after:
        footers=[n for n in before.namelist() if n.startswith('word/footer') and n.endswith('.xml')]
        return bool(footers) and all(before.read(n)==after.read(n) for n in footers)


def restore_exact_original_footer(template,target):
    """Restore footer/header byte for byte after python-docx XML serialisation.

    The original stamp/frame is not merely re-drawn: its OOXML payload remains
    exactly the original file bytes. The sectPr keeps the original footer link.
    """
    import os
    import tempfile
    with ZipFile(template) as source, ZipFile(target) as dest:
        originals={name:source.read(name) for name in source.namelist()
                   if name.startswith(('word/footer','word/header'))}
        fd,tmp=tempfile.mkstemp(suffix='.docx',dir=str(Path(target).parent))
        os.close(fd)
        with ZipFile(tmp,'w') as out:
            for item in dest.infolist():
                out.writestr(item,originals.get(item.filename,dest.read(item.filename)))
    os.replace(tmp,target)