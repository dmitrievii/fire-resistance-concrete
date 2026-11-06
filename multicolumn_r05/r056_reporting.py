"""Report appendix for R0.5.6. Keeps approved DOCX footer, stamp and frame intact."""
from multicolumn_r05.parametric_report import add_heading, add_text, add_table, add_equation, number
from rc_fire.thermal.report import add_thermal_section

def add_r056_diagnostics(doc,c,calc):
    """New section appended to all reports; does not rewrite the fixed frame/stamp."""
    add_thermal_section(doc,c,calc)
    add_heading(doc,'R0.5.6 — совместные и дополнительные диагностические проверки',2)
    add_text(doc,'Воспроизведение Mathcad K18 и параметрическая волоконная модель имеют разный методический статус. '
             'Ниже приведён вычислительный контроль, а не нормативное подтверждение предела R90.')
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
        add_text(doc,'Mathcad К18 воспроизводится исторически, СП 468 — только сравнение. '
                 'Ни один нормативный метод R0.6.0 ещё не прошёл численную квалификацию.')
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
    sp=calc.get('spalling',{})
    is_sp=sp.get('source_type')=='SP468_reference'
    add_heading(doc,'Хрупкое разрушение F — '+('СП 468, п. 9.7' if is_sp else 'ввод коэффициентов К18'),2)
    if is_sp:
        add_equation(doc,'', ['F = (a·αbt·Ebt·ρ·Wэ) / (K′1·λ·Π)'])
        add_text(doc,'Источник: СП 468.1325800.2019 (изм. № 1, 2023); таблицы 9.1–9.6; '
                 'Π, Wэ вводятся в формулу как объёмные доли. Бетонный класс B задаётся отдельно. '
                 'Нормативная применимость в Республике Беларусь не установлена.')
    else:
        add_equation(doc,'', ['F = (αF·αbt·β·Ec·ρ·Wэ) / (K1C·λ·(np/100))'])
        add_text(doc,'Ручные коэффициенты исходного К18: λ в первой степени; np введён в % и переводится в долю.')
    if sp.get('status')=='not_evaluated':
        add_text(doc,'Расчёт F не выполнен: отсутствуют либо не табулированы параметры '+
                 ', '.join(sp.get('missing',[]))+'. Отсутствующие значения не заменялись нулём.')
    elif sp.get('status')=='invalid':
        add_text(doc,'Исходные данные F некорректны: '+sp.get('error','неизвестная ошибка'))
    else:
        classification=({'index_at_or_below_threshold':'F ≤ 4: низкий риск по критерию СП 468.',
                         'requires_structural_check':'4 < F < 6: требуется дополнительная проверка по п. 9.9 СП 468.',
                         'protection_required':'F ≥ 6: требуются защитные мероприятия по СП 468.'}
                        if is_sp else
                        {'index_at_or_below_threshold':'F ≤ 4: критерий К18 выполнен.',
                         'protection_required':'F > 4: согласно К18 нужны меры защиты.'})
        add_text(doc,'F = '+number(sp.get('F'),4)+'. '+classification.get(sp.get('status'),'Неизвестный статус.'))
        if is_sp and sp.get('coefficients'):
            add_table(doc,['Величина (СП 468)','Автоматически определённое значение'],[
                (key, f'{float(val):.7g}') for key,val in sp['coefficients'].items()])
            add_text(doc,'Табличные значения допускают только указанную интерполяцию; '
                     'расчёт выполнен по составу бетона и условиям эксплуатации, введённым пользователем.')
    add_text(doc,'Итог: нормативное заключение R90 по этому выпуску не формируется — '
             'экспериментальные проверки и методика оценки общей работы колонны не прошли '
             'полную нормативную квалификацию.',bold=True)

