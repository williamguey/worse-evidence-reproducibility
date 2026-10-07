"""Frozen response contract, offline extraction; no collection."""
import json
from pathlib import Path
from api_client import request_hashes
ROOT=Path(__file__).resolve().parents[1]

class ContractError(ValueError):
    """Identity, frozen settings, or usage integrity requires collection to stop."""

def strict_answer(data, expected_model):
    if not isinstance(data, dict):
        raise ValueError('non_object_response')
    if data.get('model') != expected_model:
        raise ContractError('model_mismatch')
    choices = data.get('choices') or []
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError('multiple_or_absent_choices')
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ValueError('invalid_choice_object')
    message = choice.get('message') or {}
    if not isinstance(message, dict):
        raise ValueError('invalid_message_object')
    if choice.get('finish_reason') != 'stop' or message.get('refusal'):
        raise ValueError('incomplete_output')
    if not isinstance(message.get('content'), str):
        raise ValueError('missing_string_content')

    def pairs(items):
        answer = dict(items)
        if len(answer) != len(items):
            raise ValueError('duplicate_json_key')
        return answer

    answer = json.loads(message['content'], object_pairs_hook=pairs)
    if not isinstance(answer, dict) or set(answer) != {'choice'} or answer['choice'] not in ('A', 'B'):
        raise ValueError('invalid_answer')
    return answer

def validate_contract(data, entry, request_receipt):
    """Require provider identity and the complete frozen endpoint/settings tag.

    OpenRouter returns a provider display name, whereas `provider.only` may
    contain an endpoint tag such as `deepinfra/fp8`. The full endpoint tag is
    checked through the frozen body/settings hashes; its base provider is
    compared with the returned display name.
    """
    if not isinstance(data, dict) or not isinstance(request_receipt, dict):
        raise ContractError('receipt_object_missing')
    hashes = request_hashes(entry['body'])
    if any(request_receipt.get(k) != v for k, v in hashes.items()):
        raise ContractError('settings_or_prompt_hash_mismatch')
    only = entry['body'].get('provider', {}).get('only') or []
    actual = data.get('provider')
    if not isinstance(only, list) or len(only) != 1 or not isinstance(only[0], str):
        raise ContractError('provider_mismatch_or_missing')
    endpoint_tag = only[0]
    base_provider = endpoint_tag.split('/', 1)[0]
    normalized = ''.join(c for c in str(actual or '').casefold() if c.isalnum())
    requested = ''.join(c for c in base_provider.casefold() if c.isalnum())
    if not requested or normalized != requested:
        raise ContractError('provider_mismatch_or_missing')
    usage = data.get('usage') or {}
    if not isinstance(usage, dict):
        raise ContractError('usage_accounting_object_missing')
    for token_field in ('prompt_tokens', 'completion_tokens'):
        token_count = usage.get(token_field)
        if not isinstance(token_count, int) or isinstance(token_count, bool) or token_count < 0:
            raise ContractError('total_token_accounting_missing')
    if usage['completion_tokens'] > entry['body']['max_tokens']:
        raise ContractError('completion_token_cap_exceeded')
    completion_details = usage.get('completion_tokens_details') or {}
    if not isinstance(completion_details, dict):
        raise ContractError('reasoning_accounting_object_missing')
    reasoning_tokens = completion_details.get('reasoning_tokens')
    if not isinstance(reasoning_tokens, int) or isinstance(reasoning_tokens, bool) or reasoning_tokens < 0:
        raise ContractError('reasoning_token_accounting_missing')
    disabled = entry['body'].get('reasoning', {}).get('enabled') is False
    if disabled and reasoning_tokens != 0:
        raise ContractError('reasoning_disabled_but_tokens_observed')
    if reasoning_tokens > usage['completion_tokens']:
        raise ContractError('reasoning_tokens_exceed_total_completion')
    return {'actual_provider': actual, 'requested_provider_endpoint': endpoint_tag,
            'reasoning_tokens': reasoning_tokens,
            'reasoning_enabled': not disabled}
