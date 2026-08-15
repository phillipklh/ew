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

---

## F8 — Die Richtlinien-Hypothese hält nicht

**Gemessen** auf 6.501 Trades über 1d/4h/1h, 25 Instrumente, Training-Universum.
`scripts/test_quality.py`.

Getestete Annahme: *Je mehr Richtlinien eine Zählung zusätzlich zu den
Pflichtregeln erfüllt, desto besser das Setup.* Neun zum Signalzeitpunkt
messbare Richtlinien (Substruktur von Welle 1 und 2, Retracement-Band,
Zeitverhältnis, Volumenkontraktion, Momentum-Schub, Divergenz, Zustimmung der
höheren Ebene, relative Wellengröße).

Bewusst **nicht** als Schwellwertsuche ausgelegt: bei genug Kandidaten findet
sich immer einer, der gut aussieht. Geprüft wurde die stärkere Aussage —
steigt die Erwartung *monoton* mit dem Score?

| Timeframe | n | Erwartung | Spearman rho | p |
|---|---|---|---|---|
| 1d | 746 | +0,218 R | +0,009 | 0,81 |
| 4h | 1.213 | +0,116 R | +0,003 | 0,91 |
| 1h | 4.542 | +0,048 R | −0,029 | 0,05 |

**Kein monotoner Zusammenhang.** Auf 1h ist die Tendenz sogar leicht negativ.
In der kombinierten Auswertung über 1d+4h hatte die höchste Qualitätsstufe
(Score 7) die *schlechteste* Erwartung (−0,087 R).

Keine einzelne Richtlinie übersteht die Bonferroni-Korrektur (|t| > 2,77).
Der größte Wert ist `w2_ist_drei` mit t = −2,59 — und das mit *negativem*
Vorzeichen. `korrektur_kuerzer` sah auf 1d allein noch signifikant aus
(t = 2,97), fällt über den größeren Datensatz auf t = 0,74: ein Lehrstück
dafür, warum Einzeltimeframe-Befunde nichts wert sind.

Nebenbeobachtung: Die Erwartung **sinkt** mit steigender Frequenz
(1d +0,218 → 4h +0,116 → 1h +0,048 R). Das passt zur Placebo-Erklärung aus
F7 — auf kürzeren Horizonten ist weniger Trend zum Mitnehmen da, während die
Kosten gleich bleiben. Die Frequenz lässt sich also nicht einfach durch
schnellere Timeframes erkaufen.

---

## F9 — Der engere „taktische" Stop verschlechtert das Ergebnis

**Gemessen** auf 36 Instrument/Timeframe-Kombinationen (1d + 4h),
`scripts/test_fractal_entry.py`.

Getestete Annahme: *Wer für einen 1d-Trade in den 15m-Chart schaut, findet
einen präziseren Einstieg — und kann den Stop enger setzen, was dieselbe
Bewegung ein Vielfaches an R wert macht.*

Verglichen: Stop hinter dem Start von Welle 1 (`rule`, Regel-Invalidierung)
gegen Stop knapp hinter dem auslösenden feinen Pivot (`trigger`).

| Stop | Offset | n | Erwartung | Trefferquote | Ø Gewinn |
|---|---|---|---|---|---|
| rule | 1 | 2.029 | **+0,205 R** | 37,2 % | +1,64 R |
| rule | 2 | 1.959 | +0,155 R | 36,8 % | +1,57 R |
| rule | 3 | 2.066 | +0,179 R | 37,6 % | +1,54 R |
| trigger | 1 | 3.568 | +0,098 R | 26,2 % | +2,35 R |
| trigger | 2 | 4.251 | −0,004 R | 23,3 % | +2,53 R |
| trigger | 3 | 6.570 | **−0,110 R** | 20,8 % | +2,66 R |

Der Mechanismus funktioniert genau wie erwartet — der Ø Gewinn steigt von
+1,64 R auf +2,66 R. Aber die Trefferquote fällt von 37 % auf 21 %, und der
Tausch geht **netto verloren**: die Differenz ist mit t = −2,69 bis −5,70
klar signifikant negativ. Tiefere Auflösung verschlechtert das Ergebnis
zusätzlich.

**Einschränkung, die fair genannt werden muss:** Die Ausstiegsregel wurde
nicht mitangepasst. Bei einem engen Stop ist 1R eine sehr kleine Bewegung,
sodass die Breakeven-Regel fast sofort greift und Gewinner ausbremst. Der
Test zeigt also: *dieser* enge Stop mit *dieser* Ausstiegsregel trägt nicht.
Ob eine gemeinsam angepasste Kombination trägt, ist offen — aber das ist eine
Parametersuche, und die müsste erneut gegen den Placebo bestehen.

---

## Zwischenstand: vier unabhängige Tests, kein Edge-Nachweis

| Test | Frage | Ergebnis |
|---|---|---|
| F5 Fibonacci | Häufen sich Fib-Verhältnisse? | Lift 1,00 — nein |
| F7 Placebo | Schlägt das Timing den Zufall? | +0,056 R, t = 1,10 — nein |
| F8 Richtlinien | Sagt Qualität den Ausgang vorher? | rho ≈ 0 — nein |
| F9 Fraktal-Stop | Zahlt sich der engere Stop aus? | t = −5,70 — nein, im Gegenteil |

**Was das nicht ist:** kein Urteil über die Elliott-Wellen-Theorie und keine
Aussage über diskretionäres Trading. Der manuelle Analyst bringt Kontext ein,
den keiner dieser Tests abbildet.

**Was es ist:** Der bisher automatisierte Teil — Pivot-Erkennung, Regelprüfung,
Setup-Typ, Richtlinien-Score, Stop-Wahl — erklärt die Ergebnisse nicht. Was
den Unterschied macht, liegt außerhalb dessen, was bisher formalisiert wurde.

**Ungetestet und damit offen:**
- Die Ausstiegsregel ist grob (fixes 3R-Ziel, Breakeven bei 1R). Ein Analyst
  managt Ausstiege laufend anhand der sich entwickelnden Struktur.
- Nur das Setup „nach Welle 2 in Welle 3" wird gehandelt — nicht Welle 4→5,
  nicht Korrekturmuster, nicht Diagonalen-Abschlüsse.
- Kein Outcome-Modell: bisher wird jedes regelkonforme Setup gleich gewichtet,
  statt die Erfolgswahrscheinlichkeit aus Merkmalen zu lernen.
- Das Holdout-Universum ist unberührt.

---

## F10 — Das Zonen-System ist besser, aber der Vorsprung hält der Datenmenge nicht stand

**Gemessen** auf 16 Instrumenten (1d) bzw. 32 Kombinationen (1d + 4h),
Training-Universum. `scripts/backtest_zones.py`, `scripts/test_edge_zones.py`.

### Der Architekturwechsel war richtig

Die Beschreibung des tatsächlichen Vorgehens hat einen Grundfehler
offengelegt: gebaut war ein **Bestätigungssystem**, das auf den belegten
Wendepunkt wartet. Der Analyst wartet aber nicht — er projiziert die Zone und
legt eine Limit-Order hinein.

Das erklärt die vorherigen Negativbefunde rückwirkend:

- Befund F1 (Bestätigung trifft ~1,5-mal so spät ein wie die Welle dauert)
  ist für ein Limit-System **bedeutungslos**, war für das Bestätigungssystem
  aber der Killer.
- Das Risiko hängt an der Zonenbreite statt an Welle 1.
- Der Placebo-Test in F7 prüfte das Timing *nach* Bestätigung. Die Edge liegt,
  wenn überhaupt, in der Zonenprognose — es wurde die falsche Sache getestet.

Und die Wirkung ist messbar: der durchschnittliche Gewinn steigt von **+1,68 R
auf +2,44 R**, die Erwartung von +0,218 auf +0,306 R. Der Mechanismus greift
genau wie vorhergesagt.

### Der Placebo-Test entzieht dem trotzdem die Grundlage

| Datensatz | n | echt | Placebo (gewichtet) | Differenz | t |
|---|---|---|---|---|---|
| 1d | 553 | +0,306 R | +0,143 R | +0,162 R | **1,91** |
| 1d + 4h | 1.170 | +0,207 R | +0,120 R | **+0,087 R** | **1,64** |

Auf 1d allein lag die Differenz knapp unter der Signifikanzschwelle. Daraus
ergab sich eine testbare Vorhersage: *ist der Effekt echt, steigt t mit mehr
Daten; ist er Rauschen, fällt er.* Bei verdoppelter Stichprobe hätte t auf
etwa 2,7 steigen müssen — tatsächlich **fiel er auf 1,64**, und die
Effektgröße halbierte sich. Das ist die Signatur von Rauschen.

### Methodischer Hinweis: das Simpson-Paradox war real

Der rohe Vergleich ergab +0,212 R bei t = 2,49 — scheinbar signifikant. Der
Long-Anteil unterschied sich aber zwischen echt (60,2 %) und Placebo (55,1 %),
weil die Fill-Quoten je Richtung abweichen. Da Longs im getesteten Universum
verdienen und Shorts verlieren, entstand der Unterschied teilweise allein aus
dem Mix. Richtungsgewichtet blieben +0,162 R bei t = 1,91.

**Ohne diese Korrektur hätte hier ein signifikantes Ergebnis gestanden, das
keines ist.** Der Test berichtet seither beide Werte.

### Was jetzt noch fehlt — und zwar substanziell

Der wichtigste Teil des beschriebenen Vorgehens ist **noch nicht
implementiert**: die Zerlegung der Korrektur in eine **W-X-Y-Kombination**
(z. B. Flat–ZigZag–ZigZag) und die Projektion des Y-Endes aus der internen
5-3-5-Struktur des abschließenden ZigZags, abgeglichen über drei Zyklusgrade.

Was hier getestet wurde, ist deutlich gröber: ein Retracement-Band von Welle 1
(0,382–0,618) plus drei grobe Stützprojektionen. Die beschriebene Präzision
entsteht aber gerade dadurch, dass die Zielzone aus der *Substruktur der
Korrektur selbst* projiziert wird — aus der c-Welle des Y, deren 5-Teilung und
der 5-der-5 —, nicht aus einem Standardband der übergeordneten Welle.

Es gibt in der Regel-Engine bislang **kein Kombinationsmuster (W-X-Y)**. Das
ist die größte verbliebene Lücke zwischen Modell und beschriebener Praxis.

### Nebenbefund: der Squeeze wirkt umgekehrt

Entgegen der Erwartung liefern Setups mit aktivem Squeeze eine **schlechtere**
Erwartung (+0,082 R gegen +0,344 R ohne). Bevor daraus etwas folgt, ist
allerdings ein Implementierungsdetail zu prüfen: der Squeeze wird derzeit zum
Zeitpunkt der *Orderstellung* erfasst, nicht zum Zeitpunkt der *Ausführung* —
und dazwischen können bis zu 60 Bars liegen. Der Befund ist damit vorerst
nicht belastbar.

---

## F11 — Die W-X-Y-Zerlegung verschlechtert das Ergebnis, je genauer sie wird

**Gemessen** auf 16 Instrumenten (1d), Training-Universum.
`ew/forecast/substructure_signals.py`.

Umgesetzt wurde die beschriebene Praxis: Zerlegung der Korrektur in ihre
Teilwellen (3 = einfach, 7 = W-X-Y, 11 = dreifach nach Lesson 9), Projektion
der laufenden Schlusswelle (c = a bzw. 1,618 a), zusätzliche Projektion der
fünften Teilwelle der c, und Schnitt dieser Projektionen mit dem
Retracement-Band der übergeordneten Welle.

### Der Verlauf über vier Ausbaustufen

| Variante | Trefferquote | Ø Gewinn | Erwartung |
|---|---|---|---|
| Einfaches Band 0,382–0,618 (F10) | 38,3 % | +2,44 R | **+0,306 R** |
| Substruktur, Stop an der Schnittzone | 16,6 % | +6,23 R | −0,048 R |
| Substruktur, Stop am weiten Band | 25,5 % | +3,44 R | +0,096 R |
| Substruktur + korrekte W-X-Y-Erkennung | 23,9 % | +3,38 R | **+0,007 R** |

**Je genauer die Zerlegung, desto schlechter das Ergebnis.** Das ist nicht
das Muster, das entstünde, wenn die Umsetzung nur knapp danebenläge — dann
wäre eine Verbesserung mit jeder Korrektur zu erwarten.

Ebenso gegenläufig: mehr Konfluenz ist schlechter. Setups mit drei
übereinstimmenden Projektionen liefern −0,299 R, solche mit zweien +0,034 R.

### Zwei echte Korrekturen unterwegs

**Der Stop gehört nicht an die Schnittzone.** Erste Umsetzung setzte ihn
knapp unter den Schnitt der Projektionen. Das ergab eine sehr enge
Verlustbegrenzung und dadurch beeindruckende Gewinne (+6,23 R im Schnitt),
aber eine Trefferquote von nur 16,6 % — normales Rauschen reißt einen so
engen Stop. Richtig ist: Einstieg an der Schnittzone (Präzision), Stop unter
dem weiten Band 0,618–1,0 (Robustheit).

**Kosten dominieren bei engen Stops.** Der durchschnittliche Verlust lag bei
−1,30 R statt −1,00 R. Das ist kein Buchungsfehler: bei einem Risiko von
1,7 % des Kurses macht ein Round-Trip von 20 bps bereits 12 % des Risikos aus.
Wer den Stop verengt, um das R-Vielfache zu heben, kauft sich Kostendrag ein,
der genau dort am stärksten wirkt, wo er am wenigsten auffällt.

**Und ein Fehler in der Zerlegung selbst:** die erste Fassung nahm die
gröbste Ebene mit mindestens zwei Teilwellen und ließ dadurch fast jede
Kombination wie eine einfache Korrektur aussehen — nur 30 von 318 Strukturen
wurden als W-X-Y erkannt. Nach der Korrektur (Vorzug für kanonische
Wellenzahlen 3/7/11) sind es 666 von 2.194. Das Ergebnis wurde dadurch nicht
besser, sondern schlechter.

---

## Gesamtbild: sechs unabhängige Tests, kein Edge-Nachweis

| Test | Frage | Ergebnis |
|---|---|---|
| F5 | Häufen sich Fibonacci-Verhältnisse? | Lift 1,00 |
| F7 | Schlägt Bestätigungs-Timing den Zufall? | t = 1,10 |
| F8 | Sagt Richtlinien-Qualität den Ausgang vorher? | rho ≈ 0 |
| F9 | Zahlt sich der engere Fraktal-Stop aus? | t = −5,70 |
| F10 | Schlägt die Zonenprognose den Zufall? | t = 1,64 |
| F11 | Verbessert die W-X-Y-Zerlegung? | nein, verschlechtert |

Auffällig ist die Richtung: **jede zusätzliche Verfeinerung machte das
Ergebnis schlechter, nicht besser.** Bei einem Verfahren, das im Kern trägt
und nur ungenau umgesetzt ist, wäre das umgekehrte Muster zu erwarten.

Was durchgehend bleibt, ist die Asymmetrie zwischen Long und Short
(+0,57 R gegen −0,41 R in F11, ähnlich in allen anderen Tests). Sie ist in
jedem getesteten Aufbau vorhanden und lässt sich vollständig durch das
Trendumfeld des Universums erklären — sie ist kein Wellenphänomen.

**Was damit nicht widerlegt ist:** die diskretionäre Komponente. Die
Beschreibung des Vorgehens nennt sie an erster Stelle — „dabei kommt es auch
mehr oder weniger auf mein Gefühl an, ob ich einen Trade nehmen möchte".
Genau dieser Teil ist in keinem der sechs Tests enthalten, weil er nicht
formalisiert wurde.

---

## F12 — Es gibt Prognosekraft, aber sie ist Marktbeta, nicht Struktur

**Der abschließende Test**, und der aussagekräftigste. `scripts/experiment_structure.py`.

Nach sechs erfolglosen regelbasierten Tests wurde das Elliott-Regelwerk
fallengelassen und das Lattice nur noch als **Merkmalsgenerator** verwendet.
Zwei Modelle, identische Hyperparameter, identische Zeitschnitte, Purged +
Embargoed Walk-Forward über 38.292 Samples (16 Instrumente, 1928–2026):

- **A** — Trend, Momentum, Volatilität
- **B** — dasselbe plus 29 Strukturmerkmale aus dem Lattice

Labels über Dreifach-Barriere (Ziel 3R, Stop 2 ATR, Zeitgrenze 120 Bars),
beide Richtungen gleich häufig erzeugt.

### Ergebnis 1: Strukturmerkmale bringen keinen Zuwachs

| Kennzahl | Modell A | Modell B | Delta |
|---|---|---|---|
| Rangkorrelation | +0,1517 | +0,1460 | **−0,006** |
| Erwartung Top-50 % | +0,335 R | +0,327 R | −0,008 |
| Erwartung Top-10 % | +0,435 R | +0,483 R | +0,048 (t = 0,99) |

Bemerkenswert: das Modell **nutzt** die Strukturmerkmale intensiv — sie
stellen 53,3 % der Gesamtwichtigkeit, mit `age_rel_s6`, `swing_atr_s6` und
`retrace_s6` unter den stärksten. Out-of-sample übersetzt sich das in nichts.
Genau so sieht es aus, wenn Merkmale beim Anpassen helfen und beim
Vorhersagen nicht.

### Ergebnis 2: Die gesamte Prognosekraft ist Richtungswahl

Beide Modelle sagen hochsignifikant vorher (rho = 0,15, p < 0,0001), und das
oberste Dezil verdient +0,44 R gegen +0,08 R Basis — das Fünffache. Die
Richtungskontrolle löst das auf:

**Der Long-Anteil im obersten Dezil beträgt 97,0 %** (Stichprobe: 50,0 %).

| Richtung | n | Top-Dezil | Basis derselben Richtung | Lift | t |
|---|---|---|---|---|---|
| long | 3.096 | +0,456 R | **+0,413 R** | +0,043 | 1,14 |
| short | 95 | −0,233 R | −0,255 R | +0,022 | 0,14 |

Zufällig long zu gehen bringt in diesem Universum bereits **+0,413 R**.
Bedingt auf die Richtung fügt das Modell +0,043 R hinzu — statistisch nicht
unterscheidbar von null.

Nach Anlageklasse betrachtet stammt der Effekt entsprechend aus dem
Trendumfeld: Aktien/Indizes +0,471 R gegen +0,079 R Basis, Krypto +0,324 R
gegen +0,078 R.

### Was das heißt

Die Frage „haben die Trades Zukunft?" hat damit eine unangenehm klare
Antwort: **Prognosekraft ja — aber es ist Marktbeta.** Das Modell hat gelernt,
in einem Universum long zu gehen, das 98 Jahre lang gestiegen ist. Das ist
keine Strategie, das ist Risikoprämie, und sie ist mit einem Indexkauf
billiger zu haben.

Weder Trend- noch Strukturmerkmale liefern *innerhalb einer Richtung*
verwertbare Information. Für die Strukturmerkmale gilt das doppelt: sie
verbessern nicht einmal gegenüber dem reinen Trendmodell.

### Der eine verbleibende saubere Test

Das getestete Universum ist von Beta dominiert — der S&P 500 reicht bis 1927
zurück. Ein Test auf **trendbereinigten Daten** (Überschussrendite gegenüber
dem eigenen gleitenden Mittel oder gegenüber dem Index) würde diese Erklärung
konstruktiv ausschließen: dort kann ein Aufwärtsdrift per Konstruktion nichts
mehr beitragen, und übrig bliebe allein die Frage, ob die Struktur relative
Bewegungen vorhersagt.

Das ist der einzige Test, der nach diesen zwölf Befunden noch etwas anderes
zeigen könnte als das bisherige Bild.

---

## F13 — Trendbereinigt: kein Signal, und der eine positive Befund hält dem Holdout nicht stand

**Der abschließende Test.** `scripts/experiment_structure.py --label ...`

Befund F12 ließ eine Erklärung offen: das Universum ist von Marktbeta
dominiert. Also dieselbe Analyse mit zwei trendbereinigten Labels.

### Bereinigung 1: Eigendrift entfernt (`label_excess`)

Von der Vorwärtsrendite wird die instrumentspezifische Drift über denselben
Zeitraum abgezogen. Basis-Erwartung danach exakt **+0,0000** — die
Bereinigung greift per Konstruktion.

| Modell | rho | p | Top-10 % |
|---|---|---|---|
| A Trend | +0,0020 | 0,72 | +0,127 |
| B +Struktur | **−0,0254** | <0,0001 | −0,172 |

Ohne Drift hat **auch das Trendmodell keine Prognosekraft mehr** (p = 0,72).
Die Strukturmerkmale machen es signifikant schlechter (Top-Dezil −0,299,
t = −2,75) — die Signatur eines Modells, das in der Anpassung Muster findet,
die sich out-of-sample umkehren.

### Bereinigung 2: zusätzlich Marktbewegung entfernt (`label_xs`)

Hier wird zusätzlich abgezogen, was alle Instrumente zum selben Zeitpunkt
gemeinsam getan haben. Übrig bleibt die relative Bewegung — das, was ein
marktneutrales Long/Short-Buch vereinnahmt.

| Modell | rho | p | Top-50 % | Top-10 % |
|---|---|---|---|---|
| A Trend | +0,034 | 0,005 | +0,054 | −0,050 |
| **B +Struktur** | **+0,076** | <0,0001 | +0,177 | +0,239 |

**Erstmals ein positiver Strukturbeitrag:** die Rangkorrelation verdoppelt
sich. Die Richtungskontrolle ist sauber (52,2 % Long im obersten Dezil), was
bei einem marktneutralen Label auch so sein muss.

### Der Holdout entscheidet — negativ

Genau für diesen Moment blieben fünf Instrumente über die gesamte Entwicklung
unberührt. Trainiert auf den bekannten, getestet auf den reservierten:

| Modell | n | rho | p | Top-10 % |
|---|---|---|---|---|
| A Trend | 5.404 | −0,007 | 0,63 | −0,408 |
| **B +Struktur** | 5.404 | **−0,106** | <0,0001 | **−0,776** |

Auf ungesehenen Instrumenten sind die Vorhersagen des Strukturmodells
**negativ korreliert** mit dem Ausgang. Der Befund aus dem Trainingsuniversum
repliziert nicht — er kehrt sich um.

Das ist keine Nullaussage, sondern eine stärkere: das Modell hat etwas
gelernt, das auf den Trainingsinstrumenten gilt und anderswo das Gegenteil
bewirkt. Genau das ist Überanpassung, und genau dafür war das Holdout
reserviert.

### Damit ist die Frage beantwortet

Über acht unabhängige Testanlagen hinweg — regelbasiert wie gelernt,
bestätigend wie antizipativ, mit und ohne Trendbereinigung, mit und ohne
Marktneutralisierung — findet sich **kein Strukturbeitrag, der out-of-sample
Bestand hat.** Der einzige positive Befund verschwand beim ersten echten
Generalisierungstest.

Die Prognosekraft, die in F12 sichtbar war, ist vollständig Marktbeta: sie
verschwindet, sobald die Drift entfernt wird.

### Was ausdrücklich nicht gezeigt ist

Getestet wurde eine bestimmte Formalisierung auf einem bestimmten Universum:
Pivot-Lattice als Strukturbeschreibung, 25 Instrumente, Tagesdaten,
Dreifach-Barriere-Labels, feste Haltedauern. Nicht getestet ist die
diskretionäre Ebene — die Auswahl, welche Situation überhaupt handelbar ist,
das laufende Positionsmanagement und die Instrumentenwahl.

Die dokumentierte manuelle Performance wird durch diese Befunde weder erklärt
noch widerlegt. Gezeigt ist allein: **die hier formalisierten Teile erklären
sie nicht.**

---

## F14 — Unter Funding-Bedingungen: Frequenz ist der Engpass, nicht die Trefferquote

**Gemessen** auf der empirischen R-Verteilung des Zonen-Systems (1.170 Trades,
1d + 4h), Monte-Carlo über 20.000 Pfade. `scripts/challenge_analysis.py`.

### Die Arithmetik des Ziels

20 % pro Monat entsprechen **18,3 R pro Monat** bei 1 % Risiko (792 % p. a.).

Das System erzeugt über das gesamte Portfolio hinweg **12 Trades pro Jahr** —
also einen pro Monat. Bei einer Erwartung von +0,207 R sind das **0,21 R
monatlich**.

**Faktor 89.**

Der Engpass ist damit eindeutig identifiziert und er ist nicht die
Trefferquote, sondern die **Frequenz**. Selbst eine doppelt so gute Erwartung
änderte an der Größenordnung nichts.

### Challenge-Simulation

Ziel 10 %, max. Drawdown 10 %, Tageslimit 5 %, 60 Tage. Bezugsgröße ohne jede
Edge: 50 % (Verhältnis der Barriereabstände).

| Risiko/Trade | bestanden | DD-Aus | Zeit-Aus |
|---|---|---|---|
| 1,0 % | 0,7 % | 0,0 % | **99,3 %** |
| 2,0 % | 10,8 % | 0,9 % | 88,4 % |
| 3,0 % | 20,2 % | 9,6 % | 70,3 % |
| 5,0 % | 32,0 % | 62,5 % | 5,5 % |

**Auf keinem Risikoniveau erreicht das System die 50 % eines edgelosen
Zufallspfads.** Der Grund steht in der Spalte „Zeit-Aus": bei vernünftigem
Risiko laufen 88–99 % der Pfade schlicht aus der Zeit, weil in 60 Tagen nur
etwa zwei Trades stattfinden. Wer das Risiko so weit anhebt, dass die Zeit
reicht, verliert stattdessen am Drawdown-Limit (62,5 % bei 5 %).

Das ist die typische Falle eines Barriereproblems mit zu wenigen Ereignissen:
Es existiert kein Risikoniveau, das beide Barrieren gleichzeitig respektiert.

### Realistisch erreichbare Monatsrendite

| Risiko/Trade | pro Monat | pro Jahr |
|---|---|---|
| 1 % | +0,21 % | +2,5 % |
| 2 % | +0,41 % | +5,0 % |
| 5 % | +1,03 % | +13,0 % |

### Warum sich das nicht durch mehr Frequenz lösen lässt

Naheliegender Einwand: schnellere Timeframes erzeugen mehr Trades. Befund F8
hat das bereits gemessen — die Erwartung **sinkt** mit steigender Frequenz
(1d +0,218 → 4h +0,116 → 1h +0,048 R), weil die Kosten gleich bleiben,
während die Bewegungen kleiner werden.

Rechnet man großzügig mit 1h-Frequenz (180 Trades/Monat bei +0,048 R), ergibt
das 8,6 R monatlich statt der nötigen 18,3 — und diese Erwartung war im
Placebo-Test ebenfalls nicht von Zufall unterscheidbar.

**Es gibt in dieser Strategieklasse keine Parameterkombination, die das Ziel
erreicht.** Das ist keine Frage der Kalibrierung, sondern der Größenordnung.
