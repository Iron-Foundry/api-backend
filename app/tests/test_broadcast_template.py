from __future__ import annotations

import pytest

from app.models.clan_chat import ClanChatPayload


@pytest.mark.parametrize(
    ("sent", "plain"),
    [
        (
            "Kz Grind received a drop: <int_0=2><int_0:spacer> x Spirit seed"
            "<int_0=280000> (<int_0:spacer> coins).",
            "Kz Grind received a drop: 2 x Spirit seed (280,000 coins).",
        ),
        (
            "<int_0=162000000>Ursaring has reached <int_0:spacer> XP in Ranged.",
            "Ursaring has reached 162,000,000 XP in Ranged.",
        ),
        (
            "<int_p1=0>GIMTUNABARGE has a funny feeling like "
            "<switch,int_p1,he's,she's,they're> being followed: "
            "<int_0=32>Tumeken's guardian at <int_0:spacer> completions.",
            "GIMTUNABARGE has a funny feeling like he's being followed: "
            "Tumeken's guardian at 32 completions.",
        ),
        (
            "<str_quest_name_0=Legends' Quest>V0xes has completed a quest: "
            "<str_quest_name_0>",
            "V0xes has completed a quest: Legends' Quest",
        ),
        (
            "<col=ff0000>X</col> received <int_9:spacer> coins",
            "<col=ff0000>X</col> received <int_9:spacer> coins",
        ),
        (
            "<int_p1=7>X feels like <switch,int_p1,he's,she's> it.",
            "X feels like <switch,int_p1,he's,she's> it.",
        ),
        (
            "a <lt>3 b<gt> c<at>d <lt>int_0:spacer<gt>",
            "a <3 b> c@d <int_0:spacer>",
        ),
    ],
)
def test_payload_resolves_broadcast_variable_tags(sent: str, plain: str) -> None:
    payload = ClanChatPayload(
        clan_name="Iron Foundry", sender="Iron Foundry", message=sent, rank="IRONMAN"
    )
    assert payload.message == plain
