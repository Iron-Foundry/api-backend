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


class TrapModifier(BaseModel):
    """Landing here rolls its own dice and sends the team back that many steps.

    The dice are chosen when the trap is placed, so a trap can be made harsher
    than the board's own roll. A team springs each trap cell once; the same
    board may carry several traps and every one of them still bites.
    """

    type: Literal["trap"]
    dice_count: int = Field(default=1, ge=1, le=5)
    dice_sides: int = Field(default=6, ge=1, le=20)


Modifier = Annotated[
    SnakesLaddersModifier
    | FogModifier
    | BonusPenaltyModifier
    | SabotageModifier
    | TrapModifier,
    Field(discriminator="type"),
]
