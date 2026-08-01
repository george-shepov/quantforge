from __future__ import annotations

import hmac
import os
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


ACKNOWLEDGEMENT = "I_UNDERSTAND_THIS_IS_TESTNET"


class TestnetOrderRequest(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    size: float = Field(gt=0)
    limit_price: float = Field(gt=0)
    time_in_force: Literal["Alo", "Gtc", "Ioc"] = "Alo"
    reduce_only: bool = False
    submit: bool = False
    acknowledgement: str = ""

    @model_validator(mode="after")
    def maker_only_when_opening(self) -> "TestnetOrderRequest":
        if self.submit and not self.reduce_only and self.time_in_force != "Alo":
            raise ValueError("New testnet exposure must use maker-only Alo orders")
        return self


class TestnetSafetyGate:
    def __init__(self) -> None:
        self.enabled = os.getenv("QUANTFORGE_TESTNET_EXECUTION_ENABLED", "false").lower() == "true"
        self.network = os.getenv("QUANTFORGE_EXECUTION_NETWORK", "disabled").lower()
        self.expected_token = os.getenv("QUANTFORGE_SAFETY_TOKEN", "")
        self.max_notional = float(os.getenv("QUANTFORGE_TESTNET_MAX_NOTIONAL", "100"))

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "network": self.network,
            "testnet_only": True,
            "token_configured": bool(self.expected_token),
            "private_key_configured": bool(os.getenv("HYPERLIQUID_TESTNET_PRIVATE_KEY")),
            "account_configured": bool(os.getenv("HYPERLIQUID_TESTNET_ACCOUNT_ADDRESS")),
            "max_notional": self.max_notional,
            "required_acknowledgement": ACKNOWLEDGEMENT,
        }

    def validate(self, request: TestnetOrderRequest, supplied_token: str | None) -> None:
        if not request.submit:
            return
        if not self.enabled or self.network != "testnet":
            raise PermissionError("Testnet execution is disabled")
        if request.acknowledgement != ACKNOWLEDGEMENT:
            raise PermissionError("Explicit testnet acknowledgement is required")
        if not self.expected_token or not supplied_token or not hmac.compare_digest(self.expected_token, supplied_token):
            raise PermissionError("Invalid QuantForge safety token")
        if request.size * request.limit_price > self.max_notional:
            raise PermissionError(f"Order exceeds the {self.max_notional:.2f} USDC testnet notional cap")
        if not os.getenv("HYPERLIQUID_TESTNET_PRIVATE_KEY") or not os.getenv("HYPERLIQUID_TESTNET_ACCOUNT_ADDRESS"):
            raise PermissionError("Testnet credentials are not configured")


class HyperliquidTestnetAdapter:
    def preview(self, request: TestnetOrderRequest) -> dict[str, Any]:
        return {
            "network": "testnet",
            "endpoint": "https://api.hyperliquid-testnet.xyz",
            "symbol": request.symbol,
            "side": request.side,
            "size": request.size,
            "limit_price": request.limit_price,
            "notional": request.size * request.limit_price,
            "time_in_force": request.time_in_force,
            "reduce_only": request.reduce_only,
            "would_submit": request.submit,
        }

    def submit(self, request: TestnetOrderRequest, safety_token: str | None) -> dict[str, Any]:
        gate = TestnetSafetyGate()
        gate.validate(request, safety_token)
        preview = self.preview(request)
        if not request.submit:
            return {"status": "dry_run", "order": preview}

        from eth_account import Account
        from hyperliquid.exchange import Exchange
        from hyperliquid.utils import constants

        wallet = Account.from_key(os.environ["HYPERLIQUID_TESTNET_PRIVATE_KEY"])
        exchange = Exchange(
            wallet,
            constants.TESTNET_API_URL,
            account_address=os.environ["HYPERLIQUID_TESTNET_ACCOUNT_ADDRESS"],
        )
        response = exchange.order(
            request.symbol,
            request.side == "buy",
            request.size,
            request.limit_price,
            {"limit": {"tif": request.time_in_force}},
            reduce_only=request.reduce_only,
        )
        return {"status": "submitted_to_testnet", "order": preview, "exchange_response": response}
