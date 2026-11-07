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
    # R0.6.3B: expose qualification blockers directly in the engineering report.
    q=result.get('constitutive_qualification') or {}
    if q:
        add_heading(doc,'R0.6.3B — квалификация температурных диаграмм',3)
        add_text(doc,'Статус диаграмм: '+q['status']+'. Численное равновесие и '
                 'наличие коэффициентов таблиц 9/10 не подтверждают R90.')
        refs=q['reference_strength_options_MPa']
        add_table(doc,['Параметр','Значение','Пояснение'],[
            ('fck, МПа',f"{refs['characteristic_fck']:.4f}",'Нормативная (характеристическая) прочность'),
            ('fcd, МПа',f"{refs['design_fcd']:.4f}",'Расчетная прочность, текущий код'),
            ('fck/fcd',f"{refs['ratio_fck_over_fcd']:.4f}",'Трактовка §8.2.18 требует разрешения'),
            ('Т max, граница, °C',str(q['temperature_ranges_C'].get('boundary_max_C')),
             'Проверка области температурных таблиц'),
            ('Арматура 20–200 °C',str(q['counts']['steel_bridge_20_200']),
             'Стержней с ненормативной интерполяцией')
        ])
        add_text(doc,'Незакрытые зависимости: '+ '; '.join(q['issues']))
    cl=result.get('constitutive_closure_r063c') or {}
    if cl:
        add_heading(doc,'R0.6.3C — нормативная сверка температурных диаграмм',3)
        add_text(doc,'Статус: '+cl['status']+'. Текстовая трактовка сопротивлений при пожаре '
                 'зафиксирована, но температурная диаграмма и R90 не квалифицированы.')
        c=cl['strength_comparison']['concrete']
        add_table(doc,['Показатель','МПа','Статус'],[
          ('fc,θ по буквальному §8.2.18',f"{c['literal_SP_8_2_18_MPa']:.3f}",'Нормативное значение × kc'),
          ('fc,θ прежняя диагностическая реализация',f"{c['legacy_accidental_fcd_times_kc_MPa']:.3f}",'fcd × kc'),
          ('Абсолютное расхождение',f"{c['difference_MPa']:.3f}",'Не путать расчётные маршруты')])
        for d in cl['decisions']:
            add_text(doc,d['code']+': '+d['normative_status']+' — '+d['engineering_consequence'])
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
