"""Reproducible offline core run; excludes ONLY tests needing current GitHub multicolumn_r05 package.

This is NOT a replacement for full GitHub checkout CI.
"""
from pathlib import Path
import unittest
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tests'))
SKIP_MODULES={'test_r060_integration.py','test_r061_integration.py',
              'test_r062_thermal_integration.py','test_r063_integration.py'}

def run():
    loader=unittest.TestLoader()
    suite=unittest.TestSuite()
    files=sorted((ROOT/'tests').glob('test_*.py'))
    for p in files:
        if p.name in SKIP_MODULES:continue
        suite.addTests(loader.loadTestsFromName('tests.'+p.stem))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    print('CORE_RESULT',{'tests':result.testsRun,'failures':len(result.failures),
       'errors':len(result.errors),'skipped':len(result.skipped),
       'excluded_multicolumn_modules':sorted(SKIP_MODULES)})
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(run())
