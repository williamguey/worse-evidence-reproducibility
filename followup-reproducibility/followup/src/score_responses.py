"""Strictly score the complete frozen index; never drop missing cells."""
import argparse
import json
from pathlib import Path

from api_client import sha, write_json
from run_study import ROOT, strict_answer, validate_contract


def score(split, root=ROOT):
    index = json.loads((root / 'data' / split / 'request-index.json').read_text())
    cells = []
    for rid, entry in sorted(index.items()):
        task = entry['task']
        model = entry['model']
        configuration_id = entry.get('configuration_id') or entry.get('config_id') or model.get('configuration_id') or model.get('config_id') or model.get('id')
        if not configuration_id:
            raise ValueError('Request lacks its configuration identifier: ' + rid)
        row = {k: task.get(k) for k in ('project_id', 'split', 'case_id', 'family', 'block',
                'representation', 'preference', 'order', 'control', 'expected', 'gap', 'normalized_gap')}
        row.update({'request_id': rid, 'config_id': configuration_id, 'configuration_id': configuration_id,
                    'model_id': entry['body']['model'], 'valid': False, 'choice': None,
                    'error': None, 'invalid_reason': 'missing', 'prompt_sha256': task.get('prompt_sha256'),
                    'body_sha256': sha(entry['body']), 'actual_model': None})
        path = root / 'data' / split / 'raw' / (rid + '.json')
        failure = path.with_suffix('.failure.json')
        invalid = path.with_suffix('.invalid.json')
        if failure.exists() or invalid.exists():
            row['invalid_reason'] = 'retained_failed_or_invalid_attempt'
        elif path.exists():
            try:
                data = json.loads(path.read_text())
                row['actual_model'] = data.get('model')
                answer = strict_answer(data, entry['body']['model'])
                contract = validate_contract(data, entry, json.loads(path.with_suffix('.request.json').read_text()))
                receipt = json.loads(path.with_suffix('.receipt.json').read_text())
                if receipt.get('charge_known') is not True:
                    raise ValueError('cost_UNKNOWN')
                row['actual_provider'] = contract['actual_provider']
                row['reasoning_tokens'] = contract['reasoning_tokens']
                row.update({'valid': True, 'choice': answer['choice'],
                            'error': answer['choice'] != task['expected'], 'invalid_reason': None})
            except (ValueError, TypeError, KeyError, AssertionError, OSError) as exc:
                row['invalid_reason'] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        cells.append(row)
    write_json(root / 'results' / (split + '-scored-cells.json'), cells)
    return cells


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--split', choices=['smoke', 'main', 'heldout'], required=True)
    args = parser.parse_args()
    cells = score(args.split)
    print(json.dumps({'split': args.split, 'planned': len(cells), 'valid': sum(c['valid'] for c in cells),
                      'invalid_or_missing': sum(not c['valid'] for c in cells)}, indent=2))
