"""Frozen science with charge-known accounting projections; no paid calls."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from score_responses import score
from inference import analyze_scored_cells
def main():
    cells=score('heldout',root=ROOT)
    cases=json.loads((ROOT/'data/heldout/cases.json').read_text())
    config=('ds_off','ds_low','gpt6_luna_low')
    result=analyze_scored_cells(cases,cells,config,config[0],config[1])
    (ROOT/'results').mkdir(exist_ok=True)
    for name,value in (('heldout-scored-cells',cells),('heldout-inference',result)):
        (ROOT/('results/'+name+'.json')).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
if __name__=='__main__':main()
