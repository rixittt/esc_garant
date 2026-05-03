def make_key(prefix: str, entity_id: int, action: str) -> str:
    return f'{prefix}:{entity_id}:{action}'
