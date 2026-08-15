"""Surrogat-Serien als Nullmodell.

Die Frage "treten Fibonacci-Verhaeltnisse haeufiger auf als zufaellig?" ist
ohne Vergleichsmassstab nicht beantwortbar. Eine gemessene Trefferquote von
30 % klingt hoch, ist aber bedeutungslos, wenn schon die blosse Breite der
Toleranzbaender 30 % des Wertebereichs abdeckt.

Zwei Bezugsgroessen werden deshalb gebraucht:

1. **Geometrische Abdeckung** - welchen Anteil des Wertebereichs ueberdecken
   die Toleranzbaender ueberhaupt? Das ist die Trefferquote bei
   Gleichverteilung.
2. **Surrogat-Serien** - dieselbe Pipeline auf Kursreihen, die dieselben
   statistischen Eigenschaften haben (Renditeverteilung, Volatilitaets-
   clusterung, Bar-Geometrie), aber keine echte Wellenstruktur. Der
   Block-Bootstrap erhaelt kurzfristige Abhaengigkeiten und zerstoert die
   langreichweitige Struktur - genau das, was eine Elliott-Welle waere.

Ist die Trefferquote auf echten Daten nicht hoeher als auf Surrogaten, sind
die Fibonacci-Richtlinien kein verwertbares Signal und gehoeren nicht in die
Bewertungsfunktion.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def block_bootstrap(
    df: pd.DataFrame, *, block: int = 50, seed: int = 0
) -> pd.DataFrame:
    """Erzeugt eine Surrogat-Serie per Block-Bootstrap der Bar-Geometrie.

    Erhalten bleiben: Verteilung der Log-Renditen, Volatilitaetsclusterung
    innerhalb der Bloecke, sowie das Verhaeltnis von High/Low/Open zum Close.
    Zerstoert wird die Abfolge der Bloecke - und damit jede Wellenstruktur,
    die laenger als ein Block ist.
    """
    rng = np.random.default_rng(seed)
    n = len(df)
    if n < block * 2:
        raise ValueError(f"Serie zu kurz ({n}) fuer Blocklaenge {block}")

    close = df["close"].to_numpy("float64")
    logret = np.diff(np.log(close), prepend=np.log(close[0]))

    # Relative Lage von Open/High/Low zum Close derselben Bar.
    rel_o = df["open"].to_numpy("float64") / close
    rel_h = df["high"].to_numpy("float64") / close
    rel_l = df["low"].to_numpy("float64") / close
    vol = df["volume"].to_numpy("float64")

    n_blocks = int(np.ceil(n / block))
    starts = rng.integers(0, n - block, size=n_blocks)
    idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]

    new_ret = logret[idx]
    new_ret[0] = 0.0
    new_close = close[0] * np.exp(np.cumsum(new_ret))

    out = pd.DataFrame(
        {
            "open": new_close * rel_o[idx],
            "high": new_close * rel_h[idx],
            "low": new_close * rel_l[idx],
            "close": new_close,
            "volume": vol[idx],
        },
        index=df.index[:n],
    )
    out.index.name = df.index.name

    # Bar-Geometrie erzwingen: High und Low muessen Open/Close umschliessen.
    out["high"] = out[["open", "high", "low", "close"]].max(axis=1)
    out["low"] = out[["open", "high", "low", "close"]].min(axis=1)
    return out
