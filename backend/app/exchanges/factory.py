from app.exchanges.base import ExchangeAdapter
from app.exchanges.bitmex import BitMEXAdapter
from app.exchanges.hyperliquid import HyperliquidAdapter
from app.exchanges.synthetic import SyntheticAdapter
from app.models import ExchangeName


def get_exchange_adapter(exchange: ExchangeName) -> ExchangeAdapter:
    adapters: dict[ExchangeName, ExchangeAdapter] = {
        ExchangeName.HYPERLIQUID: HyperliquidAdapter(),
        ExchangeName.BITMEX: BitMEXAdapter(),
        ExchangeName.SYNTHETIC: SyntheticAdapter(),
    }
    return adapters[exchange]
