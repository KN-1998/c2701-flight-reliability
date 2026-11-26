"""One command for logic/integration tests, with an unambiguous exit code."""
from pathlib import Path
import io,json,sys,unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'tests'))
suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
stream=io.StringIO()
result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
report=stream.getvalue()
out=ROOT/'results';out.mkdir(exist_ok=True)
(out/'TEST_REPORT.txt').write_text(report,encoding='utf-8')
(out/'TEST_STATUS.json').write_text(json.dumps({'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'successful':result.wasSuccessful(),'evidence_level':'numeric/integration checks, NOT empirical validation'},indent=2),encoding='utf-8')
print(report)
sys.exit(0 if result.wasSuccessful() else 1)
