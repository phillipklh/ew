"""Handelsuniversum.

Die Breite ist kein Komfortmerkmal, sondern eine Anforderung aus der
Risikorechnung: fuer +100 %/Jahr bei 1 % Risiko braucht es ~40-100 Trades
pro Jahr, waehrend ein einzelnes Asset im Daily-Grad nur ~5-15 Setups
liefert. Ohne Portfolio-Breite ist das Renditeziel arithmetisch unerreichbar.

`cluster` dient spaeter dem Korrelations-Cap im Risiko-Layer: zehn
gleichzeitige Krypto-Longs sind ein 10-%-Bet, kein 1-%-Bet.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Instrument:
    symbol: str
    source: str  # "binance" | "yfinance"
    cluster: str  # Korrelationsgruppe
    name: str


UNIVERSE: list[Instrument] = [
    # --- Krypto (Binance, volle Historie ab 2017) ---
    Instrument("BTCUSDT", "binance", "crypto_major", "Bitcoin"),
    Instrument("ETHUSDT", "binance", "crypto_major", "Ethereum"),
    Instrument("SOLUSDT", "binance", "crypto_alt", "Solana"),
    Instrument("LINKUSDT", "binance", "crypto_alt", "Chainlink"),
    Instrument("BNBUSDT", "binance", "crypto_alt", "BNB"),
    Instrument("ADAUSDT", "binance", "crypto_alt", "Cardano"),
    Instrument("AVAXUSDT", "binance", "crypto_alt", "Avalanche"),
    Instrument("DOTUSDT", "binance", "crypto_alt", "Polkadot"),
    Instrument("XRPUSDT", "binance", "crypto_alt", "XRP"),
    Instrument("LTCUSDT", "binance", "crypto_alt", "Litecoin"),

    # --- Rohstoffe (yfinance Futures) ---
    Instrument("GC=F", "yfinance", "metals", "Gold"),
    Instrument("SI=F", "yfinance", "metals", "Silber"),
    Instrument("HG=F", "yfinance", "metals", "Kupfer"),
    Instrument("CL=F", "yfinance", "energy", "WTI Rohoel"),
    Instrument("NG=F", "yfinance", "energy", "Erdgas"),

    # --- Aktien & Indizes ---
    Instrument("^GSPC", "yfinance", "equity_index", "S&P 500"),
    Instrument("^NDX", "yfinance", "equity_index", "Nasdaq 100"),
    Instrument("AAPL", "yfinance", "equity_tech", "Apple"),
    Instrument("MSFT", "yfinance", "equity_tech", "Microsoft"),
    Instrument("NVDA", "yfinance", "equity_tech", "Nvidia"),
    Instrument("AMZN", "yfinance", "equity_tech", "Amazon"),
    Instrument("META", "yfinance", "equity_tech", "Meta"),
    Instrument("GOOGL", "yfinance", "equity_tech", "Alphabet"),
    Instrument("TSLA", "yfinance", "equity_tech", "Tesla"),
    Instrument("JPM", "yfinance", "equity_fin", "JPMorgan"),
]

# 4h fehlt bei yfinance nativ und wird aus 1h abgeleitet.
TIMEFRAMES = ["15m", "1h", "4h", "1d"]

# Assets, die nie ins Training/Tuning fliessen und ausschliesslich fuer den
# finalen Out-of-Sample-Test reserviert sind. Diese Trennung ist der einzige
# echte Schutz gegen Overfitting ueber viele Iterationen hinweg.
HOLDOUT = {"LTCUSDT", "DOTUSDT", "NG=F", "JPM", "GOOGL"}


def by_source(source: str) -> list[Instrument]:
    return [i for i in UNIVERSE if i.source == source]


def training_universe() -> list[Instrument]:
    return [i for i in UNIVERSE if i.symbol not in HOLDOUT]


def holdout_universe() -> list[Instrument]:
    return [i for i in UNIVERSE if i.symbol in HOLDOUT]


def get(symbol: str) -> Instrument:
    for i in UNIVERSE:
        if i.symbol == symbol:
            return i
    raise KeyError(f"Unbekanntes Symbol: {symbol}")
