import json


async def log_action(conn, actor_id: int, action: str, entity_type: str, entity_id: int, payload: dict | None = None) -> None:
    await conn.execute(
        'INSERT INTO audit_logs(actor_id, action, entity_type, entity_id, payload_json) VALUES(?, ?, ?, ?, ?)',
        (actor_id, action, entity_type, entity_id, json.dumps(payload or {}, ensure_ascii=False)),
    )
