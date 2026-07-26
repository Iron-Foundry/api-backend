"""WOM efficiency-rate API methods mixin."""

from __future__ import annotations

from app.services.http.wom_base import WomHandlerBase


class WomEfficiencyMixin(WomHandlerBase):
    async def get_efficiency_rates(
        self, metric: str, account_type: str = "ironman"
    ) -> list[dict]:
        """Fetch EHP or EHB rate configs for an account type. Returns [] on failure."""
        resp = await self._get_with_rate_limit(
            "/efficiency/rates", params={"metric": metric, "type": account_type}
        )
        return resp.json() if resp.is_success else []
