from __future__ import annotations

from app.db.models import PartyChatMessageDB, PartyDB


def party_to_dict(party: PartyDB, viewer_id: str | None = None) -> dict:
    is_member = viewer_id is not None and any(m.user_id == viewer_id for m in party.members)
    return {
        "id": party.id,
        "activity": party.activity,
        "description": party.description,
        "vibe": party.vibe,
        "leader": {"user_id": party.leader_id, "username": party.leader_username, "rsn": party.leader_rsn},
        "max_size": party.max_size,
        "member_count": len(party.members),
        "members": [
            {"user_id": m.user_id, "username": m.username, "rsn": m.rsn, "joined_at": m.joined_at.isoformat()}
            for m in party.members
        ],
        "notification_category_ids": party.notification_category_ids or [],
        "status": party.status,
        "created_at": party.created_at.isoformat(),
        "scheduled_at": party.scheduled_at.isoformat() if party.scheduled_at else None,
        "expires_at": party.expires_at.isoformat(),
        "hub_code": party.hub_code if is_member else None,
    }


def chat_message_to_dict(msg: PartyChatMessageDB) -> dict:
    return {
        "id": msg.id,
        "user_id": msg.user_id,
        "username": msg.username,
        "rsn": msg.rsn,
        "text": msg.text,
        "sent_at": msg.sent_at.isoformat(),
    }
