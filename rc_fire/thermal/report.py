"""R0.6.2 textual normative thermal annex, preserving DOCX stamp/frame."""
from __future__ import annotations


def add_thermal_section(doc,c,calc):
    from multicolumn_r05.parametric_report import add_heading,add_text,add_table,number
    t=calc.get('thermal_normative')
    if t is None:return
    add_heading(doc,'R0.6.2 — теплотехнический расчет по приложению К',2)
    add_text(doc,'Нормативная основа: СП 2.02.05-2026, приложение К. '
             'Температурная модель не является подтверждением R по несущей способности.')
    add_text(doc,'Статус: '+t['status']+'. Источник: '+t.get('source','')+'.')
    if t['status']=='not_evaluated':
        add_text(doc,'Отсутствующие параметры: '+', '.join(t.get('missing',[])))
        return
    if t['status']=='invalid':
        add_text(doc,'Ошибка области применения: '+t.get('reason',''))
        return
    coeff=t['coefficients']
    add_table(doc,['Параметр','Значение','Источник'],[
        ('a_red, м²/ч',number(coeff['a_red_m2_h'],7),coeff['a_red_source']),
        ('φ1',number(coeff['phi_1'],4),'таблица К.2'),
        ('φ2',number(coeff['phi_2'],4),'таблица К.2'),
        ('ρ0, кг/м³',number(coeff['rho_dry_kg_m3'],2),'пользователь; таблица К.2'),
        ('θcr, °C',number(t.get('critical_temperature_C'),1),'§8.2.21'),
        ('Число нагреваемых сторон',str(len(t['exposed_faces'])),'формулы К.6–К.10'),
    ])
    add_text(doc,'Температуры определены по '+t['formula']+
             ', продолжительность '+number(t['fire_minutes'],1)+' мин.')
    if t.get('reinforcement'):
        add_table(doc,['Стержень','x, мм','y, мм','Ø, мм','θ, °C'],[
            (b['id'],number(b['x_mm'],1),number(b['y_mm'],1),number(b['diameter_mm'],1),
             number(b['theta_C'],2)) for b in t['reinforcement']])
    crit=t.get('critical_section') or {}
    if crit.get('status')=='evaluated':
        add_text(doc,'Остаточная площадь по К.27: '+number(crit['remaining_area_m2'],6)+' м²; '
                 'ψ='+number(crit['psi'],4)+'.')
    if t.get('issues'):
        add_text(doc,'Ограничения области применения: '+'; '.join(t['issues']))
    add_text(doc,'Результаты не использованы для нормативного подтверждения устойчивости, '
             'несущей способности или заявленного предела огнестойкости.')