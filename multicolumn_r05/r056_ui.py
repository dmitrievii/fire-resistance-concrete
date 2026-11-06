"""Streamlit R0.5.6 panels: user-input spalling, member and biaxial diagnostics."""
from __future__ import annotations

R056_SP468_RELEASE = "r056-sp468-20261105-hotfix1"
import pandas as pd
from multicolumn_r05.r056_engine import SPALLING_FIELDS, SPALLING_UNITS
from multicolumn_r05.project_model import update_spalling


from multicolumn_r05.sp468 import (
    AGGREGATES, B_CLASSES, CURING, ENUMS, INPUT_FIELDS,
    NUMERIC_RANGES, SOURCE as SP468_SOURCE,
)

SP468_LABELS = {
    'aggregate_type':'Вид заполнителя',
    'strength_class_B':'Класс бетона B по СП 468',
    'curing':'Способ твердения',
    'aggregate_pct':'Крупный заполнитель, % объёма',
    'dry_density_kg_m3':'Плотность сухого бетона, кг/м³',
    'cement_kg_m3':'Расход цемента, кг/м³',
    'water_cement_ratio':'Водоцементное отношение В/Ц',
    'design_relative_humidity_pct':'Расчётная относительная влажность воздуха, %',
    'max_aggregate_mm':'Наибольшая крупность заполнителя, мм',
    'aggregate_porosity_fraction':'Пористость керамзита, м³/м³',
    'aggregate_volume_fraction':'Объёмное содержание керамзита, м³/м³',
}


def render_spalling_inputs(st, project, column, safe_change):
    cid=column['id'];stored=column.get('spalling') or {}
    is_manual=stored.get('method')=='manual_k18' or (
        not stored.get('method') and any(k in stored for k in SPALLING_FIELDS))
    with st.expander('Хрупкое разрушение бетона — проверка F',expanded=False):
        st.caption('СП 468.1325800.2019 (изм. №1, 2023): таблицы 9.1–9.6, формула 9.1. '
                   'Вводится состав и влажность бетона, остальные коэффициенты вычисляются. '
                   'Это справочная российская методика, а не подтверждение белорусского ТКП или R90.')
        method=st.radio('Метод проверки',('sp468','manual_k18'),
            index=1 if is_manual else 0,
            format_func=lambda x:('СП 468 — коэффициенты по таблицам' if x=='sp468'
                                  else 'К18 — вручную заданные коэффициенты'),
            key=f'r056_spall_method_{cid}')
        with st.form(key=f'r056_spall_{cid}_{method}_rev{project["revision"]}'):
            values={'method':method}
            if method=='sp468':
                st.info('Класс B здесь не определяется автоматически из C30/37: задайте его '
                        'по документации бетонной смеси. Поля без данных не заменяются допущениями.')
                c1,c2,c3=st.columns(3)
                for i,k in enumerate(INPUT_FIELDS[:9]):
                    with (c1,c2,c3)[i%3]:
                        v=stored.get(k)
                        if k in ENUMS:
                            choices=[None]+list(ENUMS[k])
                            values[k]=st.selectbox(SP468_LABELS[k],choices,
                                index=choices.index(v) if v in choices else 0,
                                format_func=lambda x: '— укажите —' if x is None else ENUMS[k][x],
                                key=f'{cid}_{k}_sp468_{project["revision"]}')
                        else:
                            label=SP468_LABELS[k]
                            a,b=NUMERIC_RANGES[k]
                            values[k]=st.text_input(label,value='' if v is None else f'{float(v):g}',
                                help=f'Допустимый диапазон без экстраполяции: {a:g}–{b:g}',
                                key=f'{cid}_{k}_sp468_{project["revision"]}')
                if values.get('aggregate_type')=='expanded_clay':
                    st.caption('Для пористого заполнителя нужны также свойства керамзита по (9.4) и (9.6).')
                    for i,k in enumerate(INPUT_FIELDS[9:]):
                        with (c1,c2,c3)[i%3]:
                            v=stored.get(k)
                            values[k]=st.text_input(SP468_LABELS[k],value='' if v is None else f'{float(v):g}',
                                key=f'{cid}_{k}_sp468_{project["revision"]}')
                st.caption('Содержание крупного заполнителя 40–60%: предел таблицы 9.3; '
                           'для иных значений теплопроводность не экстраполируется. '
                           'Таблица 9.5 не содержит K′1 для известняковых песка и щебня.')
            else:
                st.warning('Ручная методика К18 требует всех девяти параметров. '
                           'В исправленной формуле λ входит в первой степени, '
                           'а введённая пористость % преобразуется в объёмную долю.')
                cols=st.columns(3)
                for i,k in enumerate(SPALLING_FIELDS):
                    with cols[i%3]:
                        v=stored.get(k)
                        values[k]=st.text_input(k,value='' if v is None else f'{float(v):g}',
                            help=SPALLING_UNITS.get(k,''))
            submitted=st.form_submit_button('Сохранить состав бетона / параметры F')
            if submitted:
                safe_change(update_spalling,project,cid,values)


def _ru_spall(calc):
    s=calc.get('spalling',{})
    stat=s.get('status','not_evaluated')
    src=s.get('source_type','')
    if stat=='not_evaluated':return 'Недостаточно данных для вычисления F'
    if stat=='invalid':return 'Недопустимые свойства бетона / коэффициенты'
    if src=='SP468_reference':
        if stat=='index_at_or_below_threshold':return 'СП 468: F ≤ 4 — низкий риск по индексу'
        if stat=='requires_structural_check':return 'СП 468: 4 < F < 6 — требуется проверка по п. 9.9'
        if stat=='protection_required':return 'СП 468: F ≥ 6 — требуются защитные мероприятия'
    if stat=='protection_required':return 'К18: F > 4 — требуется защита'
    if stat=='index_at_or_below_threshold':return 'К18: F ≤ 4 — критерий выполнен'
    return 'Статус F не определён'


def render_r056_results(st,calc):
    contract=calc.get('normative_preflight')
    if contract:
        st.caption('R0.6.0: ' + contract['status'] +
                   ' · нормативные контракты без квалифицированного ядра · ' +
                   contract['contract_sha256'][:12])
        with st.expander('Нормативный протокол R0.6.0 — ограничения и источники',expanded=False):
            st.write('СП 2.02.05-2026 + СП 5.03.01-2020; маршрут: '+
                     contract['route'])
            st.write('Это не нормативное подтверждение R90. Исторический Mathcad и '
                     'СП 468 остаются диагностическими источниками.')
            st.dataframe(pd.DataFrame([{
                'Код':x['code'],'Приоритет':x['severity'],
                'Ограничение':x['message'],'Источник':x['clause']
            } for x in contract['issues']]),hide_index=True,use_container_width=True)
    st.subheader('R0.5.6 — дополнительные расчётные проверки')
    st.caption('Общий конверт η и совместное N–Mx–My — диагностические. '
               'Индекс F может вычисляться по справочным таблицам СП 468 '
               'или по вручную введённым коэффициентам К18; не является подтверждением R90.')
    member=calc.get('member',{})
    if member.get('status')=='evaluated':
        st.markdown('**Устойчивость по всей колонне — общий Nmax и Ncr,min**')
        st.dataframe(pd.DataFrame([{
            'Ось':axis.upper(), 'Nmax, кН':member['Nmax_kN'],
            'Ncr,min, кН':v['Ncr_min_kN'],'η колонны':v['eta_member']
        } for axis,v in member['axes'].items()]),hide_index=True,use_container_width=True)
    elif member.get('status')=='instability_or_invalid':
        st.error('Общий расчётный конверт: Nmax ≥ Ncr,min или некорректная жёсткость.')
    else:
        st.info('Общий конверт устойчивости будет доступен после ввода усилий.')
    biax=calc.get('biaxial',{})
    if biax.get('sections'):
        st.markdown('**Совместное численное равновесие N–Mx–My**')
        st.dataframe(pd.DataFrame([{
            'Сечение':sid,'Статус':rec['status'],
            'Δ равновесия':rec.get('residual_norm'),
            'εc,max':rec.get('eps_c_max'),
            'Mx, кН·м':rec['Mx_demand_kNm'],'My, кН·м':rec['My_demand_kNm']
        } for sid,rec in biax['sections'].items()]),hide_index=True,use_container_width=True)
    else:
        st.info('Совместная проверка недоступна, пока не рассчитан общий конверт.')
    sp=calc.get('spalling',{})
    st.markdown('**Хрупкое разрушение бетона — критерий F**')
    st.write(_ru_spall(calc))
    st.caption(sp.get('method','') + (' · '+sp.get('source','') if sp.get('source') else ''))
    if sp.get('F') is not None:
        st.metric('F (СП 468: границы 4 и 6; К18: граница 4)',f'{sp["F"]:.4f}')
        if sp.get('coefficients'):
            st.dataframe(pd.DataFrame([{'Параметр':k,'Значение':float(v)}
                for k,v in sp['coefficients'].items()]),hide_index=True,use_container_width=True)
    elif sp.get('status')=='not_evaluated':
        st.caption('Отсутствуют или не табулированы: '+', '.join(sp.get('missing',[])))
    elif sp.get('status')=='invalid':
        st.error(sp.get('error','Некорректные параметры F'))
    st.caption('Данные F хранятся индивидуально для каждой колонны. '
               'Значения по СП 468 — российская справочная проверка, '
               'они не подменяют приложение К ТКП 45-2.02-110.')
    st.warning('R90 не подтверждено нормативно: наличие численного равновесия, '
               'достаточной жёсткости и F ≤ 4 само по себе не завершает '
               'нормативную проверку устойчивости, двухосного действия и теплового разрушения.')


def render_r056_overview(st,project,calculations):
    st.markdown('**Дополнительные проверки R0.5.6**')
    rows=[]
    for c in project['columns']:
        x=calculations[c['id']]
        b=x.get('biaxial',{})
        states=[v['status'] for v in b.get('sections',{}).values()]
        rows.append({'Колонна':c['name'],
                     'Общий конверт η':x.get('member',{}).get('status','—'),
                     'Совместное N–Mx–My':(', '.join(sorted(set(states))) if states else 'Не рассчитано'),
                     'Критерий F':_ru_spall(x),
                     'Нормативный контракт':x.get('normative_preflight',{}).get('status','НЕ ПРОВЕРЕНО'),
                     'Итоговое R90':'Не подтверждено'})
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)