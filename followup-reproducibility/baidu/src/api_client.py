"""Offline hash and JSON output helpers; no transport or accounting."""
import hashlib
import json
import os
from pathlib import Path

def sha(value):
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

def request_hashes(body):
    return {'body_sha256': sha(body), 'prompt_sha256': sha(body.get('messages', [])),
            'settings_sha256': sha({k: v for k, v in body.items() if k != 'messages'})}

def write_json(path, value):
    """Replace one local receipt atomically; never persist a credential."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp-' + str(os.getpid()))
    with temporary.open('w') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, path)
