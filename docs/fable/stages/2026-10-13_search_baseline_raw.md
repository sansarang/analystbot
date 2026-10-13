# 🔴🔴 §6-7 검색 품질 **기준선**(고치기 전 숫자)

저장된 카드 **49장**(머리를 읽은 것만) · 결장 주장을 적은 카드 45장

   … 1/49 Levante UD vs Sevilla FC
   … 2/49 Levante UD vs Sevilla FC
   … 3/49 Elche CF vs RC Celta de Vigo
   … 4/49 Elche vs Celta Vigo
   … 5/49 Genoa CFC vs ACF Fiorentina
   … 6/49 Gwangju FC vs Ulsan HD FC
   … 7/49 Gwangju FC vs Ulsan HD FC
   … 8/49 Hull City AFC vs Everton FC
   … 9/49 Iwaki FC vs Blaublitz Akita
   … 10/49 JEF United Chiba vs V-Varen Nagasaki
   … 11/49 JEF United Chiba vs V-Varen Nagasaki
   … 12/49 Kawasaki Frontale vs Nagoya Grampus
   … 13/49 Kawasaki Frontale vs Nagoya Grampus
   … 14/49 Kawasaki Frontale vs Nagoya Grampus
   … 15/49 Kawasaki Frontale vs Nagoya Grampus
   … 16/49 Kawasaki Frontale vs Nagoya Grampus
   … 17/49 Los Angeles FC vs Vancouver Whitecaps
   … 18/49 Los Angeles FC vs Vancouver Whitecaps
   … 19/49 Los Angeles FC vs Vancouver Whitecaps
   … 20/49 Los Angeles FC vs Vancouver Whitecaps
   … 21/49 Los Angeles FC vs Vancouver Whitecaps
   … 22/49 Los Angeles FC vs Vancouver Whitecaps
   … 23/49 Los Angeles FC vs Vancouver Whitecaps
   … 24/49 Los Angeles FC vs Vancouver Whitecaps
   … 25/49 Los Angeles FC vs Vancouver Whitecaps
   … 26/49 Los Angeles FC vs Vancouver Whitecaps
   … 27/49 Los Angeles FC vs Vancouver Whitecaps
   … 28/49 Los Angeles FC vs Vancouver Whitecaps
   … 29/49 Los Angeles FC vs Vancouver Whitecaps
   … 30/49 Los Angeles FC vs Vancouver Whitecaps
   … 31/49 Los Angeles FC vs Vancouver Whitecaps
   … 32/49 Minnesota United vs Houston Dynamo FC
   … 33/49 Mito Hollyhock vs Shimizu S-Pulse
   … 34/49 Orlando City vs Columbus Crew
   … 35/49 Nice vs Strasbourg
   … 36/49 OGC Nice vs RC Strasbourg Alsace
   … 37/49 Crystal Palace FC vs Nottingham Forest FC
   … 38/49 Levante UD vs Sevilla FC
   … 39/49 New England Revolution vs Seattle Sounders FC
   … 40/49 New England Revolution vs Seattle Sounders FC
   … 41/49 Shonan Bellmare vs Albirex Niigata
   … 42/49 Shonan Bellmare vs Albirex Niigata
   … 43/49 Shonan Bellmare vs Albirex Niigata
   … 44/49 Sporting Kansas City vs Portland Timbers
   … 45/49 Sporting Kansas City vs Portland Timbers
   … 46/49 São Paulo FC vs EC Vitória
   … 47/49 Levante UD vs Sevilla FC
   … 48/49 Arsenal vs Lille
   … 49/49 Levante UD vs Sevilla FC

| 리그 | 쪽 | 실제 결장 | 카드 주장 | 맞은 것 | 재현율 | 정밀도 |
|---|---|---|---|---|---|---|
| Campeonato Brasileiro Série | 2 | 9 | 17 | 2 | **22.2%** | 11.8% |
| J. League | 16 | 56 | 12 | 6 | **10.7%** | 50.0% |
| J. League 2 | 8 | 26 | 12 | 5 | **19.2%** | 41.7% |
| K-League 1 | 4 | 8 | 2 | 1 | **12.5%** | 50.0% |
| LaLiga | 2 | 7 | 5 | 2 | **28.6%** | 40.0% |
| Major League Soccer | 36 | 134 | 150 | 22 | **16.4%** | 14.7% |
| Premier League | 2 | 3 | 9 | 0 | **0.0%** | 0.0% |
| Serie | 2 | 8 | 8 | 3 | **37.5%** | 37.5% |

🔴 **전체 — 재현율 16.3%(41/251) · 정밀도 19.1%(41/215)**

## 🔴 손실 깔때기 — 정답을 **만들지 못한** 까닭

- 5건 — 🔴 `Levante UD` 일정에 2026-10-13 경기가 없다(받은 
- 2건 — 🔴 `New England Revolution` 일정에 2026-10-1
- 1건 — 🔴 `RC Celta de Vigo` 일정에 2026-10-11 경기가 
- 1건 — 🔴 `Orlando City` 일정에 2026-10-11 경기가 없다(받
- 1건 — 🔴 `Strasbourg` 일정에 2026-10-11 경기가 없다(받은 
- 1건 — 🔴 `RC Strasbourg Alsace` 일정에 2026-10-11 
- 1건 — 🔴 `Crystal Palace FC` 일정에 2026-10-11 경기가
- 1건 — 🔴 `Arsenal` 일정에 2026-10-14 경기가 없다(받은 일정 

⚠️ **SQ1** — 이 측정은 경기 **뒤** 기록을 본다(측정용). 카드·확률 경로는 이 도구를 부르지 않는다.
