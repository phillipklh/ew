#!/usr/bin/env python3
"""Traegt die Wellenstruktur Information ueber Trend und Momentum hinaus?

Das ist die Frage, die nach sechs erfolglosen regelbasierten Tests uebrig
bleibt - und sie laesst sich sauber beantworten, ohne das Elliott-Regelwerk
vorauszusetzen.

Aufbau als kontrollierter Vergleich:

  Modell A   nur Trend, Momentum, Volatilitaet
  Modell B   dieselben Merkmale plus Struktur aus dem Pivot-Lattice

Beide werden mit identischen Hyperparametern und identischen Zeitschnitten
trainiert. **Nur die Differenz zwischen A und B ist Struktur-Information.**
Ohne diese Kontrolle wuerde ein positives Ergebnis lediglich zeigen, dass
Ruecksetzer im Aufwaertstrend funktionieren.

Validierung: Purged + Embargoed Walk-Forward. Da ein Label bis zu `max_bars`
in die Zukunft reicht, muss zwischen Trainings- und Testfenster eine Luecke
genau dieser Laenge liegen - sonst enthaelt das Trainingsset bereits
Information aus dem Testzeitraum, und jedes Ergebnis waere wertlos.

    python scripts/experiment_structure.py --timeframes 1d 4h
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402

from ew import pivots  # noqa: E402
from ew.data import store  # noqa: E402
from ew.ml.dataset import STRUCT_FEATURES, TREND_FEATURES, build  # noqa: E402

MAX_BARS = 120


def make_dataset(timeframes, step) -> pd.DataFrame:
    frames = []
    for tf in timeframes:
        for src, sym, t in store.usable(min_bars=800, timeframes=(tf,),
                                        exclude_holdout=True):
            df = store.load(src, sym, t)
            lat = pivots.build(df)
            d = build(lat, df, sym, t, step=step, max_bars=MAX_BARS)
            if len(d):
                frames.append(d)
    return pd.concat(frames, ignore_index=True).sort_values("ts")


def fit_predict(train, test, feats, seed=0):
    import lightgbm as lgb

    x_tr = train[feats].to_numpy("float32")
    y_tr = train["label_r"].to_numpy("float64")
    x_te = test[feats].to_numpy("float32")

    m = lgb.LGBMRegressor(
        n_estimators=300, learning_rate=0.03, num_leaves=15,
        min_child_samples=80, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.7, reg_lambda=5.0, random_state=seed, verbose=-1,
    )
    m.fit(x_tr, y_tr)
    return m.predict(x_te), m


def walk_forward(data: pd.DataFrame, feats: list[str], n_folds: int = 5):
    """Expandierendes Fenster mit Embargo in Hoehe des Label-Horizonts."""
    ts = data["ts"].to_numpy()
    order = np.argsort(ts)
    data = data.iloc[order].reset_index(drop=True)
    n = len(data)
    fold = n // (n_folds + 1)

    preds = np.full(n, np.nan)
    for k in range(1, n_folds + 1):
        tr_end = fold * k
        te_start, te_end = fold * k, fold * (k + 1)
        # Embargo: alle Trainingssamples entfernen, deren Label in den
        # Testzeitraum hineinreicht.
        cutoff = data["ts"].iloc[te_start]
        tr = data.iloc[:tr_end]
        tr = tr[tr["ts"] < cutoff - pd.Timedelta(days=MAX_BARS)]
        te = data.iloc[te_start:te_end]
        if len(tr) < 500 or len(te) < 100:
            continue
        p, _ = fit_predict(tr, te, feats)
        preds[te_start:te_end] = p
    return data, preds


def report(name, data, preds):
    mask = np.isfinite(preds)
    d, p = data[mask], preds[mask]
    y = d["label_r"].to_numpy("float64")

    rho, p_rho = stats.spearmanr(p, y)
    # Wirtschaftlich relevanter als die Korrelation: was verdient das
    # oberste Dezil der Vorhersagen?
    thr = np.percentile(p, 90)
    top = y[p >= thr]
    thr50 = np.percentile(p, 50)
    top50 = y[p >= thr50]
    print(f"{name:<10}{len(y):>8}{rho:>+9.4f}{p_rho:>9.4f}"
          f"{y.mean():>+10.3f}{top50.mean():>+11.3f}{top.mean():>+11.3f}")
    return {"rho": rho, "p": p_rho, "base": y.mean(),
            "top50": top50.mean(), "top10": top.mean(),
            "y": y, "pred": p, "n": len(y)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeframes", nargs="*", default=["1d"])
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args()

    data = make_dataset(args.timeframes, args.step)
    feats_a = [c for c in TREND_FEATURES if c in data.columns] + ["direction"]
    feats_b = feats_a + [c for c in STRUCT_FEATURES if c in data.columns]

    print(f"Samples: {len(data):,}   Instrumente: {data['symbol'].nunique()}")
    print(f"Zeitraum: {data['ts'].min().date()} .. {data['ts'].max().date()}")
    print(f"Merkmale A: {len(feats_a)}   B: {len(feats_b)}")
    print(f"Basis-Erwartung (alle Samples): {data['label_r'].mean():+.3f} R\n")

    print(f"{'Modell':<10}{'n_test':>8}{'rho':>9}{'p':>9}"
          f"{'alle':>10}{'top50%':>11}{'top10%':>11}")
    print("-" * 68)

    d_a, p_a = walk_forward(data, feats_a, args.folds)
    ra = report("A Trend", d_a, p_a)
    d_b, p_b = walk_forward(data, feats_b, args.folds)
    rb = report("B +Struktur", d_b, p_b)

    print("\n=== Zuwachs durch Strukturmerkmale ===")
    for key, label in (("rho", "Rangkorrelation"), ("top50", "Top-50 %-Erwartung"),
                       ("top10", "Top-10 %-Erwartung")):
        print(f"  {label:<24}{ra[key]:>+9.4f} -> {rb[key]:>+9.4f}"
              f"   Delta {rb[key] - ra[key]:+.4f}")

    # Signifikanz des Unterschieds im obersten Dezil.
    ya, yb = ra["y"], rb["y"]
    ta = ya[ra["pred"] >= np.percentile(ra["pred"], 90)]
    tb = yb[rb["pred"] >= np.percentile(rb["pred"], 90)]
    diff = tb.mean() - ta.mean()
    se = np.sqrt(ta.var(ddof=1) / len(ta) + tb.var(ddof=1) / len(tb))
    print(f"\n  Top-Dezil B gegen A: {diff:+.3f} R   "
          f"t = {diff / se if se > 0 else np.nan:.2f}")

    # Die entscheidende Kontrolle: ist die Edge richtungssymmetrisch?
    # Ein Vorsprung, der nur auf der Long-Seite entsteht, ist Trendumfeld
    # und Survivorship-Bias, kein Modellwissen.
    print("\n=== Richtungskontrolle (Modell A, oberstes Dezil) ===")
    dd = d_a.copy()
    mask = np.isfinite(p_a)
    dd = dd[mask].copy()
    dd["pred"] = p_a[mask]
    thr = np.percentile(dd["pred"], 90)
    top = dd[dd["pred"] >= thr]
    print(f"  Long-Anteil  Top-Dezil {(top['direction'] > 0).mean():.1%}   "
          f"gesamt {(dd['direction'] > 0).mean():.1%}")
    print(f"{'Richtung':<10}{'n':>7}{'Top':>10}{'Basis':>10}{'Lift':>9}{'t':>7}")
    print("-" * 53)
    for k, nm in ((1, "long"), (-1, "short")):
        x = top.loc[top["direction"] == k, "label_r"].to_numpy()
        b = dd.loc[dd["direction"] == k, "label_r"].to_numpy()
        if len(x) < 30:
            continue
        lift = x.mean() - b.mean()
        se = np.sqrt(x.var(ddof=1) / len(x) + b.var(ddof=1) / len(b))
        print(f"{nm:<10}{len(x):>7}{x.mean():>+10.3f}{b.mean():>+10.3f}"
              f"{lift:>+9.3f}{lift / se if se > 0 else np.nan:>7.2f}")

    eq = {"AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "^GSPC", "^NDX"}
    print(f"\n{'Anlageklasse':<16}{'n':>7}{'Top':>10}{'Basis':>10}{'Lift':>9}")
    print("-" * 52)
    for grp, nm in ((True, "Aktien/Indizes"), (False, "Krypto")):
        x = top.loc[top["symbol"].isin(eq) == grp, "label_r"].to_numpy()
        b = dd.loc[dd["symbol"].isin(eq) == grp, "label_r"].to_numpy()
        if len(x) < 30:
            continue
        print(f"{nm:<16}{len(x):>7}{x.mean():>+10.3f}{b.mean():>+10.3f}"
              f"{x.mean() - b.mean():>+9.3f}")

    # Merkmalswichtigkeit des vollstaendigen Modells auf allen Daten.
    _, model = fit_predict(data.iloc[: int(len(data) * 0.8)],
                           data.iloc[int(len(data) * 0.8):], feats_b)
    imp = pd.Series(model.feature_importances_, index=feats_b).sort_values(
        ascending=False)
    print("\n=== Wichtigste Merkmale (Modell B) ===")
    for k, v in imp.head(15).items():
        tag = "Struktur" if k in STRUCT_FEATURES else "Trend"
        print(f"  {k:<22}{v:>7}  [{tag}]")

    share = sum(v for k, v in imp.items() if k in STRUCT_FEATURES) / imp.sum()
    print(f"\n  Anteil der Strukturmerkmale an der Gesamtwichtigkeit: {share:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
