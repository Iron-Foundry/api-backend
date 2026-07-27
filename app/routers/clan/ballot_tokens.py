from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ballot_tokens import BallotTokenAccount, BallotTokenTransaction
from app.dependencies import get_current_user, get_session

router = APIRouter()


@router.get("/ballot-tokens/me")
async def get_my_ballot_tokens(
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    discord_user_id = int(current_user["sub"])

    balance_result = await session.execute(
        select(BallotTokenAccount.balance).where(
            BallotTokenAccount.discord_user_id == discord_user_id
        )
    )
    balance = balance_result.scalar_one_or_none() or 0

    tx_result = await session.execute(
        select(BallotTokenTransaction)
        .where(BallotTokenTransaction.discord_user_id == discord_user_id)
        .order_by(BallotTokenTransaction.created_at.desc())
        .limit(20)
    )
    transactions = [
        {
            "id": tx.id,
            "delta": tx.delta,
            "reason": tx.reason,
            "run_id": tx.run_id,
            "created_at": tx.created_at.isoformat(),
        }
        for tx in tx_result.scalars().all()
    ]

    return {"balance": balance, "transactions": transactions}
