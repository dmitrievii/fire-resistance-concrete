"""Opt-in Streamlit entrypoint; by default new solver does no heavy computation."""
from __future__ import annotations
import json
from .r064d import (sample_station_bundle, evaluate_explicit_member_bundle,
                    MemberEvidenceInputError, _signature)


def render_member_evidence(st, column, existing_result, *,
                           project=None, safe_change=None, update_member_spec=None):
    from .r067 import (build_uniform_fire_bundle, evaluate_uniform_fire_member,
                       validate_member_spec)
    with st.expander('R0.6.7 · Нагретая колонна: автоматическое сопряжение (не R90)',expanded=False):
        st.caption('R0.6.7: температурные поля для всех узлов и точек Гаусса '
                   'можно построить по приложению К при явном допущении '
                   'одинакового нагрева вдоль колонны. При неоднородном нагреве '
                   'используйте независимые станции через JSON. '
                   'Все результаты — только диагностические.')
        st.info('По условиям проекта все N, Mx, My в расчётных сечениях '
                'уже являются расчётными усилиями для пожарной ситуации. '
                'Повторное формирование пожарного сочетания не требуется.')
        spec=validate_member_spec(column.get('member_spec'))
        if project is not None and update_member_spec is not None and safe_change is not None:
            sid=column.get('id','column')
            with st.form(f"r067_member_inputs_{sid}_{project['revision']}"):
                modes=('explicit_only','uniform_assumed')
                mode=st.selectbox('Температура по длине',
                    modes,index=modes.index(spec.get('thermal_longitudinal_mode','explicit_only')),
                    format_func=lambda x:('Независимые температурные станции (JSON)'
                        if x=='explicit_only' else 'Одинаковый нагрев всех сечений (допущение пользователя)'))
                note=st.text_input('Обоснование одинакового нагрева по длине',
                    value=spec.get('uniform_fire_basis') or '',
                    help='Например, одинаковое огневое воздействие и условия теплообмена по всей длине')
                c1,c2=st.columns(2)
                supports=('', 'pinned','fixed','guided')
                with c1:
                    left=st.selectbox('Нижняя опора',supports,
                        index=supports.index(spec.get('left_support') or ''),
                        format_func=lambda x: {'':'— не задана —',
                            'pinned':'Шарнир','fixed':'Защемление','guided':'Направляющая'}[x])
                with c2:
                    right=st.selectbox('Верхняя опора',supports,
                        index=supports.index(spec.get('right_support') or ''),
                        format_func=lambda x: {'':'— не задана —',
                            'pinned':'Шарнир','fixed':'Защемление','guided':'Направляющая'}[x])
                support_src=st.text_input('Обоснование опор (проект, схема закрепления)',
                    value=spec.get('support_provenance') or '')
                choices=('not_defined','axial_only','uniform_transverse_load')
                load_mode=st.selectbox('Расчётная схема поперечной нагрузки',
                    choices,index=choices.index(spec.get('load_mode','not_defined')),
                    format_func=lambda x: {'not_defined':'— не задана —',
                        'axial_only':'Подтверждённое осевое нагружение (Mx=My=0)',
                        'uniform_transverse_load':'Заданная равномерная нагрузка qx, qy'}[x])
                q1,q2=st.columns(2)
                with q1:
                    qx=st.number_input('qx, кН/м (ось X)',
                        value=float(spec.get('q_x_kNpm') or 0.0),step=0.1)
                with q2:
                    qy=st.number_input('qy, кН/м (ось Y)',
                        value=float(spec.get('q_y_kNpm') or 0.0),step=0.1)
                nodes=st.number_input('Расчётные узлы по длине',
                    value=int(spec.get('node_count',3)),min_value=2,max_value=21,step=1)
                if st.form_submit_button('Сохранить схему нагрева, опирания и нагрузок'):
                    payload={'thermal_longitudinal_mode':mode,
                        'uniform_fire_basis':note.strip() or None,
                        'left_support':left or None,'right_support':right or None,
                        'support_provenance':support_src.strip() or None,
                        'load_mode':load_mode,
                        'q_x_kNpm':float(qx) if load_mode=='uniform_transverse_load' else None,
                        'q_y_kNpm':float(qy) if load_mode=='uniform_transverse_load' else None,
                        'node_count':int(nodes)}
                    safe_change(update_member_spec,project,sid,payload)
        if spec.get('thermal_longitudinal_mode')=='uniform_assumed':
            try:
                bundle=build_uniform_fire_bundle(column,
                    thermal=existing_result.get('thermal_normative'))
            except MemberEvidenceInputError as exc:
                st.info('Автоматическое сопряжение пока недоступно: '+str(exc))
            else:
                st.caption('Подготовлены '+str(len(bundle['node_stations']))+
                    ' узловых и '+str(3*len(bundle['gauss_stations']))+
                    ' гауссовых температурных станций из одного аналитического '
                    'профиля с явной записью допущения об одинаковом нагреве по длине.')
                st.download_button('Скачать полный диагностический JSON R0.6.7',
                    json.dumps(bundle,ensure_ascii=False,indent=2),
                    file_name=f"{column.get('id','column')}_r067_uniform.json",
                    mime='application/json',key=f"r067_download_{column.get('id','c')}")
                if st.button('Вычислить R0.6.7: сопряжённая механика (не R90)',
                             key=f"r067_run_{column.get('id','c')}"):
                    with st.spinner('Проверка температур, материалов и равновесия колонны'):
                        result=evaluate_uniform_fire_member(column,
                            thermal=existing_result.get('thermal_normative'))
                    st.session_state[f"r064d_result_{column.get('id','c')}"]={
                        'result':result,'signature':_signature(column)}
                st.divider()
                st.caption('R0.6.9A · История нагрева и предельных деформаций по времени. '
                           'Это численная диагностика, а не нормативный предел R(t). '
                           'Точки с температурой вне диапазона таблиц или отсутствием '
                           'сходимости обозначаются как неопределённые, а не как отказ.')
                step=st.number_input('Шаг временного сканирования, мин',
                    min_value=1.0,max_value=120.0,value=10.0,step=1.0,
                    key=f"r069_step_{column.get('id','c')}",
                    help='Каждая точка: новый расчёт поля приложения К и пространственной механики. '
                         'Расчёт начинается с 1 мин (аналитическая модель не применяется при t=0).')
                if st.button('Рассчитать историю R(t) — только диагностика',
                             key=f"r069_run_{column.get('id','c')}"):
                    from .r069 import evaluate_uniform_fire_time_history
                    try:
                        with st.spinner('Повторный расчёт температур и ULS на каждом временном шаге'):
                            history=evaluate_uniform_fire_time_history(
                                column,step_minutes=float(step))
                        st.session_state[f"r069_result_{column.get('id','c')}"]={
                            'result':history,'signature':_signature(column)}
                    except (MemberEvidenceInputError,ValueError,TypeError) as exc:
                        st.error('R0.6.9A: '+str(exc))
                history_cache=st.session_state.get(f"r069_result_{column.get('id','c')}")
                if history_cache is not None and history_cache.get('signature') != _signature(column):
                    st.session_state.pop(f"r069_result_{column.get('id','c')}",None)
                    history_cache=None
                if history_cache is not None:
                    history=history_cache['result']
                    st.write('Диагностический статус истории:',history['status'])
                    st.dataframe(history['samples'],use_container_width=True,hide_index=True)
                    st.json({'R_t_minutes':None,
                             'observed_transition_brackets_minutes':history['observed_transition_brackets_minutes'],
                             'unresolved_times_minutes':history['unresolved_times_minutes'],
                             'normative_claim':False,
                             'fire_resistance_status':'not_demonstrated'})
                    st.download_button('Скачать диагностику R0.6.9A (JSON)',
                        json.dumps(history,ensure_ascii=False,indent=2),
                        file_name=f"{column.get('id','column')}_r069_time_history.json",
                        mime='application/json',key=f"r069_download_{column.get('id','c')}")
        else:
            st.info('Автоматический перенос температур выключен. '
                'Для неоднородного обогрева требуется полный независимый JSON.')
        st.divider()
        st.caption('R0.6.4D: ручной импорт независимых продольных температурных полей '
                   'остаётся доступным ниже.')
        st.json({'status': existing_result.get('member_r064d',{}).get('status','NOT_EVALUATED'),
                 'normative_claim': False,'fire_resistance_status':'not_demonstrated'})
        sample=sample_station_bundle(column,node_count=3)
        actions=sample.get('section_actions_reference_only',[])
        ready=sum(a['load_state']=='ready' for a in actions)
        n=sample.get('N_kN')
        st.caption(f'Расчётные усилия при пожаре из общей таблицы: {ready}/{len(actions)} сечений заполнено. '
                   + (f'Постоянная N={n:g} кН перенесена в шаблон. ' if n is not None
                      else 'Постоянная N не определена для всей колонны. ')
                   + 'Mx/My сохранены как пожарные расчётные усилия, но не преобразуются '
                     'автоматически в распределённую нагрузку. Тепловые станции '
                     'и условия закрепления должны быть заданы отдельно.')
        st.download_button('Шаблон входных данных R0.6.4D (неполный)',
                           json.dumps(sample,ensure_ascii=False,indent=2),
                           file_name=f"{column.get('id','column')}_member_stations_template.json",
                           mime='application/json',key=f"r064d_template_{column.get('id','c')}")
        supplied=st.file_uploader('Загрузить полный набор температурных сечений и нагрузок (JSON)',
                   type=['json'],key=f"r064d_input_{column.get('id','c')}")
        if supplied is not None and st.button('Вычислить диагностическую ULS-проверку',
                                             key=f"r064d_run_{column.get('id','c')}"):
            try:
                data=json.loads(supplied.getvalue().decode('utf-8'))
                result=evaluate_explicit_member_bundle(data, expected_column=column)
                st.session_state[f"r064d_result_{column.get('id','c')}"]={'result':result,'signature':_signature(column)}
            except (MemberEvidenceInputError,ValueError,TypeError,KeyError) as exc:
                st.error(f'R0.6.4D: данные не приняты: {exc}')
        cached=st.session_state.get(f"r064d_result_{column.get('id','c')}")
        if cached is not None and cached.get('signature') != _signature(column):
            st.session_state.pop(f"r064d_result_{column.get('id','c')}",None)
            cached=None
        result=cached['result'] if cached is not None else None
        if result is not None:
            st.warning('Только диагностика; положительное нормативное заключение R90 запрещено.')
            st.write('Численный статус:',result['status'])
            st.json({'normative_claim':False,
                     'fire_resistance_status':'not_demonstrated',
                     'blockers':result.get('uls',{}).get('blockers',result.get('blockers',[]))})

    with st.expander('R0.6.9B · Критическая изотерма §8.2.21 (не нормативный R(t))',expanded=False):
        st.caption('Аналитическая площадь остаточного сечения — по формуле К.27, '
                   'только для квадратной колонны с четырёхсторонним нагревом. '
                   'Применимость в расчёте прочности отдельно проверяется по §8.2.21: '
                   'одноосный изгиб в плоскости симметрии и две симметричные крайние '
                   'арматурные зоны. Произвольный двухосный изгиб не допускается.')
        from rc_fire.mechanics.critical_isotherm import (
            evaluate_critical_isotherm_section, evaluate_critical_isotherm_history)
        colid=column.get('id','c')
        if st.button('Проверить изотерму и область применения',
                     key=f"r069b_now_{colid}"):
            result=evaluate_critical_isotherm_section(column,grid=40)
            st.session_state[f"r069b_now_cache_{colid}"]={'result':result,'signature':_signature(column)}
        cached_now=st.session_state.get(f"r069b_now_cache_{colid}")
        if cached_now is not None and cached_now.get('signature') != _signature(column):
            st.session_state.pop(f"r069b_now_cache_{colid}",None)
            cached_now=None
        if cached_now is not None:
            result=cached_now['result']
            st.write('Статус:',result['status'])
            st.write('Площадь по К.27, м²:',result['remaining_area_m2'])
            if result.get('N_optimistic_upper_kN') is not None:
                st.write('Только оптимистичная верхняя оценка осевой силы, кН:',
                         result['N_optimistic_upper_kN'])
                st.warning('Это НЕ N_Rd и НЕ проверка N–Mx–My. '
                           'Превышение верхней оценки является диагностическим '
                           'нарушением необходимого условия, но отсутствие '
                           'превышения НЕ подтверждает несущую способность.')
            if result.get('blockers'):
                st.warning('Неподтверждённые условия: '+', '.join(result['blockers']))
            st.download_button('Скачать проверку изотермы (JSON)',
                json.dumps(result,ensure_ascii=False,indent=2),
                file_name=f'{colid}_r069b_isotherm.json',
                mime='application/json',key=f"r069b_json_{colid}")
        st.divider()
        step=st.number_input('Шаг проверки изотермы во времени, мин',
            min_value=1.,max_value=120.,value=10.,step=1.,
            help='На каждом шаге повторно считается температура по приложению К; '
                 'нормативное время отказа не выдаётся.',
            key=f"r069b_step_{colid}")
        if st.button('Построить временную историю остаточной площади (диагностика)',
                     key=f"r069b_scan_{colid}"):
            try:
                with st.spinner('Пересчёт приложения К на каждом временном шаге'):
                    scan=evaluate_critical_isotherm_history(column,step_minutes=float(step),grid=40)
                st.session_state[f"r069b_scan_result_{colid}"]={
                    'result':scan,'signature':_signature(column)}
            except (ValueError,TypeError) as exc:
                st.error(f'R0.6.9B: {exc}')
        cached_scan=st.session_state.get(f"r069b_scan_result_{colid}")
        if cached_scan is not None and cached_scan.get('signature') != _signature(column):
            st.session_state.pop(f"r069b_scan_result_{colid}",None)
            cached_scan=None
        if cached_scan is not None:
            scan=cached_scan['result']
            st.dataframe(scan['samples'],use_container_width=True,hide_index=True)
            st.caption('R(t) не установлен: флаг normative_claim=False. '
                       'Отсутствие численного превышения верхнего осевого предела '
                       'не означает соответствие R90.')
            st.download_button('Скачать историю критической изотермы (JSON)',
                json.dumps(scan,ensure_ascii=False,indent=2),
                file_name=f'{colid}_r069b_history.json',
                mime='application/json',key=f"r069b_history_json_{colid}")

    with st.expander('R0.6.9C · Запас по N–Mx–My и пространственной колонне во времени (диагностика)',expanded=False):
        st.caption('Два независимых расчёта: (1) все введённые N, Mx, My '
                   'масштабируются без пересчёта пожарных сочетаний и проверяются '
                   'на нелинейном волокнистом сечении; (2) по выбору — расчёт '
                   'пространственной колонны по явно заданным N, qx, qy и опорам '
                   'с P–Δ и собственными температурными деформациями. '
                   'Введённые Mx/My НЕ преобразуются в q и НЕ считаются '
                   'проверенными в пространственной схеме автоматически.')
        st.warning('Это численный запас на фиксированной траектории нагрузок, '
                   'а не нормативная несущая способность. Несходимость, '
                   'неполные сведения и нагрев выше 800 °C = неопределённость, '
                   'НЕ разрушение. Положительное заключение R90 запрещено.')
        cid=column.get('id','c')
        tm=st.number_input('Шаг сканирования времени, мин (R0.6.9C)',
            min_value=1.,max_value=120.,value=30.,step=1.,
            key=f'r069c_time_step_{cid}',
            help='Каждый момент: независимая температура, N–Mx–My и при выборе '
                 'отдельная пространственная модель. Не более 12 временных точек.')
        inc=st.checkbox('Дополнительно считать пространственную колонну по явно заданным N и q',
            value=False,key=f'r069c_member_enabled_{cid}',
            help='Только если в R0.6.7 уже определены нагрев вдоль длины, '
                 'опирание и нагрузка. Заметно увеличивает время вычисления.')
        if st.button('Рассчитать диаграмму запаса во времени R0.6.9C',
                     key=f'r069c_run_{cid}'):
            from .r069c import evaluate_fire_action_capacity_history
            try:
                with st.spinner('Независимый расчёт температур и двухосной прочности на каждом шаге'):
                    outcome=evaluate_fire_action_capacity_history(
                        column,step_minutes=float(tm),factor_step=.5,
                        max_factor=2.,max_bisection=4,grid=12,
                        include_member=bool(inc))
                st.session_state[f'r069c_cache_{cid}']={
                    'result':outcome,'signature':_signature(column),
                    'settings':(float(tm),bool(inc))}
            except (ValueError,MemberEvidenceInputError,TypeError) as exc:
                st.error('R0.6.9C: '+str(exc))
        cached_c=st.session_state.get(f'r069c_cache_{cid}')
        if (not isinstance(cached_c,dict) or
            cached_c.get('signature')!=_signature(column) or
            cached_c.get('settings')!=(float(tm),bool(inc))):
            st.session_state.pop(f'r069c_cache_{cid}',None)
            cached_c=None
        if cached_c is not None:
            outcome=cached_c['result']
            st.write('Статус:',outcome['status'])
            st.dataframe([{
                't, мин':s['time_minutes'],
                'Расчёт сечений':s['section_classification_at_lambda_1'],
                'Расчёт колонны':s['member_classification_at_lambda_1'],
                'T_max, °C':s['temperature_max_C'],
                'T_s,max, °C':s['steel_temperature_max_C'],
                'Площадь К.27, м²':s['K27_area_m2_geometry_only'],
                'Причина':s.get('reason')}
                for s in outcome['samples']],use_container_width=True,hide_index=True)
            st.caption('При неизменных введённых пожарных усилиях λ=1 — '
                       'расчётная точка. Наблюдаемые интервалы λ между '
                       'равновесными состояниями не являются нормативной N_Rd или R(t). '
                       'Для R(t) нужна квалификация полной расчётной модели.')
            st.json({'R_t_minutes':outcome['R_t_minutes'],
                     'normative_claim':outcome['normative_claim'],
                     'sampled_time_transition_brackets':
                         outcome['observed_section_reference_transitions_minutes'],
                     'unresolved_times_minutes':outcome['unresolved_times_minutes']})
            st.download_button('Скачать полный аудит R0.6.9C (JSON)',
                json.dumps(outcome,ensure_ascii=False,indent=2),
                file_name=f'{cid}_r069c_capacity_history.json',
                mime='application/json',key=f'r069c_download_{cid}')

    with st.expander('R0.6.9D2 · ТКП EN 1992-1-2 — нелинейное сечение и колонна (диагностика)',
                     expanded=False):
        st.caption('Материалы: ТКП EN 1992-1-2-2009 с белорусским национальным '
                   'приложением. Нагрев пока по приложению К СП 2.02.05-2026 '
                   '(смешанная, ещё не квалифицированная методика). '
                   'Никаких повторных пожарных сочетаний N, Mx, My.')
        cid=column.get('id','c')
        route=st.selectbox('Способ изготовления продольной арматуры S500',
             ('Не установлен','hot_rolled','cold_worked'),
             key=f'r069d2_route_{cid}',
             help='Горячекатаная или холоднодеформированная. '
                  'По одной маркировке S500 выбор запрещён.')
        duct=st.selectbox('Класс пластичности арматуры',
             ('Не установлен','A','B','C'),key=f'r069d2_ductility_{cid}',
             help='Требуется установленный класс A, B или C, не выводится из S500.')
        allow_tail=st.checkbox(
            'Только для исследования: обнулить бетон 1100–1200 °C',
            value=False,key=f'r069d2_hot_tail_{cid}',
            help='В таблице 3.1 отсутствуют деформации при 1200 °C. '
                 'Этот режим НЕ подтверждает нормативную прочность.')
        include_beam=st.checkbox(
            'Дополнительно: пространственная колонна только при явно определённых N и q',
            value=False,key=f'r069d2_member_{cid}',
            help='Нужны схема закрепления и распределённые нагрузки из R0.6.7. '
                 'Моменты из отдельного сечения не преобразуются в q.')
        time_step=st.number_input('Шаг времени для ТКП, мин',
            min_value=1.,max_value=120.,value=30.,step=1.,
            key=f'r069d2_tstep_{cid}')
        st.warning('Результаты механики — диагностические. '
                   'Незаданная технология арматуры, неполная диаграмма бетона '
                   'при 1100–1200 °C и отсутствие достоверной схемы колонны '
                   'не заменяются предположениями. Время R(t) пока не установлено.')
        settings=(route,duct,bool(allow_tail),bool(include_beam),float(time_step))
        if st.button('Проверить нагретое сечение по ТКП в заданный момент',
                     key=f'r069d2_now_btn_{cid}'):
            from .r069d2 import evaluate_tkp_fire_mechanics_at_time
            with st.spinner('Нелинейные волокна ТКП и температурные собственные деформации'):
                d=evaluate_tkp_fire_mechanics_at_time(
                    column,production_route=None if route=='Не установлен' else route,
                    ductility_class=None if duct=='Не установлен' else duct,
                    high_temperature_tail='zero_tail_diagnostic' if allow_tail else 'reject',
                    grid=12,max_factor=1.,factor_step=1.,max_bisection=0,
                    include_member=bool(include_beam))
            st.session_state[f'r069d2_now_cache_{cid}']={
                'signature':_signature(column),'settings':settings,'result':d}
        if st.button('Построить историю деформаций по ТКП',
                     key=f'r069d2_history_btn_{cid}'):
            from .r069d2 import evaluate_tkp_fire_mechanics_history
            try:
                with st.spinner('Независимые расчёты температуры и механики по времени'):
                    d=evaluate_tkp_fire_mechanics_history(
                        column,production_route=None if route=='Не установлен' else route,
                        ductility_class=None if duct=='Не установлен' else duct,
                        high_temperature_tail='zero_tail_diagnostic' if allow_tail else 'reject',
                        step_minutes=float(time_step),grid=12,
                        include_member=bool(include_beam))
                st.session_state[f'r069d2_history_cache_{cid}']={
                    'signature':_signature(column),'settings':settings,'result':d}
            except (ValueError,TypeError,KeyError) as exc:
                st.error('ТКП, история: '+str(exc))
        for kind in ('now','history'):
            cache=st.session_state.get(f'r069d2_{kind}_cache_{cid}')
            if (cache is None or cache.get('signature')!=_signature(column) or
                cache.get('settings')!=settings):
                st.session_state.pop(f'r069d2_{kind}_cache_{cid}',None)
                continue
            result=cache['result']
            st.write('Расчёт ТКП ('+('один момент' if kind=='now' else 'история')+'):',
                     result.get('status'))
            if kind=='now':
                st.write('Температура у арматуры, °C:',
                         result.get('bar_temperatures_C'))
                st.write('Максимум на границе бетона, °C:',
                         result.get('boundary_temperature_max_C'))
                if result.get('reason'):st.warning(result['reason'])
                if result.get('sections'):
                    st.dataframe([{
                        'Сечение':s['id'],
                        'N, кН':s['entered_fire_design_actions']['N_kN'],
                        'Mx, кНм':s['entered_fire_design_actions']['Mx_kNm'],
                        'My, кНм':s['entered_fire_design_actions']['My_kNm'],
                        'Состояние':s['reference_at_lambda_1']['classification'],
                        'Численная причина':s['reference_at_lambda_1'].get('reason')}
                        for s in result['sections']],hide_index=True,use_container_width=True)
            else:
                st.dataframe([{
                    't, мин':s['time_minutes'],
                    'Статус':s['status'],
                    'N+M':s['reference_classification'],
                    'T поверхности, °C':s.get('hot_boundary_C'),
                    'Модель колонны':s.get('member_status'),
                    'Причина':s.get('reason')}
                    for s in result['samples']],hide_index=True,use_container_width=True)
            st.caption('R(t) = не установлен. Нельзя утверждать R90 по этому '
                       'предварительному численному решению.')
            st.download_button('Скачать аудит ТКП '+kind+' (JSON)',
                json.dumps(result,ensure_ascii=False,indent=2,default=str),
                file_name=f'{cid}_r069d2_{kind}.json',
                mime='application/json',key=f'r069d2_dl_{kind}_{cid}')

    with st.expander('R0.6.9D3 · ТКП: 2D нестационарный прогрев → волокна → N–Mx–My',
                     expanded=False):
        st.caption('Расчёт прогрева теперь независим от аналитического температурного '
                   'поля приложения К: конечно-объёмное решение уравнения '
                   'теплопроводности с нижней теплопроводностью ТКП, '
                   'теплоёмкостью и плотностью по температуре, конвекцией и '
                   'излучением. Используется явно выбранный опорный режим '
                   'приложения А (h=25 Вт/(м²·К), ε=0,7) и стандартная '
                   'газовая кривая по формуле (3) СП 2.02.05-2026.')
        cid=column.get('id','c')
        moisture=st.number_input('Начальная массовая влажность бетона, % (ТКП)',
            min_value=0.,max_value=3.,value=1.5,step=.1,
            help='1,5% — исходное условие температурных графиков приложения А. '
                 'Это НЕ оценка влажности по относительной влажности воздуха '
                 'из приложения Л. Подтвердите фактическое значение.',
            key=f'r069d3_water_{cid}')
        mesh=st.selectbox('Сетка теплопроводности по каждой оси',options=(8,12,16),
            index=1,key=f'r069d3_mesh_{cid}')
        maxdt=st.number_input('Максимальный шаг теплопроводности, мин',
            min_value=.5,max_value=10.,value=5.,step=.5,
            key=f'r069d3_dt_{cid}')
        timestep=st.number_input('Шаг вывода механики во времени, мин',
            min_value=1.,max_value=120.,value=30.,step=1.,
            key=f'r069d3_time_{cid}')
        sr=st.selectbox('Фактическая технология арматуры S500 (D3)',
            ('Не установлена','hot_rolled','cold_worked'),
            key=f'r069d3_steel_{cid}',
            help='Не выводится автоматически из марки S500.')
        sd=st.selectbox('Класс пластичности S500 (D3)',
            ('Не установлен','A','B','C'),key=f'r069d3_duct_{cid}')
        member3=st.checkbox('Дополнительно рассчитать пространственную колонну P–Δ',
            value=False,key=f'r069d3_member_{cid}',
            help='Только при явно заданных N, qx, qy, опорах и принятом '
                 'одинаковом прогреве вдоль длины. Моменты не конвертируются в q.')
        refine_t=st.checkbox('Уточнять первый наблюдаемый переход предельной деформации',
            value=False,key=f'r069d4_refine_{cid}',
            help='Повторный интегральный прогрев от исходного состояния '
                 'для каждого уточняемого времени. Только диагностический '
                 'интервал; не определяет нормативное R(t).')
        st.warning('Опорный тепловой расчёт ещё требует проверки по EN 1991-1-2, '
                   'экспериментам и сеточной сходимости. Статус R(t) остаётся '
                   '«не установлен». Выбор процента влажности здесь — '
                   'исходный параметр сценария, а не измеренное значение.')
        settings=(float(moisture),int(mesh),float(maxdt),float(timestep),
                  sr,sd,bool(member3),bool(refine_t))
        cache_key=f'r069d3_cache_{cid}'
        if st.button('Выполнить полный тепловой и механический расчёт D3',
                     key=f'r069d3_run_{cid}'):
            from rc_fire.thermal.tkp_heat import reference_annex_a_boundary
            from .r069d3 import evaluate_tkp_thermal_mechanical_history
            try:
                bound=reference_annex_a_boundary(moisture_mass_pct=float(moisture))
                with st.spinner('2D температура, баланс энергии и независимое N–Mx–My'):
                    r=evaluate_tkp_thermal_mechanical_history(
                        column,boundary=bound,cell_count=int(mesh),
                        max_step_minutes=float(maxdt),step_minutes=float(timestep),
                        production_route=None if sr=='Не установлена' else sr,
                        ductility_class=None if sd=='Не установлен' else sd,
                        max_factor=1.,factor_step=1.,max_bisection=0,
                        include_member=bool(member3),
                        refine_strain_transition=bool(refine_t),
                        max_time_refinements=4)
                st.session_state[cache_key]={
                    'result':r,'signature':_signature(column),'settings':settings}
            except (ValueError,TypeError,ArithmeticError) as exc:
                st.error('D3: '+str(exc))
        result_cache=st.session_state.get(cache_key)
        if (not isinstance(result_cache,dict) or
            result_cache.get('signature')!=_signature(column) or
            result_cache.get('settings')!=settings):
            st.session_state.pop(cache_key,None)
            result_cache=None
        if result_cache is not None:
            out=result_cache['result']
            st.write('Статус:',out['status'])
            st.write('Относительная невязка теплового баланса:',
                out['thermal_energy_balance']['relative_cumulative_residual'])
            st.dataframe([{
                't, мин':s['time_minutes'],
                'Температура газа, °C':s['T_gas_C'],
                'Макс. бетон, °C':s['T_concrete_boundary_max_C'],
                'Центр бетона, °C':s['T_concrete_center_C'],
                'Нелинейное N–Mx–My':s['reference_classification'],
                'Статус':s['status'],
                'Пространственная модель':(
                    (s.get('member') or {}).get('status'))
            } for s in out['samples']],use_container_width=True,hide_index=True)
            strain=out.get('observed_section_strain_transition') or {}
            if strain.get('observed_within_to_exceeded_intervals'):
                st.write('Наблюдаемые интервалы превышения деформаций сечения:',
                         strain['observed_within_to_exceeded_intervals'])
            if strain.get('refined_first_diagnostic_interval'):
                st.write('Уточнённый диагностический интервал:',
                         strain['refined_first_diagnostic_interval'])
            if strain.get('unknown_time_points_minutes'):
                st.warning('Неопределённые состояния при t, мин: '
                           +str(strain['unknown_time_points_minutes']))
            st.caption('Превышение деформаций в расчётных волокнах не равно '
                       'утрате несущей способности всей колонны. '
                       'Время физического отказа R(t) не установлено.')
            st.json({'R_t_minutes':None,'normative_claim':False,
                     'mesh_time_convergence_still_required':True,
                     'source_gas_temperature_C':out[
                         'reference_standard_fire_gas_at_end_C']})
            st.download_button('Скачать D3 тепловую и механическую историю (JSON)',
                data=json.dumps(out,ensure_ascii=False,indent=2,default=str),
                file_name=f'{cid}_R069D3_TKP_Thermomechanics.json',
                mime='application/json',key=f'r069d3_dl_{cid}')
        if st.button('Проверить сеточную и временную чувствительность D3',
                     key=f'r069d3_refine_{cid}'):
            from rc_fire.thermal.tkp_heat import reference_annex_a_boundary
            from .r069d3 import compare_tkp_thermal_refinement
            try:
                with st.spinner('Сравнение трёх независимых решений теплопроводности'):
                    rr=compare_tkp_thermal_refinement(column,
                        boundary=reference_annex_a_boundary(
                            moisture_mass_pct=float(moisture)),
                        coarse=8,fine=12,dt_minutes=float(maxdt))
                st.write('Максимальное различие по сетке, °C:',
                         rr['max_spatial_difference_C'])
                st.write('Максимальное различие по времени, °C:',
                         rr['max_temporal_difference_C'])
                st.caption('Численная сходимость сама по себе не заменяет '
                           'верификацию граничных условий и эксперимент.')
                st.download_button('Скачать сравнение сетки D3 (JSON)',
                    json.dumps(rr,ensure_ascii=False,indent=2),
                    file_name=f'{cid}_R069D3_refinement.json',
                    mime='application/json',key=f'r069d3_refine_json_{cid}')
            except (ValueError,TypeError,ArithmeticError) as exc:
                st.error('Сеточная проверка D3: '+str(exc))
