from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class ExchangeEnvironment(str, Enum):
    SIMULATION = "simulation"
    TESTNET = "testnet"
    DEMO = "demo"
    MAINNET_READONLY = "mainnet-readonly"


@dataclass(frozen=True)
class ExchangeEndpoints:
    rest: str
    websocket: str | None
    environment: ExchangeEnvironment
    execution_allowed: bool = False


def endpoints_for(exchange: str, environment: ExchangeEnvironment) -> ExchangeEndpoints:
    exchange = exchange.lower()
    if environment == ExchangeEnvironment.SIMULATION:
        return ExchangeEndpoints("", None, environment, False)

    endpoints: dict[tuple[str, ExchangeEnvironment], ExchangeEndpoints] = {
        ("hyperliquid", ExchangeEnvironment.TESTNET): ExchangeEndpoints(
            "https://api.hyperliquid-testnet.xyz", "wss://api.hyperliquid-testnet.xyz/ws", environment
        ),
        ("hyperliquid", ExchangeEnvironment.MAINNET_READONLY): ExchangeEndpoints(
            "https://api.hyperliquid.xyz", "wss://api.hyperliquid.xyz/ws", environment
        ),
        ("bybit", ExchangeEnvironment.TESTNET): ExchangeEndpoints(
            "https://api-testnet.bybit.com", "wss://stream-testnet.bybit.com/v5/public/linear", environment
        ),
        ("bybit", ExchangeEnvironment.DEMO): ExchangeEndpoints(
            "https://api-demo.bybit.com", "wss://stream-demo.bybit.com/v5/public/linear", environment
        ),
        ("bybit", ExchangeEnvironment.MAINNET_READONLY): ExchangeEndpoints(
            "https://api.bybit.com", "wss://stream.bybit.com/v5/public/linear", environment
        ),
        ("bitmex", ExchangeEnvironment.TESTNET): ExchangeEndpoints(
            "https://testnet.bitmex.com/api/v1", "wss://ws.testnet.bitmex.com/realtime", environment
        ),
        ("bitmex", ExchangeEnvironment.MAINNET_READONLY): ExchangeEndpoints(
            "https://www.bitmex.com/api/v1", "wss://ws.bitmex.com/realtime", environment
        ),
        ("whitebit", ExchangeEnvironment.DEMO): ExchangeEndpoints(
            "https://whitebit.com/api/v4", "wss://api.whitebit.com/ws", environment
        ),
        ("whitebit", ExchangeEnvironment.MAINNET_READONLY): ExchangeEndpoints(
            "https://whitebit.com/api/v4", "wss://api.whitebit.com/ws", environment
        ),
    }
    try:
        return endpoints[(exchange, environment)]
    except KeyError as exc:
        raise ValueError(f"Unsupported environment {environment.value!r} for {exchange!r}") from exc


def configured_environment(exchange: str) -> ExchangeEnvironment:
    raw = os.getenv(f"QUANTFORGE_{exchange.upper()}_ENV", "mainnet-readonly")
    return ExchangeEnvironment(raw.lower())


def assert_no_mainnet_execution(environment: ExchangeEnvironment, submit: bool) -> None:
    if submit:
        raise PermissionError(
            "Order submission is disabled in this release. QuantForge supports simulation, public data, and testnet configuration only."
        )
