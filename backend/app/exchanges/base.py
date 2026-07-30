from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import Candle, MarketDataRequest


class ExchangeAdapterError(RuntimeError):
    pass


class ExchangeAdapter(ABC):
    name: str

    @abstractmethod
    async def fetch_candles(self, request: MarketDataRequest) -> list[Candle]:
        raise NotImplementedError
