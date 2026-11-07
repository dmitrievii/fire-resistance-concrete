"""DOCX audit heading, without any normative certification label."""
from __future__ import annotations

def add_member_evidence_note(doc, calculation):
    doc.add_heading('R0.6.4D — сопряжённая механика колонны (диагностика)',level=2)
    r=calculation.get('member_r064d') or {}
    doc.add_paragraph('Нормативная огнестойкость R90 данным разделом НЕ подтверждается.')
    doc.add_paragraph(f"Статус расчёта: {r.get('status','NOT_EVALUATED')}. ")
    doc.add_paragraph('Необходимы полные температурные поля по длине, пожарные сочетания нагрузок, '
                      'нормативная квалификация диаграмм, устойчивости и откола бетона.')
