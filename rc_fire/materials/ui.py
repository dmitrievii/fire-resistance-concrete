"""Streamlit editor for R0.6.1 material properties (uses canonical project dict)."""
from __future__ import annotations
from rc_fire.materials import resolve_materials, ConcreteMix, Reinforcement, concrete_at_temperature, reinforcement_at_temperature

FAMILIES={None:'— не задан —','siliceous':'Силикатный заполнитель','calcareous':'Карбонатный заполнитель'}
CONSISTENCY={None:'— не задан —','V3_V4':'V3–V4 (Ж3–Ж4)','V1_V2':'V1–V2 (Ж1–Ж2)',
             'S1_S2':'S1–S2 (П1–П2)','S3_S5':'S3–S5 (П3–П5)'}
CURING={None:'— не задан —','natural':'Естественное твердение','heat':'Тепловая обработка'}
MODULUS_AGG={None:'— не задан —','gravel_granite_upto40':'Гравий / гранитный щебень до 40 мм',
             'other':'Другой заполнитель (нужны испытания Ecm)'}
TRISTATE={None:'— не задано —',True:'Да',False:'Нет'}
STEEL_TYPES={None:'— не задан —','weldable_bar':'Свариваемая стержневая арматура',
             'corrosion_resistant_bar':'Коррозионно-стойкая',
             'wire_or_heat_treated':'Проволока / термически упрочнённая'}

def render_material_inputs(st, project, column, safe_change, update_material_spec):
    """Live project editor. Fields remain blank until explicitly supplied."""
    stored=column.get('material_spec') or {}
    cm=stored.get('concrete') or {};sm=stored.get('steel') or {}
    cid=column['id']
    with st.expander('R0.6.1 — нормативные свойства бетона и арматуры',expanded=False):
        st.caption('СП 5.03.01-2020: таблицы 6.1 и 6.3, §6.2.2. '
                   'СП 2.02.05-2026: таблицы 9–12. Пустые свойства не заменяются допущениями.')
        with st.form(f'materials_{cid}_rev{project["revision"]}'):
            cols=st.columns(2)
            values={'concrete':{},'steel':{}}
            def choice(col,name,options,old):
                opts=list(options)
                return col.selectbox(name,opts,index=opts.index(old) if old in opts else 0,
                    format_func=lambda x:options[x])
            with cols[0]:
                st.markdown('**Бетон**')
                values['concrete']['aggregate_family']=choice(st,'Заполнитель для пожара',FAMILIES,cm.get('aggregate_family'))
                values['concrete']['consistency']=choice(st,'Консистенция по таблице 6.3',CONSISTENCY,cm.get('consistency'))
                values['concrete']['curing']=choice(st,'Способ твердения',CURING,cm.get('curing'))
                values['concrete']['modulus_aggregate']=choice(st,'Заполнитель для Ecm',MODULUS_AGG,cm.get('modulus_aggregate'))
            with cols[1]:
                st.markdown('**Дополнительные свойства**')
                values['concrete']['fine_grained']=choice(st,'Мелкозернистый бетон',TRISTATE,cm.get('fine_grained'))
                values['steel']['product_type']=choice(st,'Вид арматуры по таблице 10',STEEL_TYPES,sm.get('product_type'))
                val=cm.get('independently_measured_Ecm_GPa')
                s=st.text_input('Ecm из испытаний, ГПа (необязательно)',value='' if val is None else str(val))
                values['concrete']['independently_measured_Ecm_GPa']=s
                val=sm.get('fyk_MPa')
                s=st.text_input('Подтверждённый fyk, МПа (необязательно)',value='' if val is None else str(val))
                values['steel']['fyk_MPa']=s
            submitted=st.form_submit_button('Сохранить свойства материала')
            if submitted:safe_change(update_material_spec,project,cid,values)
        data=resolve_materials(column)
        st.write('Статус каталога: **'+data['status']+'**')
        if data['issues']:st.info('Для полного разрешения свойств: '+ '; '.join(data['issues']))
        conc=data.get('concrete')
        steel=data.get('steel')
        if conc:
            st.write(f"Бетон: fck={conc['f_ck_MPa']:g} МПа, " +
                     (f"Ecm={conc['E_cm_GPa']:g} ГПа" if conc['E_cm_GPa'] is not None else 'Ecm не определён'))
        if steel:st.write('Арматура: '+steel['group']+'; '+('Es='+str(steel['E_s_GPa'])+' ГПа'))
        if data['status']=='resolved_for_property_lookup':
            profile=column['material_spec']
            concrete=ConcreteMix(strength_class=column['concrete'],**profile['concrete'])
            rebar=Reinforcement(grade=column['steel_grade'],**profile['steel'])
            values=[]
            for t in (20.,200.,400.,500.,600.,800.):
                c=concrete_at_temperature(concrete,t,data['concrete'])
                s=reinforcement_at_temperature(rebar,t,data['steel'])
                values.append({'θ, °C':int(t),'kc':c['k_c'],'βc':c['beta_E'],
                              'ks':s['k_s'],'βs':s['beta_E']})
            st.dataframe(values,hide_index=True,use_container_width=True)
        st.caption('R0.6.1 проверяет нормативное происхождение свойств. '
                   'Решатель R0.5.6 пока остаётся диагностическим; '
                   'положительный вывод R90 заблокирован.')