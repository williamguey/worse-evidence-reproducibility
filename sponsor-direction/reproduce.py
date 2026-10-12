"""Run the complete scientific calculation without network access."""
import hashlib
import json
from pathlib import Path
from science import calculate, compare
root=Path(__file__).resolve().parent
for name,expected in json.loads((root/'manifest.json').read_text())['files'].items():
    if hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected:
        raise SystemExit('Manifest mismatch: '+name)
def read(name):return json.loads((root/name).read_text())
answer=calculate(read('data/cases.json'),read('data/plan.json'),read('data/outcomes.json'))
compare(read('expected.json'),answer)
(root/'reproduced.json').write_text(json.dumps(answer,indent=2,allow_nan=False)+'\n')
print('PASS: all 1,872 planned scientific cells, exact oracle, envelopes, fixed mixture, intervals, and Holm3 reproduced.')
