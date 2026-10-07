STUDY_MONEY_KEYS={'total_cost', 'cost_details', 'budget', 'upstream_inference_prompt_cost', 'upstream_inference_completions_cost', 'raw_usage_charge_usd', 'upstream_inference_cost', 'shared_ledger', 'ledger_snapshot', 'ledger', 'upper_reservation_usd', 'cost_usd', 'raw_usage_charges'}
DENY_KEYS={'password', 'reasoning_content', 'apikey', 'reasoning_details', 'authorization', 'private_key', 'chain_of_thought', 'refresh_token', 'access_token', 'credentials', 'api_key', 'client_secret'}
"""Accounting-only publication projection; no scientific changes."""
def money_key(key, parent):
    folded=str(key).casefold()
    return folded in STUDY_MONEY_KEYS or folded.endswith('_usd') or \
        (folded=='cost' and parent in ('usage','raw_usage'))

def redact(value, path=(), removed=None):
    """Keep fictional decision costs and unit pricing; omit actual expenditure."""
    removed=[] if removed is None else removed
    if isinstance(value,dict):
        result={}
        for key,child in value.items():
            if money_key(key,path[-1] if path else None):
                removed.append('/'.join((*path,str(key))))
            elif str(key).casefold() in DENY_KEYS:
                if child not in (None,'',[],{}): raise ValueError('Private field in publication projection')
            elif key=='raw_path':
                result[key]=str(child).replace('\\','/').split('/data/',1)[-1]
                if not result[key].startswith('data/'):
                    result[key]='data/'+result[key]
            elif key in ('usage','raw_usage') and isinstance(child,dict):
                result[key]=usage_projection(child)
            else: result[key]=redact(child,(*path,str(key)),removed)
        return result
    if isinstance(value,list): return [redact(child,(*path,str(i)),removed) for i,child in enumerate(value)]
    return value

def usage_projection(value):
    if not isinstance(value,dict):return {}
    allowed=('prompt_tokens','completion_tokens','total_tokens','prompt_tokens_details','completion_tokens_details')
    result={k:value[k] for k in allowed if k in value}
    for field in ('prompt_tokens_details','completion_tokens_details'):
        if field in result:
            if not isinstance(result[field],dict):raise ValueError('Token metadata must be an object')
            result[field]={k:v for k,v in result[field].items() if k in
                ('cached_tokens','cache_write_tokens','reasoning_tokens','audio_tokens','image_tokens','video_tokens')}
    return result
