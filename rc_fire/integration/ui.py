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
