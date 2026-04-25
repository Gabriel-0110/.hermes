"""Exports for trading provider clients and provider profiles."""

from backend.integrations.provider_profiles import PROVIDER_PROFILES
from backend.integrations.macro.fred_client import FredClient
from backend.integrations.market_data.coingecko_client import CoinGeckoClient
from backend.integrations.market_data.coinmarketcap_client import CoinMarketCapClient
from backend.integrations.market_data.twelvedata_client import TwelveDataClient
from backend.integrations.news_sentiment.cryptopanic_client import CryptoPanicClient
from backend.integrations.news_sentiment.newsapi_client import NewsApiClient
from backend.integrations.news_sentiment.lunarcrush_client import LunarCrushClient
from backend.integrations.onchain.bitmart_wallet_client import BitMartWalletAIClient
from backend.integrations.onchain.etherscan_client import EtherscanClient
from backend.integrations.onchain.nansen_client import NansenClient
from backend.integrations.defi.defillama_client import DefiLlamaClient, DefiLlamaEndpointUnavailableError
from backend.integrations.execution.ccxt_client import CCXTExecutionClient
from backend.integrations.notifications.slack_client import SlackNotificationClient
from backend.integrations.notifications.telegram_client import TelegramNotificationClient
from backend.integrations.derivatives.bitmart_public_client import BitMartPublicClient

__all__ = [
    "PROVIDER_PROFILES",
    "FredClient",
    "CoinGeckoClient",
    "CoinMarketCapClient",
    "TwelveDataClient",
    "CryptoPanicClient",
    "NewsApiClient",
    "LunarCrushClient",
    "BitMartWalletAIClient",
    "EtherscanClient",
    "NansenClient",
    "DefiLlamaClient",
    "DefiLlamaEndpointUnavailableError",
    "CCXTExecutionClient",
    "SlackNotificationClient",
    "TelegramNotificationClient",
    "BitMartPublicClient",
]
