# -*- coding: utf-8 -*-
"""Agent memory: conversation history management."""
import json
import uuid
from typing import List, Optional
from ..database import get_conn
from ..utils import now_iso

MAX_HISTORY_MESSAGES = 40  # Keep last N messages per conversation


def create_conversation(version_id: int, title: str = "") -> str:
    """Create a new conversation, return conversation_id."""
    conv_id = f"conv_{uuid.uuid4().hex[:12]}"
    conn = get_conn()
    cur = conn.cursor()
    ts = now_iso()
    cur.execute(
        "INSERT INTO agent_conversations (id, version_id, title, messages_json, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?)",
        (conv_id, version_id, title or "New Chat", "[]", ts, ts),
    )
    conn.commit()
    conn.close()
    return conv_id


def load_messages(conversation_id: str) -> List[dict]:
    """Load conversation message history."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT messages_json FROM agent_conversations WHERE id=?", (conversation_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return []
    try:
        return json.loads(row["messages_json"])
    except Exception:
        return []


def save_messages(conversation_id: str, messages: List[dict]):
    """Save conversation message history (trim to MAX_HISTORY_MESSAGES)."""
    # Keep system message + last N messages
    trimmed = _trim_messages(messages)
    conn = get_conn()
    cur = conn.cursor()
    ts = now_iso()
    cur.execute(
        "UPDATE agent_conversations SET messages_json=?, updated_at=? WHERE id=?",
        (json.dumps(trimmed, ensure_ascii=False), ts, conversation_id),
    )
    conn.commit()
    conn.close()


def update_title(conversation_id: str, title: str):
    """Update conversation title."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE agent_conversations SET title=? WHERE id=?", (title, conversation_id))
    conn.commit()
    conn.close()


def list_conversations(version_id: int) -> List[dict]:
    """List all conversations for a version, newest first."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title, created_at, updated_at FROM agent_conversations "
        "WHERE version_id=? ORDER BY updated_at DESC",
        (version_id,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_conversation(conversation_id: str) -> Optional[dict]:
    """Get conversation metadata."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM agent_conversations WHERE id=?", (conversation_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_conversation(conversation_id: str):
    """Delete a conversation and its task history."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM agent_conversations WHERE id=?", (conversation_id,))
    cur.execute("DELETE FROM agent_tasks WHERE conversation_id=?", (conversation_id,))
    conn.commit()
    conn.close()


def save_task(conversation_id: str, version_id: int, user_message: str,
              reply: str, tool_calls: list, steps: int, status: str = "completed"):
    """Save an agent task execution record."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO agent_tasks (conversation_id,version_id,user_message,reply,tool_calls_json,steps,status,created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (conversation_id, version_id, user_message, reply, json.dumps(tool_calls, ensure_ascii=False), steps, status, now_iso()),
    )
    conn.commit()
    conn.close()


def _trim_messages(messages: list) -> list:
    """Trim message history: keep system message + last MAX_HISTORY_MESSAGES."""
    if len(messages) <= MAX_HISTORY_MESSAGES:
        return messages
    # Find system message
    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    return system + rest[-(MAX_HISTORY_MESSAGES - len(system)):]