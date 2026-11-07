#!/usr/bin/env python3
"""Safely overlay R0.6.3A–R0.6.4D on a pinned full GitHub checkout.

A fresh checkout of main commit 02c689... is required. The script changes
neither main nor unrelated files, and never writes a positive R90 verdict.
It is non-destructive in --check mode (the default).
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess
import hashlib
import shutil
import sys

PINNED_MAIN='02c689fbcfdd946391842d2394376daf1216c6a6'
SCRIPT_ROOT=Path(__file__).resolve().parents[1]
SOURCES=('rc_fire/mechanics','rc_fire/member','rc_fire/integration')
# Keep original R0.6.1/R0.6.2/R0.6.0 source intact; only mechanic deltas are overlaid.
SKIP_SOURCE={'rc_fire/mechanics/ui.py'}
TESTS=('test_r063a_independent.py','test_r063b_qualification.py',
       'test_r063c_resolution.py','test_r064_member_stability.py',
       'test_r064b_coupled.py','test_r064c_uls.py',
       'test_r064d_integration.py','test_r064d_constitutive.py','test_r064d_hooks.py',
       'test_r063_integration.py')
SCRIPTS=('tools/integrate_r064d.py','tools/validate_constitutive_r064d.py',
         'tools/run_isolated_r064d.py')


class IntegrateError(RuntimeError):pass


def _replace_once(txt,old,new,label):
    n=txt.count(old)
    if n!=1:
        raise IntegrateError(f'{label}: expected exactly one insertion anchor, found {n}')
    return txt.replace(old,new,1)


def patch_facade(txt):
    if 'R064D_REPOSITORY_HOOK' in txt:
        raise IntegrateError('project_calculator already contains R064D hook')
    txt=_replace_once(txt,'def evaluate_column(c,grid=48):',
             'def _evaluate_column_pre_r064d(c,grid=48):','project_calculator: facade')
    marker='def evaluate_project(project,grid=48):'
    inject=("# R064D_REPOSITORY_HOOK: add evidence without modifying historical calculation.\n"
            "def evaluate_column(c,grid=48):\n"
            "    from rc_fire.integration import attach_member_evidence\n"
            "    old = _evaluate_column_pre_r064d(c,grid)\n"
            "    return attach_member_evidence(old,expected_column=c)\n\n\n")
    return _replace_once(txt,marker,inject+marker,'project_calculator: project')


def patch_streamlit(txt):
    if 'R064D_REPOSITORY_HOOK' in txt:raise IntegrateError('Streamlit already hooked')
    anchor='    render_mechanics_results(st,c,calculation)'
    add=(anchor+'\n'
         '    # R064D_REPOSITORY_HOOK: diagnostic-only opt-in, no default solve.\n'
         '    from rc_fire.integration.ui import render_member_evidence\n'
         '    render_member_evidence(st,c,calculation)')
    txt=_replace_once(txt,anchor,add,'multicolumn app')
    marker="if selected=='Обзор проекта':show_overview()"
    before="""# Restore only diagnostics associated with unchanged source column data.
from rc_fire.integration.r064d import _signature as _r064d_signature
for _column in project['columns']:
    _key='r064d_result_'+str(_column['id'])
    _saved=st.session_state.get(_key)
    if _saved is not None and _saved.get('signature')==_r064d_signature(_column):
        calculations[_column['id']]['member_r064d']=_saved['result']
    elif _saved is not None:
        st.session_state.pop(_key,None)
"""
    return _replace_once(txt,marker,before+marker,'multicolumn app: cached evidence')


def patch_reports(txt):
    if 'R064D_REPOSITORY_HOOK' in txt:raise IntegrateError('reports already hooked')
    anchor="    add_text(doc,'Параметрический диагностический расчёт. Не является нормативным подтверждением R90.',bold=True)"
    txt=_replace_once(txt,anchor,anchor+'\n    # R064D_REPOSITORY_HOOK: no extra pages for an unrequested member diagnostic.\n'
        '    if calc.get("member_r064d",{}).get("status") not in (None, "NOT_EVALUATED"):\n'
        '        from rc_fire.integration.report import add_member_evidence_note\n'
        '        add_member_evidence_note(doc,calc)', 'project_reports: add_column')
    old="        add_r056_diagnostics(doc,c,calc)\n        finish(doc,target,template)"
    new=("        add_r056_diagnostics(doc,c,calc)\n"
         "        if calc.get('member_r064d',{}).get('status') not in (None, 'NOT_EVALUATED'):\n"
         "            from rc_fire.integration.report import add_member_evidence_note\n"
         "            add_member_evidence_note(doc,calc)\n"
         "        finish(doc,target,template)")
    return _replace_once(txt,old,new,'project_reports: single_report')


def patch_entrypoint(txt):
    if 'R064D_HOT_RELOAD_GUARD' in txt:
        raise IntegrateError('entrypoint already patched')
    txt=_replace_once(txt,'"R0.6.3-section-mechanics-v1"',
        '"R0.6.3C-source-adjudication-candidate"','streamlit: mechanics stamp')
    marker='if _stale:\n'
    extra=("# R064D_HOT_RELOAD_GUARD: prevent mixing old member/bridge modules.\n"
      "for _name, _version in ((\"rc_fire.member.coupled\", \"R0.6.4C-member-uls-audited-diagnostic-v1\"),\n"
      "                        (\"rc_fire.integration.r064d\", \"R0.6.4D-repository-integration-v1\")):\n"
      "    _existing = sys.modules.get(_name)\n"
      "    if _existing is not None:\n"
      "        _stale |= getattr(_existing, \"VERSION\", None) != _version\n\n")
    # quote characters inside the generated source are not escaped after evaluation
    extra=extra.replace('\\"','"')
    txt=_replace_once(txt,marker,extra+marker,'streamlit: hot reload marker')
    anchor='or _name == "rc_fire.thermal" or _name.startswith("rc_fire.thermal.")):'
    txt=_replace_once(txt,anchor,
       'or _name == "rc_fire.thermal" or _name.startswith("rc_fire.thermal.")\n'
       '             or _name == "rc_fire.member" or _name.startswith("rc_fire.member.")\n'
       '             or _name == "rc_fire.integration" or _name.startswith("rc_fire.integration.")):',
       'streamlit: cache invalidation')
    return txt


PATCHES={'multicolumn_r05/project_calculator.py':patch_facade,
         'multicolumn_r05/app.py':patch_streamlit,
         'multicolumn_r05/project_reports.py':patch_reports,
         'streamlit_app.py':patch_entrypoint}


def _git(root,*args):
    r=subprocess.run(['git','-C',str(root),*args],capture_output=True,text=True)
    if r.returncode:raise IntegrateError(f'git {" ".join(args)}: {r.stderr.strip()}')
    return r.stdout.strip()


def build_plan(target:Path,source:Path=SCRIPT_ROOT):
    target=target.resolve(); source=source.resolve()
    if not (target/'multicolumn_r05/project_model.py').is_file():
        raise IntegrateError('target is not a complete R0.5.6+ repository (missing project_model.py)')
    changes={}
    for p,action in PATCHES.items():
        existing=target/p
        if not existing.is_file():raise IntegrateError(f'missing app integration anchor: {p}')
        changes[p]=action(existing.read_text(encoding='utf-8'))
    for folder in SOURCES:
        for f in (source/folder).rglob('*.py'):
            p=f.relative_to(source).as_posix()
            if p in SKIP_SOURCE:continue
            changes[p]=f.read_text(encoding='utf-8')
    for test in TESTS:
        p=f'tests/{test}'
        if not (source/p).is_file():raise IntegrateError('missing test '+p)
        changes[p]=(source/p).read_text(encoding='utf-8')
    for p in SCRIPTS:
        changes[p]=(source/p).read_text(encoding='utf-8')
    return changes


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('repository',type=Path)
    ap.add_argument('--apply',action='store_true',help='write overlay in the current non-main branch')
    ap.add_argument('--allow-unpinned',action='store_true',help='for development only; audit diff manually')
    args=ap.parse_args()
    root=args.repository.resolve()
    head=_git(root,'rev-parse','HEAD')
    if head!=PINNED_MAIN and not args.allow_unpinned:
        raise IntegrateError(f'HEAD {head} != pinned main {PINNED_MAIN}')
    if _git(root,'status','--porcelain'):
        raise IntegrateError('target checkout must be clean')
    branch=_git(root,'branch','--show-current')
    if args.apply and branch in ('main','master',''):
        raise IntegrateError('refusing to modify main/master/detached HEAD; create an integration branch first')
    changes=build_plan(root)
    altered=[p for p,s in changes.items() if not (root/p).is_file() or (root/p).read_text(encoding='utf-8')!=s]
    print(f'R064D planned overlay: {len(altered)} paths; HEAD={head}; branch={branch}')
    for p in sorted(altered):print(' - '+p)
    if not args.apply:
        print('DRY RUN: nothing written; use --apply on a clean feature branch')
        return
    for p in altered:
        dest=root/p; dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(changes[p],encoding='utf-8')
    print('UPDATED: run python -m unittest discover -s tests -v; do not merge without full green CI')


if __name__=='__main__':
    try:main()
    except IntegrateError as exc:
        print('R064D INTEGRATION BLOCKED:',exc,file=sys.stderr)
        raise SystemExit(2)
