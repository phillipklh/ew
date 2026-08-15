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


def make_dataset(timeframes, step, include_holdout=False) -> pd.DataFrame:
    frames = []
    for tf in timeframes:
        for src, sym, t in store.usable(min_bars=800, timeframes=(tf,),
                                        exclude_holdout=not include_holdout):
            df = store.load(src, sym, t)
            lat = pivots.build(df)
            d = build(lat, df, sym, t, step=step, max_bars=MAX_BARS)
            if len(d):
                frames.append(d)
    data = pd.concat(frames, ignore_index=True).sort_values("ts")
    return _add_cross_sectional(data)


def _add_cross_sectional(data: pd.DataFrame) -> pd.DataFrame:
    """Querschnittsbereinigtes Label: Abzug der gleichzeitigen Marktbewegung.

    Waehrend `label_excess` nur die Eigendrift des Instruments entfernt,
    entfernt dieses Label zusaetzlich das, was zur selben Zeit alle
    Instrumente gemeinsam getan haben. Damit koennen weder ein
    Saekulartrend noch eine gemeinsame Faktorbewegung (Risk-on-Phasen,
    Krypto-Zyklen) noch etwas beitragen - uebrig bleibt allein die relative
    Bewegung eines Instruments gegenueber seinen Vergleichswerten.

    Das ist zugleich das, was ein marktneutrales Long/Short-Buch
    tatsaechlich vereinnahmt.
    """
    up = data[data["direction"] > 0]
    # Marktmittel je Zeitpunkt, gebildet aus der Long-Sicht.
    mkt = up.groupby("ts")["label_fwd"].mean().rename("mkt")
    data = data.merge(mkt, left_on="ts", right_index=True, how="left")
    n_per_ts = up.groupby("ts").size().rename("n_ts")
    data = data.merge(n_per_ts, left_on="ts", right_index=True, how="left")
    data["label_xs"] = data["label_fwd"] - data["direction"] * data["mkt"]
    # Zeitpunkte mit nur einem Instrument liefern kein sinnvolles Marktmittel.
    data.loc[data["n_ts"] < 3, "label_xs"] = np.nan
    return data


LABEL = "label_r"


def fit_predict(train, test, feats, seed=0):
    import lightgbm as lgb

    x_tr = train[feats].to_numpy("float32")
    y_tr = train[LABEL].to_numpy("float64")
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
    y = d[LABEL].to_numpy("float64")

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


def _holdout_test(data: pd.DataFrame) -> int:
    """Training auf bekannten, Test auf reservierten Instrumenten.

    Der schaerfste verfuegbare Test: die Holdout-Instrumente wurden waehrend
    der gesamten Entwicklung nie angefasst. Haelt ein Effekt hier, ist er
    nicht das Ergebnis der vielen Entscheidungen, die unterwegs am
    Trainingsuniversum getroffen wurden.
    """
    from ew.data.universe import HOLDOUT

    feats_a = [c for c in TREND_FEATURES if c in data.columns] + ["direction"]
    feats_b = feats_a + [c for c in STRUCT_FEATURES if c in data.columns]

    tr = data[~data["symbol"].isin(HOLDOUT)]
    te = data[data["symbol"].isin(HOLDOUT)]
    print(f"Label: {LABEL}")
    print(f"Training  {len(tr):,} Samples, {tr['symbol'].nunique()} Instrumente")
    print(f"Holdout   {len(te):,} Samples, {te['symbol'].nunique()} Instrumente: "
          f"{sorted(te['symbol'].unique())}")
    print(f"Basis-Erwartung Holdout: {te[LABEL].mean():+.4f}\n")

    print(f"{'Modell':<12}{'n':>8}{'rho':>9}{'p':>9}{'top50%':>11}{'top10%':>11}")
    print("-" * 60)
    res = {}
    for name, feats in (("A Trend", feats_a), ("B +Struktur", feats_b)):
        pred, _ = fit_predict(tr, te, feats)
        y = te[LABEL].to_numpy("float64")
        rho, p_rho = stats.spearmanr(pred, y)
        t50 = y[pred >= np.percentile(pred, 50)]
        t10 = y[pred >= np.percentile(pred, 90)]
        res[name] = (rho, t10, y)
        print(f"{name:<12}{len(y):>8}{rho:>+9.4f}{p_rho:>9.4f}"
              f"{t50.mean():>+11.4f}{t10.mean():>+11.4f}")

    (_, a10, _), (_, b10, _) = res["A Trend"], res["B +Struktur"]
    d = b10.mean() - a10.mean()
    se = np.sqrt(a10.var(ddof=1) / len(a10) + b10.var(ddof=1) / len(b10))
    print(f"\n  Top-Dezil B gegen A: {d:+.4f}   "
          f"t = {d / se if se > 0 else np.nan:.2f}")
    print("\n  Die Holdout-Instrumente waren waehrend der gesamten")
    print("  Entwicklung nie Teil einer Auswertung.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeframes", nargs="*", default=["1d"])
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--holdout-test", action="store_true",
                    help="Auf Trainingsinstrumenten trainieren, auf den "
                         "reservierten Holdout-Instrumenten testen")
    ap.add_argument("--label", default="label_r",
                    choices=["label_r", "label_excess", "label_xs"],
                    help="label_r = Dreifach-Barriere (enthaelt Drift), "
                         "label_excess = Eigendrift entfernt, "
                         "label_xs = zusaetzlich Marktbewegung entfernt")
    args = ap.parse_args()
    global LABEL
    LABEL = args.label

    data = make_dataset(args.timeframes, args.step,
                        include_holdout=args.holdout_test)
    data = data[np.isfinite(data[LABEL])].reset_index(drop=True)

    if args.holdout_test:
        return _holdout_test(data)
    feats_a = [c for c in TREND_FEATURES if c in data.columns] + ["direction"]
    feats_b = feats_a + [c for c in STRUCT_FEATURES if c in data.columns]

    print(f"Samples: {len(data):,}   Instrumente: {data['symbol'].nunique()}")
    print(f"Zeitraum: {data['ts'].min().date()} .. {data['ts'].max().date()}")
    print(f"Merkmale A: {len(feats_a)}   B: {len(feats_b)}")
    print(f"Label: {LABEL}")
    print(f"Basis-Erwartung (alle Samples): {data[LABEL].mean():+.4f}")
    for k, nm in ((1, "long"), (-1, "short")):
        x = data.loc[data["direction"] == k, LABEL]
        print(f"    {nm}: {x.mean():+.4f}  (n={len(x):,})")
    print()

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
        x = top.loc[top["direction"] == k, LABEL].to_numpy()
        b = dd.loc[dd["direction"] == k, LABEL].to_numpy()
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
        x = top.loc[top["symbol"].isin(eq) == grp, LABEL].to_numpy()
        b = dd.loc[dd["symbol"].isin(eq) == grp, LABEL].to_numpy()
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
