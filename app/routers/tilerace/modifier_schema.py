from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class SnakesLaddersModifier(BaseModel):
    type: Literal["snakes_ladders"]
    target_position: int


class FogModifier(BaseModel):
    type: Literal["fog"]
    radius: int = 1


class BonusPenaltyModifier(BaseModel):
    type: Literal["bonus_penalty"]
    effect: Literal["extra_roll", "skip_turn", "reroll"]


class SabotageModifier(BaseModel):
    type: Literal["sabotage"]
    action: Literal["steal_progress", "block"]
    amount: int = 0


Modifier = Annotated[
    SnakesLaddersModifier | FogModifier | BonusPenaltyModifier | SabotageModifier,
    Field(discriminator="type"),
]
