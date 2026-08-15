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

## F4 — Das Dreieck braucht die Überlappungsbedingung

Ohne die Bedingung, dass jedes Extrem innerhalb des übernächsten bleibt
(kontrahierend) bzw. darüber hinausgeht (expandierend), ging nahezu jede
Seitwärtsbewegung als Dreieck durch. Nach Ergänzung fällt die Zahl der
Dreieck-Labelings auf BTCUSDT 1d von **333 auf 39** (−88 %), ohne dass ein
Regel-Test bricht. Konvergenz der Begrenzungslinien allein — die im Buch
genannte Konstruktion über die Endpunkte von a/c und b/d — reicht als
Kriterium nicht aus.
