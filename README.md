# EW — Automatisierte Elliott-Wave-Analyse

Operationalisierung des Elliott-Wave-Regelsatzes zu handelbaren Signalen über
Krypto, Aktien und Rohstoffe.

## Warum die üblichen Ansätze scheitern

Fünf Fehlermodi, die dieses Projekt gezielt adressiert:

| # | Fehlermodus | Lösung hier |
|---|---|---|
| 1 | Fester ZigZag-Schwellwert → Labels kippen bei jedem Volatilitätsregime | Multi-Scale-Lattice, ATR-normiert |
| 2 | **Repainting/Lookahead** → Backtest glänzt, Live versagt | Strikte Trennung `idx` / `confirmed_idx` |
| 3 | Kombinatorische Explosion der Zählungen | Hard-Rule-Pruning + Beam Search |
| 4 | Suche nach dem „einen richtigen Count" | Rangierte Verteilung über Top-K-Hypothesen |
| 5 | Overfitting auf Fibonacci-Toleranzen | Purged Walk-Forward + Deflated Sharpe |

Fehlermodus 2 ist der stillste und teuerste. Deshalb trägt **jeder** Pivot zwei
Zeitpunkte: den Bar seines Extremwerts und den Bar, ab dem er überhaupt bekannt
sein kann. Nur letzterer darf in Signale einfließen.

## Kernidee: Zyklusgrad ≠ Timeframe

Ein Wochen-Pivot mit anderem Preis als der Daily-Pivot ist kein Marktphänomen,
sondern ein Artefakt des Resamplings. Hier werden Pivots **genau einmal** auf der
feinsten Serie berechnet; jede gröbere Ebene entsteht rekursiv aus der feineren
und ist damit per Konstruktion eine echte Teilmenge — gleicher Preis, gleicher
Zeitpunkt. Der Zyklusgrad ist eine Ebene in diesem Baum, relativ vergeben.

## Struktur

```
ew/
  data/      Quellen (Binance, yfinance), Normalisierung, Parquet-Store, Integritätschecks
  pivots/    ATR-ZigZag, Multi-Scale-Lattice, kausale Indikatoren
  rules/     Harte EW-Regeln als prüfbare Prädikate
  labeling/  Hypothesen-Enumeration, Beam Search, Gradzuweisung
  scoring/   Guideline-Priors, Scoring, Ranking
  forecast/  Zielzonen, Invalidierung, Entry-Zonen
  backtest/  Kausaler Backtest, Purged Walk-Forward
  risk/      Positionsgrößen, Portfolio-Heat, Korrelations-Cluster
  live/      Scanner, Alerts
  viz/       Chart-Rendering für visuelles Audit
```

## Setup

```bash
pip install -e ".[dev]"
```

Daten laden (liegen bewusst außerhalb des Repos, siehe `.gitignore`):

```bash
python scripts/fetch_data.py
```

Verzögerungsanalyse je Lattice-Ebene:

```bash
python scripts/analyze_lag.py
```

## Datenquellen

| Quelle | Abdeckung | Status |
|---|---|---|
| Binance REST | Krypto, volle Historie ab 2017-08, alle TFs | aktiv |
| yfinance | Aktien, Indizes, Futures | aktiv (IP-Rate-Limit, geduldiger Backoff) |
| Stooq | — | verworfen: JS-Bot-Prüfung |

Marktdaten liegen nicht im Repo. Reproduzierbarkeit stellt `data/manifest.json`
her: zu jedem Datensatz Inhalts-Hash, Zeitraum und Bar-Anzahl.

## Status

- [x] **M0** Datenpipeline, Store, Integritätschecks
- [x] **M1** Pivot-Lattice, Kausalitäts-Invarianten, Chart-Rendering
- [ ] **M2** Harte Regel-Engine + Beam Search
- [ ] **M3** Guideline-Priors + Scoring
- [ ] **M4** Signalgenerierung + Backtest — *Go/No-Go-Gate*
- [ ] **M5** Outcome-Modell
- [ ] **M6** Portfolio-/Risiko-Layer
- [ ] **M7** Live-Scanner + Alerts
