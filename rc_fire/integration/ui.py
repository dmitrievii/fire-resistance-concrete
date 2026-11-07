"""Opt-in Streamlit entrypoint; by default new solver does no heavy computation."""
from __future__ import annotations
import json
from .r064d import (sample_station_bundle, evaluate_explicit_member_bundle,
                    MemberEvidenceInputError, _signature)


def render_member_evidence(st, column, existing_result):
    with st.expander('R0.6.4D · Нагретая колонна: диагностика второго порядка (не R90)',expanded=False):
        st.caption('Исследовательский режим. Требуются явные температуры всех точек Гаусса и узлов; '
                   'из одного поперечного сечения температура автоматически по длине не переносится.')
        st.json({'status': existing_result.get('member_r064d',{}).get('status','NOT_EVALUATED'),
                 'normative_claim': False,'fire_resistance_status':'not_demonstrated'})
        sample=sample_station_bundle(column,node_count=3)
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
