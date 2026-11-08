"""Report appendix for R0.5.6. Keeps approved DOCX footer, stamp and frame intact."""
from multicolumn_r05.parametric_report import add_heading, add_text, add_table, add_equation, number
from rc_fire.thermal.report import add_thermal_section
from rc_fire.mechanics.report import add_mechanics_section

def add_r056_diagnostics(doc,c,calc):
    """New section appended to all reports; does not rewrite the fixed frame/stamp."""
    add_thermal_section(doc,c,calc)
    add_mechanics_section(doc,c,calc)
    add_heading(doc,'R0.5.6 — совместные и дополнительные диагностические проверки',2)
    add_text(doc,'Численная механика R0.5.6 является диагностической. '
             'Ниже приведён вычислительный контроль, а не нормативное подтверждение R90.')
    material=calc.get('material_preflight')
    if material:
        add_heading(doc,'R0.6.1 — нормативные свойства бетона и арматуры',2)
        add_text(doc,'Каталог: '+material['status']+
                 '. Таблицы 6.1/6.3 СП 5.03.01-2020 и 9–12 СП 2.02.05-2026.')
        if material.get('concrete'):
            mc=material['concrete']
            add_text(doc,'Бетон '+str(mc['strength_class'])+
                ': fck='+str(mc['f_ck_MPa'])+' МПа; Ecm='+
                ('НЕ ОПРЕДЕЛЁН' if mc['E_cm_GPa'] is None else str(mc['E_cm_GPa'])+' ГПа')+
                '; происхождение Ecm: '+mc['modulus_source'])
        if material.get('steel'):
            stl=material['steel']
            add_text(doc,'Арматура '+str(stl['group'])+
                     '; Es='+str(stl['E_s_GPa'])+' ГПа.')
        if material.get('issues'):
            add_text(doc,'Недостаточные данные: '+', '.join(material['issues']))
        add_text(doc,'Параметрический решатель остаётся диагностическим. При отсутствии данных '
                 'он использует прежние значения Ecm для сравнения с К18, '
                 'а не как нормативное назначение материала.')
    contract=calc.get('normative_preflight')
    if contract:
        add_heading(doc,'R0.6.0 — нормативный контракт и происхождение результата',2)
        add_text(doc,'СП 2.02.05-2026 + СП 5.03.01-2020; статус '+contract['status']+
                 '; версия '+contract['contract_version']+
                 '; SHA-256 '+contract['contract_sha256']+'.')
        add_text(doc,'Нормативные источники: СП 2.02.05-2026 и СП 5.03.01-2020. '
                 'Проверка предела R90 пока не квалифицирована.')
        add_table(doc,['Код блокировки','Нормативный источник','Причина'],[
            (x['code'],x['clause'],x['message']) for x in contract['issues']])
    member=calc.get('member',{})
    if member.get('status')=='evaluated':
        add_heading(doc,'Устойчивость колонны: общий расчётный конверт',2)
        add_text(doc,'Из исходной формулы Mathcad η=1/(1−N/Ncr) принят диагностический вариант '
                 'Nmax по расчётным сечениям и минимальное Ncr по колонне. '
                 'Это не эквивалент пространственного расчёта второго порядка.')
        add_table(doc,['Ось','Nmax, кН','Ncr,min, кН','η, колонна'],[
            (axis.upper(),number(member['Nmax_kN'],2),number(v['Ncr_min_kN'],2),
             number(v['eta_member'],4)) for axis,v in member['axes'].items()])
        add_table(doc,['Сечение','Ось','MEd, кН·м','MRd, кН·м','u'],[
            (sid,axis.upper(),number(a['M_Ed_kNm'],2),number(a['M_Rd_kNm'],2),
             number(a['utilization'],4)) for sid,axes in member['sections'].items()
            for axis,a in axes.items()])
    else:
        add_text(doc,'Общий расчётный конверт устойчивости: '+str(member.get('status','не рассчитан')))
    biax=calc.get('biaxial',{})
    add_heading(doc,'Совместное равновесие N–Mx–My',2)
    add_text(doc,'Одновременно решены три уравнения равновесия на дискретизированном '
             'сечении с учетом температур арматуры. Это экспериментальная модель, '
             'не утверждённая нормативная поверхность предельных состояний.')
    if biax.get('sections'):
        add_table(doc,['Сечение','Статус','N, кН','Mx, кН·м','My, кН·м','εc,max'],[
            (sid,{'equilibrium_within_strain':'Равновесие выполнено',
                  'concrete_strain_exceeded':'Превышена εc',
                  'equilibrium_not_found':'Нет решения',
                  'axial_capacity_outside':'N вне диапазона',
                  'invalid_demand':'Некорректная нагрузка'}.get(r['status'],r['status']),number(r['N_demand_kN'],1),number(r['Mx_demand_kNm'],2),
             number(r['My_demand_kNm'],2),number(r['eps_c_max'],6) if r.get('eps_c_max') is not None else '—')
            for sid,r in biax['sections'].items()])
    else:
        add_text(doc,'Совместное равновесие не рассчитано: '+str(biax.get('reason','нет полных нагрузок')))
    # Only the actual Belarus Annex L criterion belongs in current reports.
    annex=calc.get('annex_l') or {}
    add_heading(doc,'Хрупкое разрушение бетона — приложение Л СП 2.02.05-2026',2)
    add_equation(doc,'', ['F = (αF·αbt·β·Ec·ρ0·Wэ)/(K1c·λк·np)'])
    add_text(doc,'Источник: СП 2.02.05-2026, приложение Л, Л.1–Л.6, таблицы Л.1–Л.2. '
             'Плотность, заполнители, Ec и теплофизические свойства взяты из '
             'единого набора исходных данных материала.')
    if annex.get('status')=='calculated_method_scope':
        val=annex['F']
        label=('F ≤ 4: хрупкое разрушение по критерию не прогнозируется.'
               if val<=4 else
               '4 < F ≤ 6: потенциально опасный интервал, защита требуется по Л.6.'
               if val<=6 else
               'F > 6: прогнозируется хрупкое разрушение, необходима защита по Л.6.')
        add_text(doc,'F = '+number(val,4)+'. '+label)
        if not annex.get('natural_sand_verified',True):
            add_text(doc,'ОГРАНИЧЕНИЕ: природный песок для таблицы Л.1 принят '
                'положительным по умолчанию только для диагностики; документально '
                'состав заполнителя не подтверждён. Нормативное применение F заблокировано.')
        moist=(annex.get('provenance') or {}).get('Wc','не определён')
        mass=(annex.get('coefficients') or {}).get('Wc_kg_kg')
        add_text(doc,'Влажность Wc: '+str(moist)+
            ('; '+number(mass,6)+' кг/кг.' if mass is not None else '.'))
        if not annex.get('moisture_method_qualified',True):
            add_text(doc,'ОГРАНИЧЕНИЕ: для влажности использована формула Л.5 с явно принятой '
                'интерпретацией процентов либо инженерная интерполяция таблицы Л.2. '
                'Нормативная квалификация этого способа не завершена. '
                'Результат F — только диагностический.')
        add_table(doc,['T, °C','αbt, 1/°C','λ, Вт/(м·°C)','F'],[
            (number(x['temperature_C'],1),
             number(x['alpha_bt_1_C'],9),
             number(x['lambda_W_mC'],5),number(x['F'],4))
            for x in annex['temperature_profile']])
        add_text(doc,'Для оценки показан максимум по точкам 200, 250, 300 °C. '
                 'Результат не является доказательством предела огнестойкости.')
    else:
        add_text(doc,'Оценка F по приложению Л не выполнена: '+
                 annex.get('reason','исходные данные отсутствуют')+
                 '. Неизвестные значения не подменялись допущениями.')
    add_text(doc,'Итог: нормативное заключение R90 по этому выпуску не формируется — '
             'экспериментальные проверки и методика оценки общей работы колонны не прошли '
             'полную нормативную квалификацию.',bold=True)

