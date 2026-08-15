"""Merkmale und Labels fuer die empirische Strukturfrage.

Ausgangspunkt ist nicht mehr das Elliott-Regelwerk, sondern die Frage
dahinter: **traegt die Wellenstruktur ueberhaupt Information ueber Trend und
Momentum hinaus?** Sechs Tests mit vorgegebenen Regeln blieben ohne Nachweis;
statt weitere Regeln vorzugeben, wird das Lattice hier nur noch als
Merkmalsgenerator verwendet und die Gewichtung den Daten ueberlassen.

Der Aufbau ist bewusst als **kontrollierter Vergleich** angelegt:

  Merkmalsgruppe A  Trend, Momentum, Volatilitaet - was jedes gewoehnliche
                    System auch sieht
  Merkmalsgruppe B  Struktur aus dem Pivot-Lattice - Schwunglaengen,
                    Verhaeltnisse, Substrukturzahlen, Lage im uebergeordneten
                    Grad

Nur der **Zuwachs von A nach B** ist Struktur-Information. Ohne diese
Kontrolle wuerde ein Modell schlicht "Ruecksetzer im Aufwaertstrend kaufen"
lernen und das als Wellenanalyse ausgeben.

Alle Merkmale sind streng kausal: der Wert an Bar t nutzt nur Bars <= t.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..pivots.indicators import atr, macd, rsi, squeeze
from ..pivots.lattice import Lattice

# Lattice-Ebenen, aus denen Strukturmerkmale gezogen werden.
FEATURE_SCALES = (2, 3, 4, 5, 6)

TREND_FEATURES = [
    "ret_5", "ret_20", "ret_60", "ret_120",
    "atr_rel", "atr_trend", "rsi", "macd_hist_norm",
    "dist_ma50", "dist_ma200", "vol_rel", "squeeze_on",
    "hi_dist_60", "lo_dist_60",
]

STRUCT_FEATURES = [
    # je Ebene: Richtung, Fortschritt, Retracement, Schwunggroesse, Alter
    *[f"{k}_s{s}" for s in FEATURE_SCALES
      for k in ("dir", "retrace", "swing_atr", "age_rel", "subwaves")],
    # ebenenuebergreifend
    "scale_agree", "swing_ratio_prev", "dur_ratio_prev", "n_scales_up",
]


@dataclass
class Sample:
    bar: int
    ts: pd.Timestamp
    symbol: str
    timeframe: str
    features: dict[str, float]
    label_r: float
    label_hit: int      # 1 = Ziel zuerst, 0 = Stop zuerst, -1 = Zeitablauf
    direction: int


def _trend_features(df: pd.DataFrame) -> pd.DataFrame:
    """Merkmalsgruppe A: was jedes gewoehnliche System sieht."""
    close = df["close"]
    a = atr(df, 14)
    out = pd.DataFrame(index=df.index)

    for n in (5, 20, 60, 120):
        out[f"ret_{n}"] = np.log(close / close.shift(n))

    out["atr_rel"] = a / close
    out["atr_trend"] = a / a.rolling(100, min_periods=20).mean()
    out["rsi"] = rsi(df, 14) / 100.0
    m = macd(df)["hist"]
    out["macd_hist_norm"] = m / a

    ma50 = close.rolling(50, min_periods=10).mean()
    ma200 = close.rolling(200, min_periods=30).mean()
    out["dist_ma50"] = (close - ma50) / a
    out["dist_ma200"] = (close - ma200) / a

    v = df["volume"]
    out["vol_rel"] = v / v.rolling(50, min_periods=10).mean().replace(0, np.nan)
    out["squeeze_on"] = squeeze(df)["on"].astype(float)

    hi60 = df["high"].rolling(60, min_periods=10).max()
    lo60 = df["low"].rolling(60, min_periods=10).min()
    out["hi_dist_60"] = (hi60 - close) / a
    out["lo_dist_60"] = (close - lo60) / a
    return out


def _struct_features_at(lat: Lattice, df: pd.DataFrame, bar: int,
                        atr_arr: np.ndarray) -> dict[str, float]:
    """Merkmalsgruppe B: Struktur aus dem Lattice, streng kausal."""
    f: dict[str, float] = {}
    px = float(df["close"].iloc[bar])
    a = float(atr_arr[bar]) or np.nan
    dirs: list[float] = []

    for s in FEATURE_SCALES:
        piv = [p for p in lat.visible_at(s, bar) if not p.is_anchor]
        if len(piv) < 2:
            for k in ("dir", "retrace", "swing_atr", "age_rel", "subwaves"):
                f[f"{k}_s{s}"] = np.nan
            continue

        p0, p1 = piv[-2], piv[-1]
        swing = p1.price - p0.price
        d = 1.0 if swing > 0 else -1.0
        dirs.append(d)

        f[f"dir_s{s}"] = d
        # Wie weit hat der Kurs den letzten Schwung zurueckgeholt?
        f[f"retrace_s{s}"] = (
            abs(px - p1.price) / abs(swing) if swing != 0 else np.nan
        )
        f[f"swing_atr_s{s}"] = abs(swing) / a if a and np.isfinite(a) else np.nan
        # Alter des laufenden Schwungs relativ zur Dauer des vorigen.
        dur_prev = max(p1.idx - p0.idx, 1)
        f[f"age_rel_s{s}"] = (bar - p1.idx) / dur_prev
        # Substruktur: Teilwellen des letzten Schwungs eine Ebene tiefer.
        if s > 0:
            inner = [q for q in lat.pivots(s - 1)
                     if p0.idx < q.idx < p1.idx and q.confirmed_idx <= bar]
            f[f"subwaves_s{s}"] = len(inner) + 1
        else:
            f[f"subwaves_s{s}"] = np.nan

    # Uebereinstimmung der Richtungen ueber die Ebenen: +1 alle aufwaerts.
    f["scale_agree"] = float(np.mean(dirs)) if dirs else np.nan
    f["n_scales_up"] = float(sum(1 for x in dirs if x > 0))

    # Verhaeltnis des letzten zum vorletzten Schwung auf einer mittleren Ebene.
    mid = [p for p in lat.visible_at(4, bar) if not p.is_anchor]
    if len(mid) >= 3:
        l1 = abs(mid[-1].price - mid[-2].price)
        l0 = abs(mid[-2].price - mid[-3].price)
        d1 = max(mid[-1].idx - mid[-2].idx, 1)
        d0 = max(mid[-2].idx - mid[-3].idx, 1)
        f["swing_ratio_prev"] = l1 / l0 if l0 > 0 else np.nan
        f["dur_ratio_prev"] = d1 / d0
    else:
        f["swing_ratio_prev"] = np.nan
        f["dur_ratio_prev"] = np.nan
    return f


def _triple_barrier(
    df: pd.DataFrame, bar: int, direction: int, stop_dist: float,
    target_r: float, max_bars: int,
) -> tuple[float, int]:
    """Dreifach-Barriere: Ziel, Stop oder Zeitablauf.

    Einstieg auf dem Open der Folgebar. Bei Beruehrung beider Barrieren
    innerhalb einer Bar gilt konservativ der Stop.
    """
    n = len(df)
    e = bar + 1
    if e >= n or stop_dist <= 0:
        return np.nan, -1
    entry = float(df["open"].iloc[e])
    stop = entry - direction * stop_dist
    target = entry + direction * target_r * stop_dist

    hi = df["high"].to_numpy("float64")
    lo = df["low"].to_numpy("float64")
    for i in range(e, min(e + max_bars, n)):
        if (direction > 0 and lo[i] <= stop) or (direction < 0 and hi[i] >= stop):
            return -1.0, 0
        if (direction > 0 and hi[i] >= target) or (direction < 0 and lo[i] <= target):
            return float(target_r), 1
    last = min(e + max_bars, n) - 1
    r = (float(df["close"].iloc[last]) - entry) * direction / stop_dist
    return r, -1


def _forward_excess(
    df: pd.DataFrame, bar: int, direction: int, horizon: int, drift: float,
    stop_dist: float,
) -> float:
    """Trendbereinigte Vorwaertsrendite ueber einen festen Horizont.

    Von der Log-Rendite wird die **Eigendrift des Instruments** ueber
    denselben Zeitraum abgezogen. Damit kann ein Aufwaertstrend per
    Konstruktion nichts mehr beitragen: ein Instrument, das im Mittel
    steigt, liefert bei zufaelligem Einstieg eine Ueberschussrendite von
    null statt eines positiven Beitrags.

    Skaliert wird auf das Risiko (Stop-Abstand), damit die Groesse mit den
    R-Vielfachen der uebrigen Auswertungen vergleichbar bleibt.
    """
    n = len(df)
    e = bar + 1
    j = e + horizon
    if j >= n or stop_dist <= 0:
        return np.nan
    p0 = float(df["open"].iloc[e])
    p1 = float(df["close"].iloc[j])
    if p0 <= 0 or p1 <= 0:
        return np.nan
    raw = np.log(p1 / p0) - drift * horizon
    return direction * raw * p0 / stop_dist


def build(
    lat: Lattice,
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    *,
    step: int = 5,
    target_r: float = 3.0,
    max_bars: int = 120,
    stop_atr: float = 2.0,
    warmup: int = 250,
) -> pd.DataFrame:
    """Baut den Datensatz: ein Sample alle `step` Bars, beide Richtungen.

    Beide Richtungen werden bewusst gleich haeufig erzeugt. Damit kann das
    Modell keinen Richtungsbias aus der Stichprobe ziehen - der Long-Ueberhang
    war in allen frueheren Tests die Hauptquelle scheinbarer Profitabilitaet.
    """
    trend = _trend_features(df)
    a = atr(df, 14)
    atr_arr = a.to_numpy("float64")
    rows: list[dict] = []

    # Eigendrift des Instruments je Bar. Wird fuer das trendbereinigte Label
    # abgezogen. Die Schaetzung ueber die volle Historie ist zwar
    # rueckblickend, wirkt aber nur als konstanter Abzug und kann keine
    # Rangfolge zwischen Samples desselben Instruments erzeugen - sie
    # verschiebt lediglich das Nullniveau.
    logp = np.log(df["close"].to_numpy("float64"))
    drift = float(np.nanmean(np.diff(logp))) if len(logp) > 2 else 0.0

    for bar in range(warmup, len(df) - max_bars - 2, step):
        struct = _struct_features_at(lat, df, bar, atr_arr)
        base = trend.iloc[bar].to_dict()
        stop_dist = stop_atr * float(atr_arr[bar])
        if not np.isfinite(stop_dist) or stop_dist <= 0:
            continue

        for direction in (1, -1):
            r, hit = _triple_barrier(df, bar, direction, stop_dist,
                                     target_r, max_bars)
            if not np.isfinite(r):
                continue
            row = {**base, **struct}
            # Strukturmerkmale sind richtungsabhaengig zu lesen: eine
            # Aufwaertsstruktur ist fuer einen Short das Gegenteil.
            row["direction"] = float(direction)
            for s in FEATURE_SCALES:
                k = f"dir_s{s}"
                if k in row and np.isfinite(row[k]):
                    row[k] = row[k] * direction
            if np.isfinite(row.get("scale_agree", np.nan)):
                row["scale_agree"] *= direction
            for k in ("ret_5", "ret_20", "ret_60", "ret_120",
                      "macd_hist_norm", "dist_ma50", "dist_ma200"):
                if k in row and np.isfinite(row[k]):
                    row[k] = row[k] * direction

            row.update(
                label_r=r, label_hit=hit, bar=bar, ts=df.index[bar],
                symbol=symbol, timeframe=timeframe,
                # Trendbereinigtes Label ueber festen Horizont.
                label_excess=_forward_excess(df, bar, direction, max_bars,
                                             drift, stop_dist),
                # Rohe Vorwaertsrendite, aus der spaeter das Querschnitts-
                # label gebildet wird (Abzug des Marktmittels zur selben Zeit).
                label_fwd=_forward_excess(df, bar, direction, max_bars,
                                          0.0, stop_dist),
            )
            rows.append(row)

    return pd.DataFrame(rows)
