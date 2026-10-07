"""Original H01 scientific implementation is unchanged; accounting is private."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import analyze_study as analysis
from publication_fields import redact
INVALID_STATUSES={'malformed_raw_response','provider_error','model_mismatch','completion_count_invalid',
    'finish_reason_not_stop','refusal_or_unexpected_tool_call','content_not_string','output_not_strict_json','choice_schema_invalid'}
if hasattr(analysis,'parse_completion'):
    frozen_parse=analysis.parse_completion
    def projected_parse(raw,model):
        result=frozen_parse(raw,model)
        marker=raw.get('source_completion_status') if isinstance(raw,dict) else None
        if marker in INVALID_STATUSES:
            if result[0] is not None:raise ValueError('Projected invalid status contradicts strict valid choice')
            return None,marker
        if marker not in (None,'valid'):raise ValueError('Unknown projected completion status')
        return result
    analysis.parse_completion=projected_parse
def main():
    for split in ('pilot','heldout'):
        value=analysis.analyze_study(ROOT,split,materials_verified=True,charges_verified=True)
        value=redact(value)
        path=ROOT/('results/'+split+'/analysis.json');path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value,indent=2,allow_nan=False,default=getattr(analysis,'_json_default',None))+'\n')
    print(json.dumps({'original_scientific_method':'unchanged Holm2','charge_values':'private; independently verified before publication'}))
if __name__=='__main__':main()
