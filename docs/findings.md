# Befunde

Laufendes Protokoll gemessener Ergebnisse. Aufgenommen wird nur, was aus den
Daten folgt — nicht, was plausibel klingt.

---

## F1 — Die Bestätigungsverzögerung ist skaleninvariant

**Gemessen** über 20 Datensätze (BTC/ETH/SOL/LINK/BNB, Timeframes 15m–1d),
`scripts/analyze_lag.py`.

Ein Pivot ist erst bekannt, wenn die Gegenbewegung den Schwellwert gerissen
hat. Die Frage ist, wie groß diese Verzögerung im Verhältnis zur Dauer der
Welle selbst ist:

| Ebene | θ (ATR) | Median-Lag | Median-Dauer | **Lag / Dauer** | Median-Move |
|---|---|---|---|---|---|
| 0 | 0.50 | 1 | 2 | 0.50 | 2.3 % |
| 1 | 0.75 | 3 | 2 | 1.50 | 2.6 % |
| 2 | 1.10 | 5 | 3 | 1.67 | 3.4 % |
| 3 | 1.60 | 10 | 5 | 2.00 | 4.8 % |
| 4 | 2.40 | 18 | 11 | 1.64 | 7.2 % |
| 5 | 3.60 | 39 | 26 | 1.47 | 11.0 % |
| 6 | 5.40 | 88 | 65 | 1.35 | 18.0 % |
| 7 | 8.10 | 211 | 167 | 1.29 | 28.9 % |

**Der Quotient liegt auf allen acht Ebenen zwischen 1.3 und 2.0 (Median 1.49).**

### Was daraus folgt

Die Bestätigung eines Wendepunkts trifft im Median rund **1,5-mal so spät ein,
wie die Welle überhaupt gedauert hat** — die Bewegung ist zum Zeitpunkt ihrer
Bestätigung also längst vorbei. Und zwar auf *jeder* Skala gleichermaßen.

Das ist kein Kalibrierungsproblem, das sich durch einen besseren Schwellwert
lösen ließe. Es ist eine strukturelle Folge der Selbstähnlichkeit: verkleinert
man die Skala, schrumpfen Verzögerung und Wellendauer im gleichen Verhältnis.

Zwei Konsequenzen:

**1. Keine einzelne Ebene ist für sich handelbar.** Wer auf die Bestätigung des
Pivots in dem Grad wartet, den er handeln will, kommt systematisch zu spät.

**2. Der Top-down-Ansatz ist damit nicht Stilfrage, sondern zwingend.** Der
Kontext muss aus einer groben Ebene kommen, der Auslöser aus einer feinen:
eine laufende Hypothese auf Ebene *k* liefert Richtung, Invalidierung und Ziel,
während die Bestätigung auf Ebene *k−2* oder *k−3* den Einstieg auslöst. Genau
das tut ein erfahrener Elliott-Analyst intuitiv, wenn er den Wochenchart für
die These und den 4h-Chart für den Einstieg nutzt.

### Warum das erklärt, dass naive EW-Backtests scheitern

Eine übliche Implementierung verwendet den Extrempunkt des ZigZag, sobald er im
Chart sichtbar ist. Damit unterschlägt sie eine Verzögerung in der
Größenordnung der Wellendauer selbst — das Ergebnis sieht hervorragend aus und
ist im Livebetrieb nicht reproduzierbar. Deshalb trägt hier jeder Pivot beide
Zeitpunkte (`idx` und `confirmed_idx`), und die Signallogik darf ausschließlich
den zweiten sehen.

---

## F2 — Regelkonforme Mehrdeutigkeit ist massiv und nicht wegregelbar

**Gemessen** auf BTCUSDT 1d, 3.285 Bars, `enumerate_complete`.

Zahl der Labelings, die *alle* harten Regeln erfüllen:

| Ebene | Impuls | Diagonalen | Zigzag | Flat | Dreieck | **Summe** |
|---|---|---|---|---|---|---|
| 3 | 44 | 36 | 127 | 253 | 39 | **499** |
| 4 | 18 | 16 | 67 | 113 | 13 | **227** |
| 5 | 8 | 8 | 26 | 50 | 9 | **101** |

Allein auf Ebene 3 sind 499 verschiedene Zählungen regelkonform. Die Suche nach
der *einen richtigen* ist damit gegenstandslos — die harten Regeln schränken
zwar stark ein, determinieren aber nicht.

Auffällig ist die Verteilung: **Korrekturen (Flat 253, Zigzag 127) dominieren
die motiven Muster (Impuls 44) um eine Größenordnung.** Das ist kein Artefakt,
sondern spiegelt die Regellage: für Impulse nennt das Buch vier scharfe Regeln,
für Flats im Kern nur eine (B retraciert A zu mindestens ~90 %). Dass sich
Elliott-Analysten überwiegend über Korrekturen streiten, ist also im Regelwerk
selbst angelegt.

**Konsequenz:** Die Reduktion muss aus Substruktur-Konsistenz und gelerntem
Scoring kommen. Zusätzliche „Regeln" zu erfinden, die im Buch nicht stehen,
wäre Überanpassung in Regelform.

---

## F3 — Die Regel „Welle 3 ist nie die kürzeste" braucht Log-Längen

Das Buch formuliert sie prozentual („a greater percentage movement"). Über
Historien mit vervielfachtem Kursniveau — BTC von 3.000 auf 120.000 — ist der
arithmetische Vergleich irreführend: eine späte Welle wirkt allein durch das
Preisniveau riesig. Auf arithmetischer Basis würde die Regel systematisch
falsche Zählungen verwerfen und gültige durchlassen. Implementiert über
`geometry.log_lengths`, abgesichert durch einen Test mit prozentual
konsistenten, arithmetisch widersprüchlichen Wellen.

---

## F5 — Fibonacci-Verhältnisse sind in diesen Daten kein verwertbares Signal

**Das ist der Befund mit den weitreichendsten Folgen für den Plan.**

**Gemessen** auf 30 integritätsgeprüften Datensätzen (Krypto + Gold, 4h/1d,
Holdout ausgeschlossen), 63.138 regelkonforme Labelings gegen 189.585
Labelings aus Block-Bootstrap-Surrogaten. `scripts/test_fibonacci.py`.

Verglichen wird die Trefferquote nahe eines Fibonacci-Levels (±5 % relativ)
gegen zwei Bezugsgrößen: **Surrogate** mit identischer Renditestatistik, aber
ohne Wellenstruktur, und die **geometrische Abdeckung** — der Anteil des
Wertebereichs, den die Toleranzbänder ohnehin überdecken.

| Kennzahl | n | beobachtet | Surrogat | Abdeckung | Lift | z |
|---|---|---|---|---|---|---|
| w2_retrace_w1 | 10.274 | 31,6 % | 32,3 % | 31,1 % | 0.98 | −1.4 |
| w4_retrace_w3 | 10.289 | 38,4 % | 38,2 % | 34,7 % | 1.01 | 0.5 |
| w3_ext_w1 | 10.278 | 37,0 % | 35,7 % | 20,9 % | 1.03 | 2.2 |
| w5_ext_w1 | 10.298 | 18,3 % | 16,8 % | 23,4 % | 1.09 | **3.3** |
| w5_ext_w3 | 10.281 | 9,8 % | 10,1 % | 34,0 % | 0.97 | −0.8 |
| b_retrace_a | 51.702 | 13,0 % | 13,0 % | 5,0 % | 1.00 | −0.1 |
| c_ext_a | 51.832 | 31,8 % | 32,2 % | 19,1 % | 0.99 | −1.5 |

**Median-Lift: 1.00.**

Beispiel zur Lesart: w2 liegt in 31,6 % der Fälle nahe einem Fib-Retracement.
Das klingt nach einem starken Effekt — bis man sieht, dass die Toleranzbänder
31,1 % des Wertebereichs überdecken und das strukturlose Surrogat auf 32,3 %
kommt. Die Treffer entstehen also vollständig durch die Bandbreite der
Toleranz, nicht durch Wellenstruktur.

### Robustheitsprüfung

Naheliegender Einwand: der Test läuft über *alle* regelkonformen Labelings,
von denen die meisten falsch sind — ein echtes Signal könnte darin untergehen.
Auf die Teilmenge mit **perfekter Substruktur-Konsistenz** eingeschränkt
(n = 3.195) steigt der Median-Lift nur auf 1.06, und kein z-Wert übersteht die
Bonferroni-Korrektur. Der Befund ist also nicht ein Artefakt der falschen
Labelings.

### Was das heißt — und was nicht

Einzig `w5_ext_w1` übersteht die Korrektur für Mehrfachtests (z = 3.3 gegen
Schwelle 2.69). Der Effekt ist mit +1,5 Prozentpunkten allerdings so klein,
dass er als Merkmal einer Handelsentscheidung nicht trägt.

**Nicht** gezeigt ist, dass Fibonacci-Level *keinerlei* Rolle spielen. Getestet
wurde die unbedingte Häufung von Verhältniszahlen an Fib-Levels. Nicht
getestet ist, ob ein Fib-Level *bedingt auf eine korrekte Zählung*
Prognosewert für den weiteren Verlauf hat — das beantwortet erst das
Outcome-Modell über Forward-Payoff.

**Gezeigt ist:** Das Merkmal „Verhältnis liegt nahe einem Fibonacci-Level"
ist als Bestandteil der Bewertungsfunktion durch diese Daten nicht
gerechtfertigt. Es einzubauen hieße, Rauschen zu gewichten.

### Folge für den Plan

Die ursprünglich für M3 vorgesehenen Fibonacci-Priors entfallen als
Score-Bestandteil. Die Bewertungsfunktion stützt sich stattdessen auf die
Größen, die messbar Information tragen:

- **Substruktur-Konsistenz** — zerfällt jede Welle in die erwartete Unterteilung
- **Label-Stabilität** — kippt die Zählung, wenn eine Bar dazukommt
- **Forward-Payoff** — wird das projizierte Ziel vor der Invalidierung erreicht

Das ist keine Verkleinerung des Vorhabens, sondern die Vermeidung einer
teuren Sackgasse: eine auf Fibonacci gestützte Bewertung hätte im Backtest
plausibel ausgesehen und wäre live wirkungslos gewesen.

---

## F6 — WTI hat negative Preise, und Integritätsbefunde müssen erzwungen werden

`CL=F` (WTI) enthält am 20./21. April 2020 **negative Settlement-Preise**
(Minimum −37,63). Für ein log-basiertes Framework ist das fatal: `log(-37,63)`
ist NaN, und ein NaN-Vergleich macht jede Regelprüfung still zu `False` —
Muster würden unbemerkt durchgewinkt statt verworfen.

Zwei Lehren:

1. `geometry.log_lengths` fällt bei nicht-positiven Preisen explizit auf
   arithmetische Längen zurück, statt still NaN zu erzeugen.
2. Der Integritätscheck hatte den Datensatz korrekt als fehlerhaft markiert
   (`integrity_ok=False`) — aber die Auswertung hat ihn trotzdem verwendet,
   weil sie nur nach Bar-Anzahl filterte. **Ein Prüfsystem, dessen Ergebnis
   die Auswertungen ignorieren, ist wirkungslos.** Deshalb gibt es jetzt
   `store.usable()`, das zwingend auf `integrity_ok` filtert; Auswertungen
   greifen nicht mehr direkt auf das Manifest zu.

Nebenbefund: `CL=F 1d` enthält zusätzlich 7 Bars, bei denen High/Low die
Open/Close-Spanne nicht umschließen — eine Datenqualitätsschwäche der Quelle.

---

## F4 — Das Dreieck braucht die Überlappungsbedingung

Ohne die Bedingung, dass jedes Extrem innerhalb des übernächsten bleibt
(kontrahierend) bzw. darüber hinausgeht (expandierend), ging nahezu jede
Seitwärtsbewegung als Dreieck durch. Nach Ergänzung fällt die Zahl der
Dreieck-Labelings auf BTCUSDT 1d von **333 auf 39** (−88 %), ohne dass ein
Regel-Test bricht. Konvergenz der Begrenzungslinien allein — die im Buch
genannte Konstruktion über die Endpunkte von a/c und b/d — reicht als
Kriterium nicht aus.

---

## F7 — Die erste Signalversion zeigt **keine** nachweisbare Edge

**Das ist das Go/No-Go-Ergebnis für M4 — und es fällt negativ aus.**

**Gemessen** auf 16 Instrumenten (Krypto + Aktien + Indizes), Timeframe 1d,
746 Trades, Kontextebenen 4/5/6, Trigger-Offset 2, Ziel 3R, Breakeven ab 1R,
10 bps Kosten je Seite. `scripts/backtest.py`, `scripts/test_edge.py`.

### Der Backtest allein sieht brauchbar aus

| Kennzahl | Wert |
|---|---|
| Erwartungswert | +0,218 R / Trade |
| Trefferquote | 38,2 % |
| Ø Gewinn / Ø Verlust | +1,68 R / −0,69 R |
| Summe | +162,5 R |
| positive Instrumente | 13 von 16 |

Der mittlere Verlust von −0,69 R zeigt, dass der Breakeven-Mechanismus wirkt —
die Voraussetzung der Drawdown-Rechnung ist konstruktiv erreichbar.

### Der Placebo-Test entzieht dem die Grundlage

Ein positiver Backtest belegt für sich nichts. Auf einem Universum aus Aktien
im Säkularaufwärtstrend erzeugt jedes long-lastige System Gewinne. Also:
zu jedem echten Signal 20 Placebo-Trades auf demselben Instrument, in
derselben Richtung, mit demselben relativen Stop-Abstand und derselben
Ausstiegsregel — nur zu einem **zufälligen Zeitpunkt**. Alles bleibt gleich
außer der Information über den Einstiegszeitpunkt.

| Richtung | n | echt | Placebo | Differenz | t |
|---|---|---|---|---|---|
| long | 445 | +0,637 R | **+0,502 R** | +0,134 | 1.89 |
| short | 301 | −0,401 R | **−0,311 R** | −0,090 | −1.74 |
| **gesamt** | 746 | +0,218 R | +0,162 R | **+0,056** | **1.10** |

**Kein signifikanter Unterschied.** Der Placebo verdient auf der Long-Seite
+0,502 R allein dadurch, dass das Universum gestiegen ist. Die gesamte
scheinbare Profitabilität erklärt sich aus zwei Quellen, die nichts mit
Elliott zu tun haben: dem Richtungsübergewicht (445 Long gegen 301 Short) und
dem Trendumfeld der getesteten Instrumente.

Hinzu kommt Survivorship-Bias: AAPL, NVDA, TSLA und META sind die Gewinner
von heute. Ein long-lastiges System darauf zu testen, ist strukturell
optimistisch.

### Zusätzlich: die Frequenz reicht bei weitem nicht

Auf 1d erzeugt das System **2–3 Trades pro Instrument und Jahr**. Für die
Zielrendite werden **70 R pro Jahr** gebraucht; erreicht werden bei
+0,218 R/Trade rund **0,5 R pro Instrument-Jahr**. Selbst wenn die Edge echt
wäre, bräuchte es dafür über hundert unkorrelierte Instrumente — was die
Drawdown-Vorgabe wieder sprengen würde.

### Was daraus folgt — und was nicht

**Kein Urteil über die Elliott-Wellen-Theorie.** Getestet wurde *diese eine,
bewusst einfache Signalversion*: feste Kontextebenen, fester Trigger-Offset,
festes 3R-Ziel — und **ohne jede Qualitätsbewertung**. Jedes regelkonforme
Setup wurde genommen, unabhängig von Substruktur, Stabilität oder Rang.

**Klares Urteil über den nächsten Schritt.** Es wäre falsch, jetzt an
Parametern zu drehen, bis die Zahlen stimmen — bei dieser Zahl an
Stellschrauben findet sich immer eine Kombination, und der Placebo-Test würde
sie sofort wieder entlarven. Sinnvoll ist genau eine Frage:

> Sagt die *Qualität* einer Zählung (Substruktur-Konsistenz, Label-Stabilität,
> Rang) den Ausgang des Trades vorher?

Trifft das zu, liegt die Edge in der Selektion, nicht im Setup-Typ — und der
Placebo-Test muss auf der selektierten Teilmenge erneut bestanden werden.
Trifft es nicht zu, ist die These in dieser Form widerlegt, und das ist ein
Ergebnis, kein Scheitern.

### Nebenbefund: Auswertungsfehler, der das Bild verzerrt hätte

Die erste Fassung der Portfoliobewertung rechnete Trades pro Jahr über
Bar-Indizes eines beliebigen Referenzinstruments. Da der S&P 500 bis 1927
zurückreicht und ADA erst 2018 beginnt, wurde die Handelsfrequenz um etwa das
Zwölffache überschätzt (90 statt 7,6 Trades/Jahr). `Trade` trägt jetzt echte
Zeitstempel, und die Auswertung rechnet auf Kalenderbasis.
