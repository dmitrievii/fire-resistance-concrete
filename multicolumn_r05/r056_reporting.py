"""Report appendix for R0.5.6. Keeps approved DOCX footer, stamp and frame intact."""
from multicolumn_r05.parametric_report import add_heading, add_text, add_table, add_equation, number

def add_r056_diagnostics(doc,c,calc):
    """New section appended to all reports; does not rewrite the fixed frame/stamp."""
    add_heading(doc,'R0.5.6 — совместные и дополнительные диагностические проверки',2)
    add_text(doc,'Воспроизведение Mathcad K18 и параметрическая волоконная модель имеют разный методический статус. '
             'Ниже приведён вычислительный контроль, а не нормативное подтверждение предела R90.')
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
    add_heading(doc,'Критерий хрупкого разрушения F — отчёт К18, формула (3.4.1)',2)
    add_equation(doc,'', ['F = (αF·αbt·β·Ec·ρ·Wэ) / (K1C·λ²·np)'])
    if sp.get('status')=='not_evaluated':
        add_text(doc,'Расчёт F не выполнен: отсутствуют обязательные исходные параметры '+
                 ', '.join(sp.get('missing',[]))+'. Ни один параметр не принят равным нулю по умолчанию.')
    elif sp.get('status')=='invalid':
        add_text(doc,'Исходные данные критерия F некорректны: '+sp.get('error','неизвестная ошибка'))
    else:
        add_text(doc,'F = '+number(sp.get('F'),4)+' (порог 4,0). '+
             ('F > 4: согласно тексту эталонного отчёта требуется защита от хрупкого разрушения.'
              if sp.get('status')=='protection_required' else
              'F ≤ 4: условие критерия по введённым значениям выполнено; иные проверки остаются необходимыми.'))
    add_text(doc,'Итог: нормативное заключение R90 по этому выпуску не формируется — '
             'экспериментальные проверки и методика оценки общей работы колонны не прошли '
             'полную нормативную квалификацию.',bold=True)

