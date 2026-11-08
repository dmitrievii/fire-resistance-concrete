"""DOCX audit heading, without any normative certification label."""
from __future__ import annotations

def add_member_evidence_note(doc, calculation):
    doc.add_heading('R0.6.4D — сопряжённая механика колонны (диагностика)',level=2)
    r=calculation.get('member_r064d') or {}
    doc.add_paragraph('Нормативная огнестойкость R90 данным разделом НЕ подтверждается.')
    doc.add_paragraph(f"Статус расчёта: {r.get('status','NOT_EVALUATED')}. ")
    doc.add_paragraph('Введённые усилия уже расчётные для пожара. Необходимы полные температурные поля по длине, '
                      'нормативная квалификация диаграмм, устойчивости и откола бетона.')


def add_fire_history_note(doc, calculation):
    from .time_ui import STATUS_RU, STATE_RU
    result = calculation.get('fire_history_r069')
    if not result:
        return
    doc.add_heading('R0.6.9 — несущая способность во времени (диагностика)', level=2)
    doc.add_paragraph(STATUS_RU.get(result['status'], result['status']))
    controls = result['controls']
    doc.add_paragraph(f"Интервал 0–{controls['end_minutes']:g} мин; шаг "
        f"{controls['step_minutes']:g} мин; точность границы {controls['tolerance_minutes']:g} мин. "
        f"Проверено моментов: {result['evaluation_count']}.")
    doc.add_paragraph('Усилия для пожарной ситуации неизменны. Температурное поле и механика '
        'пересчитываются в каждом проверенном моменте. Принимается одинаковый нагрев по длине. '
        'Начальные несовершенства, ползучесть и непрерывное предельное состояние не квалифицированы. '
        'Нормативный предел огнестойкости НЕ подтверждён. Граница модели и несходимость не доказывают разрушение.')
    table = doc.add_table(rows=1, cols=4)
    for cell, text in zip(table.rows[0].cells, ('t, мин', 'Состояние', 'max ε/εlim', 'Причина')):
        cell.text = text
    for row in result['samples']:
        ratio = row.get('maximum_strain_ratio')
        for cell, text in zip(table.add_row().cells, (f"{row['time_minutes']:g}",
                STATE_RU[row['state']], '—' if ratio is None else f'{ratio:.5f}',
                row.get('reason') or '—')):
            cell.text = text
    boundary = result.get('boundary')
    if boundary:
        doc.add_paragraph('Последний допущенный момент: ' + str(boundary['last_admitted_minutes'])
            + '; первый недопущенный: ' + str(boundary['first_nonadmitted_minutes'])
            + ' мин. Это проверенные состояния, а не доказанная непрерывная граница R.')
    doc.add_paragraph('Идентификатор исходных данных: ' + result['source_sha256'])
