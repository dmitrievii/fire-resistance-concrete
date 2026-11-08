"""Generate per-column and single combined DOCX/PDF while retaining master VML footer/frame.

Complete load cases get full R0.4 parametric diagnostic per-column reports.
Missing loads get *drafts*; no invented resistance or R90 certification.
Combined document contains a project overview and each column's inputs,
reinforcement diagram, per-bar thermal characteristics, and calculated
section-specific Ncr / eta / MEd / MRd diagnostics.
"""
from __future__ import annotations
import io
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import tempfile
import subprocess
import shutil
from docx import Document
from docx.shared import Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from multicolumn_r05.parametric_report import (_prune_document,add_heading,add_text,add_table,add_equation,
    omml_subscript,_figure,restore_exact_original_footer,verify_footer_unchanged,create_report,number)
from multicolumn_r05.clean_unused import prune_unused_template_assets
from multicolumn_r05.project_model import CONCRETE,to_engine_input,load_state
from multicolumn_r05.r056_reporting import add_r056_diagnostics
from rc_fire.resistance.report import add_resistance_history_note
from multicolumn_r05.parametric_engine import GeneralInput

HERE=Path(__file__).resolve().parent
MASTER=HERE.parent/'templates'/'RC_Fire_Report_Master.docx'
STATUS_RU={'pending':'Не рассчитано','partial':'Частично рассчитано','calculated':'Рассчитано (диагностически)',
           'invalid':'Ошибка исходных данных','error':'Ошибка расчёта'}
LOAD_RU={'empty':'Не задано','ready':'Заполнено','incomplete':'Неполные нагрузки','invalid':'Некорректно'}


def clean_filename(s):
    return ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in s)[:45] or 'column'


def init_master(template=MASTER):
    doc=Document(template)
    _prune_document(doc)
    doc.sections[0].bottom_margin=Cm(3.2)
    return doc


def finish(doc,out,template=MASTER):
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    doc.save(out)
    restore_exact_original_footer(template,out)
    prune_unused_template_assets(out)
    if not verify_footer_unchanged(template,out):
        raise RuntimeError('Footer/stamp byte preservation failed')
    return out


def add_column(doc,c,calc):
    add_heading(doc,f'{c["name"]} — характеристики и расчётные сечения',1)
    add_text(doc,'Параметрический диагностический расчёт. Не является нормативным подтверждением R90.',bold=True)
    add_resistance_history_note(doc,calc)
    # R064D_REPOSITORY_HOOK: no extra pages for an unrequested member diagnostic.
    if calc.get("member_r064d",{}).get("status") not in (None, "NOT_EVALUATED"):
        from rc_fire.integration.report import add_member_evidence_note
        add_member_evidence_note(doc,calc)
    add_table(doc,['Характеристика','Значение'],[
        ('Сечение, мм',f'{c["b_mm"]:g} × {c["h_mm"]:g}'),
        ('Длина, м',number(c['length_m'],2)),
        ('Бетон',c['concrete']),('Продольная арматура',c['steel_grade']),
        ('Ø продольных стержней по умолчанию, мм',number(c['bar_diameter_mm'],1)),
        ('Защитный слой до поверхности хомута, мм',number(c['cover_mm'],1)),
        ('Хомут Ø, мм',number(c['stirrup_mm'],1)),
        ('Коэффициенты расчётной длины μx / μy',f'{number(c["mu_x"],2)} / {number(c["mu_y"],2)}'),
        ('Пожар, мин',number(c['fire_minutes'],0)),
        ('Состояние расчёта',STATUS_RU.get(calc['status'],calc['status']))])
    add_heading(doc,'Сечения и нагрузки',2)
    add_table(doc,['Сечение','z, м','N, кН','Mx, кН·м','My, кН·м','Статус'],[
        (s['name'],number(s['z_m'],2),number(s['N_kN'],2) if s['N_kN'] is not None else '—',
         number(s['Mx_kNm'],2) if s['Mx_kNm'] is not None else '—',
         number(s['My_kNm'],2) if s['My_kNm'] is not None else '—',LOAD_RU[load_state(s)]) for s in c['sections']])
    add_heading(doc,'Армирование',2)
    # For uncalculated cases it is still possible to draw exact supplied geometry.
    from multicolumn_r05.parametric_engine import GeneralVariant,Bar
    from dataclasses import replace
    # _figure needs GeneralInput-like b/h and variant-like bars. Use cheap structs.
    from types import SimpleNamespace
    spec=SimpleNamespace(b_m=c['b_mm']/1000,h_m=c['h_mm']/1000)
    variant=SimpleNamespace(id=c['name'],bars=[SimpleNamespace(id=b['id'],x_m=b['x_mm']/1000,
           y_m=b['y_mm']/1000,diameter_mm=b['diameter_mm']) for b in c['bars']])
    p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(_figure(spec,variant),width=Cm(12.0))
    add_table(doc,['Стержень','x, мм','y, мм','Ø, мм','A, мм²'],[
        (b['id'],number(b['x_mm'],1),number(b['y_mm'],1),number(b['diameter_mm'],1),
         number(3.141592653589793*b['diameter_mm']**2/4,1)) for b in c['bars']])
    # Automatically derived material schedule; manufacture/cut lengths are deliberately not invented.
    by_diameter={}
    for bar in c['bars']:
        d=float(bar['diameter_mm'])
        by_diameter[d]=by_diameter.get(d,0)+1
    add_heading(doc,'Спецификация продольных стержней (по диаметрам)',2)
    add_table(doc,['Диаметр, мм','Количество, шт.','Суммарная площадь As, мм²','Масса на 1 м, кг/м'],[
      (number(d,1),str(n),number(n*3.141592653589793*d*d/4,1),
       number(n*3.141592653589793*(d/1000)**2/4*7850,3))
      for d,n in sorted(by_diameter.items())])
    add_text(doc,'Длины заготовок и масса готовых изделий не определяются без данных о продольных стыках, анкеровке и загибах.')
    if calc['issues']:
        for note in calc['issues']:add_text(doc,'Диагностика: '+str(note))
    if not calc['results']:
        add_text(doc,'РАСЧЁТ НЕ ВЫПОЛНЕН: отсутствуют полные усилия по расчётным сечениям либо исходные данные некорректны. Заключение об огнестойкости не формируется.',bold=True)
        add_r056_diagnostics(doc,c,calc)
        return
    add_heading(doc,'Температурные и расчётные результаты',2)
    add_equation(doc,'', [omml_subscript('M','Ed'), ' / ',omml_subscript('M','Rd'),
       ' — диагностический коэффициент использования по отдельной плоскости'])
    for s in c['sections']:
        v=calc['results'].get(s['id'])
        if v is None:
            add_text(doc,f'{s["name"]}: исходные усилия не заполнены, результат отсутствует.')
            continue
        add_heading(doc,f'{s["name"]} — расчёт',2)
        add_table(doc,['Ось','Ncr, кН','η','MEd, кН·м','MRd, кН·м','u'],[
            (axis,number(a['N_cr_kN'],2),number(a['eta'],3),number(a['M_Ed_kNm'],2),
             number(a['M_Rd_kNm'],2),number(a['utilization'],3))
            for axis,a in v['axes'].items()])
        for axis,a in v['axes'].items():
            add_equation(doc,f'{s["name"]}/{axis}',[omml_subscript('M','Ed,'+axis),
               ' = (abs(',number(a['M0_kNm'],2),') + ',number(v['N_kN'],2),'·',
               number(a['imperfection_e_m'],4),')·',number(a['eta'],3),' = ',
               number(a['M_Ed_kNm'],2),' кН·м'])
        if v.get('bars'):
            add_table(doc,['Ст.','T, °C','k(T)','β(T)'],[
                (b['id'],number(b['temperature_C'],1),number(b['k'],3),number(b['beta'],3))
                for b in v['bars']])
    add_r056_diagnostics(doc,c,calc)
    if calc['worst']:
        x=calc['worst']
        add_text(doc,f"Максимальный диагностический u = {number(x['u'],3)}, "
            f"сечение {x['section_id']}, ось {x['axis'].upper()}.",bold=True)


def single_report(c,calc,target,template=MASTER):
    """One independent DOCX; detailed R0.4 algorithm for fully loaded columns."""
    if calc['status']=='calculated':
        inp=to_engine_input(c,grid=calc.get('grid',48))
        # R0.4 report requires a single common geometry and lists each section as variant
        result=calc.get('raw_results')
        if result is None:
            from multicolumn_r05.parametric_engine import compute_general
            result=compute_general(GeneralInput.from_dict(inp))
        legacy_audit=create_report(template,inp,result,target)
        doc=Document(target)
        doc.add_page_break()
        add_r056_diagnostics(doc,c,calc)
        add_resistance_history_note(doc,calc)
        if calc.get('member_r064d',{}).get('status') not in (None, 'NOT_EVALUATED'):
            from rc_fire.integration.report import add_member_evidence_note
            add_member_evidence_note(doc,calc)
        finish(doc,target,template)
        return legacy_audit
    doc=init_master(template)
    add_heading(doc,'РАСЧЁТНЫЙ ОТЧЁТ — ЧЕРНОВИК',1)
    add_column(doc,c,calc)
    add_heading(doc,'Выводы',1)
    add_text(doc,'Нагрузки отсутствуют или не полностью заданы. Расчётная огнестойкость НЕ определена.',bold=True)
    finish(doc,target,template)
    return {'report_path':str(target),'report_class':'draft','footer_parts_unchanged':True}


def combined_report(project,calculations,target,template=MASTER):
    doc=init_master(template)
    add_heading(doc,'СВОДНЫЙ РАСЧЁТ ЖЕЛЕЗОБЕТОННЫХ КОЛОНН',1)
    add_text(doc,project.get('title','Проект'))
    add_text(doc,'Отчёт представляет исходные данные и диагностические результаты. Положительное заключение о R90 по экспериментальной параметрической модели НЕ выдаётся.',bold=True)
    add_heading(doc,'Обзор конструкций',2)
    rows=[]
    for c in project['columns']:
        calc=calculations[c['id']];w=calc.get('worst')
        rows.append((c['name'],f"{c['b_mm']:g}×{c['h_mm']:g}",number(c['length_m'],2),
                    c['concrete'],str(len(c['sections'])),
                    number(w['u'],3) if w else '—',STATUS_RU.get(calc['status'],calc['status'])))
    add_table(doc,['Колонна','b×h, мм','L, м','Бетон','Сеч.','max u','Статус'],rows)
    add_text(doc,'max u = максимальное MEd/MRd по рассчитанным осям и сечениям; диагностическая величина, не нормативный критерий совместного действия N–Mx–My.')
    for c in project['columns']:
        doc.add_page_break()
        add_column(doc,c,calculations[c['id']])
    add_heading(doc,'Выводы',1)
    add_text(doc,'Объединённые результаты и статус каждого расчётного элемента:',bold=True)
    add_table(doc,['Колонна','Сечений всего','Сечений рассчитано','Макс. u','Статус'],[
        (c['name'],str(len(c['sections'])),str(len(calculations[c['id']]['results'])),
         number(calculations[c['id']]['worst']['u'],3) if calculations[c['id']]['worst'] else '—',
         STATUS_RU.get(calculations[c['id']]['status'],calculations[c['id']]['status'])) for c in project['columns']])
    add_text(doc,'Нормативное заключение о пределе огнестойкости по этому расчётному выпуску не формируется. Незаполненные нагрузки и диагностические значения указаны явно.',bold=True)
    add_text(doc,'Расчётные данные и все нагрузки сохраняются в project.json. Для повторного выпуска документа рекомендуется использовать тот же набор исходных данных, редакцию вычислительного движка и геометрию стержней.')
    return finish(doc,target,template)


def pdf_from_docx(path,out_dir=None):
    lo=shutil.which('libreoffice') or shutil.which('soffice')
    if not lo:raise RuntimeError('Для PDF необходим LibreOffice (Word DOCX доступен)')
    path=Path(path)
    output=Path(out_dir or path.parent);output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        cmd=[lo,f'-env:UserInstallation=file://{tmp}/profile','--headless',
            '--convert-to','pdf','--outdir',str(output),str(path)]
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=120)
        if p.returncode!=0:raise RuntimeError(p.stderr or p.stdout)
    pdf=output/(path.stem+'.pdf')
    if not pdf.exists() or pdf.stat().st_size<1000:raise RuntimeError('PDF не сформирован')
    return pdf


def make_exports(project,calcs,pdf=True,template=MASTER):
    """In-memory ZIP for Streamlit; one combined DOCX/PDF and per-column DOCX/PDF."""
    from multicolumn_r05.project_model import export_json
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        combined=combined_report(project,calcs,root/'combined.docx',template)
        allpaths=[('Общий_отчет.docx',combined)]
        if pdf:
            allpaths.append(('Общий_отчет.pdf',pdf_from_docx(combined)))
        for c in project['columns']:
            name=clean_filename(c['name'])+'_'+c['id']
            p=root/(name+'.docx')
            single_report(c,calcs[c['id']],p,template)
            allpaths.append((f'Конструкции/{name}.docx',p))
            if pdf:allpaths.append((f'Конструкции/{name}.pdf',pdf_from_docx(p)))
        data=io.BytesIO()
        with ZipFile(data,'w',ZIP_DEFLATED) as z:
            for name,p in allpaths:z.write(p,arcname=name)
            z.writestr('project.json',export_json(project))
            z.writestr('summary.json',json.dumps(calcs,ensure_ascii=False,indent=2,default=str))
        return data.getvalue()