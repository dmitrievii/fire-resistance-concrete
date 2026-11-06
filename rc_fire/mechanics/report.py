"""R0.6.3 DOCX appendix; cannot generate a positive R-limit verdict."""
from __future__ import annotations


def add_mechanics_section(doc, column:dict, calculation:dict):
    from multicolumn_r05.parametric_report import add_heading, add_text, add_table
    result=calculation.get('mechanics_r063')
    if not result:return
    add_heading(doc,'R0.6.3 — совместная механика сечений N–Mx–My',2)
    add_text(doc,'Нормативная основа: СП 2.02.05-2026 (§8.2.18–8.2.20, таблицы 9–10); '
             'СП 5.03.01-2020 (§4.2.5.3, §6.1.5, §6.2.2, §8.1.2). '
             'Метод: плоские сечения, параболически-линейный бетон, двухлинейная арматура.')
    add_text(doc,'СТАТУС: '+result['status']+'. Это отдельный численный расчёт сечения; '
             'его сходимость НЕ подтверждает предел огнестойкости R90. '
             'Глобальная устойчивость, температурное защемление и образование '
             'хрупких сколов бетона рассчитываются отдельно.')
    m=result.get('material_strengths') or {}
    if m:
        add_table(doc,['Характеристика','Значение','Основание'],[
          ('γc, особая ситуация',f"{m['gamma_c']:.3f}",'Таблица 4.6'),
          ('γs, особая ситуация',f"{m['gamma_s']:.3f}",'Таблица 4.6'),
          ('αcc',f"{m['alpha_cc']:.4f}",'Формула (6.5)'),
          ('fcd, 20 °C, МПа',f"{m['f_cd_MPa']:.4f}",'Формула (6.4)'),
          ('fyd, 20 °C, МПа',f"{m['f_yd_MPa']:.4f}",'Формула (6.28)'),
          ('Ecm, 20 °C, ГПа',str(m['Ecm_ambient_GPa']),'Таблица 6.3'),
        ])
    rows=[]
    for sid,rec in result.get('sections',{}).items():
        residual=rec.get('relative_residual')
        details=rec.get('details') or {}
        rows.append((sid,rec['status'],
            '—' if residual is None else f'{residual:.4e}',
            '—' if not details else f"{details['max_concrete_compression']*1000:.3f}",
            '—' if not details else f"{details['min_steel_strain']*1000:.3f}"))
    if rows:
        add_table(doc,['Сечение','Результат','Невязка','εc,max, ‰','εs,min, ‰'],rows)
    if result.get('issues'):
        add_text(doc,'Ограничения и исходные допущения: '+ '; '.join(result['issues']))
    add_text(doc,'Расчёт R(t), пространственная устойчивость, поперечная сила и '
             'нормативная квалификация сопротивления остаются открытыми. '
             'Положительное заключение R90 запрещено.')