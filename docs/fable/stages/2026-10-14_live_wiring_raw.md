2026-10-13 16:02:07,140 INFO app.config [config] .env 에서 27개 읽었다
2026-10-13 16:02:07,143 INFO app.config [config] .env 에서 0개 읽었다
[run_stage8] 예산 — 월 $8.0618 · 오늘(UTC) $0.0001 · 게이트 열림
2026-10-13 16:02:09,255 INFO app.bot_boot [boot] 질의 템플릿 사전 검사 통과(§2 · M129) — 템플릿 48개
2026-10-13 16:02:09,256 INFO app.research.rerank [rerank] 로드 #1 — mod=app.research.rerank id=4453481296 pid=81150 tid=6180745216(rerank_0)
2026-10-13 16:02:14,388 INFO httpx HTTP Request: HEAD https://huggingface.co/BAAI/bge-reranker-v2-m3/resolve/main/modules.json "HTTP/1.1 404 Not Found"
2026-10-13 16:02:14,389 INFO sentence_transformers.base.model No modules.json found for BAAI/bge-reranker-v2-m3, initializing a new CrossEncoder model.
2026-10-13 16:02:14,591 INFO httpx HTTP Request: GET https://huggingface.co/api/models/BAAI/bge-reranker-v2-m3 "HTTP/1.1 200 OK"
2026-10-13 16:02:14,796 INFO httpx HTTP Request: GET https://huggingface.co/api/models/BAAI/bge-reranker-v2-m3 "HTTP/1.1 200 OK"
2026-10-13 16:02:15,013 INFO httpx HTTP Request: HEAD https://huggingface.co/BAAI/bge-reranker-v2-m3/resolve/main/adapter_config.json "HTTP/1.1 404 Not Found"
2026-10-13 16:02:15,220 INFO httpx HTTP Request: GET https://huggingface.co/api/models/BAAI/bge-reranker-v2-m3 "HTTP/1.1 200 OK"
2026-10-13 16:02:15,434 INFO httpx HTTP Request: GET https://huggingface.co/api/models/BAAI/bge-reranker-v2-m3 "HTTP/1.1 200 OK"
Loading weights:   0%|          | 0/393 [00:00<?, ?it/s]Loading weights: 100%|██████████| 393/393 [00:00<00:00, 6165.39it/s]
2026-10-13 16:02:15,816 INFO httpx HTTP Request: GET https://huggingface.co/api/models/BAAI/bge-reranker-v2-m3 "HTTP/1.1 200 OK"
2026-10-13 16:02:16,040 INFO httpx HTTP Request: GET https://huggingface.co/api/models/BAAI/bge-reranker-v2-m3/tree/main/additional_chat_templates?recursive=false&expand=false "HTTP/1.1 404 Not Found"
2026-10-13 16:02:16,253 INFO httpx HTTP Request: GET https://huggingface.co/api/models/BAAI/bge-reranker-v2-m3/tree/main?recursive=true&expand=false "HTTP/1.1 200 OK"
2026-10-13 16:02:17,404 INFO httpx HTTP Request: GET https://huggingface.co/api/models/BAAI/bge-reranker-v2-m3 "HTTP/1.1 200 OK"
2026-10-13 16:02:20,125 INFO app.research.rerank [rerank] ✅ bge-reranker-v2-m3 (mps)
Batches:   0%|          | 0/1 [00:00<?, ?it/s]Batches: 100%|██████████| 1/1 [00:00<00:00,  1.63it/s]Batches: 100%|██████████| 1/1 [00:00<00:00,  1.63it/s]
2026-10-13 16:02:20,793 INFO bot [bot] 재정렬 예열 — ✅ bge-reranker-v2-m3 (mps) (로드 1회)
2026-10-13 16:02:21,168 INFO app.teamref [teamref] 같은 팀을 합쳤다 — team:000281 ← team:000353 (Kyoto Sanga F.C.) · 옛 번호는 별칭으로 남긴다
2026-10-13 16:02:21,178 INFO app.teamref [teamref] 같은 팀을 합쳤다 — team:000145 ← team:000447 (Monaco) · 옛 번호는 별칭으로 남긴다
2026-10-13 16:02:21,203 INFO app.teamref [teamref] 팀 573개 · 이름 2577개 · 못 박은 번호 520개 — CLDR 5개 언어 · 이름 1316개 · 대표팀 표기 3곳 · 이름 9개 · 축구협회 4곳 · 이름 17개 · 54팀 표 54팀 · 이름 152개 · 클럽 이름 524개 · ⚠️ 출처를 **가릴 수 없는** 옛 캐시 3개(NPB, J리그, K리그1) — 도장이 안 맞아 다음 온라인 판에 다시 받는다 · 유럽 별칭 13개 · 한국어 별칭 179개 · 표기 사전 143개 붙임 · 정식명을 못 찾아 건너뜀 33개 · 사용자 별칭 43개 붙임 · 정식명을 못 찾아 건너뜀 10개 · 배운 별칭 0개 · 못 박은 번호 520개(오픈월드 되살림 3 · 진짜 팀으로 0)
2026-10-13 16:02:21,228 INFO app.league_index [league_index] KBO 10팀 (어댑터 선언 `TEAM_IDS` 10팀(캐시))
2026-10-13 16:02:21,228 INFO app.league_index [league_index] NPB 팀 명단 0건 — `NPB` 에 `teams_from` 이 없다
2026-10-13 16:02:21,229 INFO app.league_index [league_index] MLB 60팀 (공식 API `mlb` 88팀(캐시))
2026-10-13 16:02:21,229 INFO app.league_index [league_index] J리그 팀 명단 0건 — `J리그` 에 `teams_from` 이 없다
2026-10-13 16:02:21,229 INFO app.league_index [league_index] K리그1 팀 명단 0건 — `K리그1` 에 `teams_from` 이 없다
2026-10-13 16:02:21,230 INFO app.league_index [league_index] 해외축구 359팀 (fdorg `PL` 20팀 · fdorg `PD` 20팀 · fdorg `SA` 20팀 · fdorg `BL1` 18팀 · fdorg `FL1` 18팀 · fdorg `DED` 18팀 · fdorg `PPL` 18팀 · fdorg `CL` 36팀 · fdorg `BSA` 20팀 · fdorg `ELC` 24팀(캐시))
2026-10-13 16:02:21,230 INFO app.league_index [league_index] NHL 32팀 (공식 API `nhl` 32팀(캐시))
2026-10-13 16:02:21,326 INFO httpx HTTP Request: GET https://www.fotmob.com/robots.txt "HTTP/1.1 200 OK"
2026-10-13 16:02:21,327 INFO app.net [net] robots 200 → `read` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`www.fotmob.com`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:02:21,391 INFO httpx HTTP Request: GET https://www.fotmob.com/match/6362342 "HTTP/1.1 200 OK"
2026-10-13 16:02:21,421 INFO app.collect.fotmob [fotmob] §13-c ② 약한 검사 — 상대를 몰라 우리 팀만 봤다 ['Mito Hollyhock', 'FC Tokyo']
2026-10-13 16:02:21,422 INFO app.collect.fotmob [fotmob] 맥락 5건 · ['h2h', 'form', 'info', 'lineup', 'lineup']
2026-10-13 16:02:21,435 INFO app.collect.fotmob [fotmob] 기준 XI·과거 통계·선수 8건 ← ob.com/matches/shimizu-s-pulse-vs-mito-hollyhock/6dkluzh
2026-10-13 16:02:21,439 INFO app.collect.fotmob [fotmob] 기준 XI·과거 통계·선수 7건 ← .com/matches/mito-hollyhock-vs-fukushima-united/22p8z3f5
2026-10-13 16:02:21,447 INFO app.collect.fotmob [fotmob] 기준 XI·과거 통계·선수 5건 ← .com/matches/yokohama-fmarinos-vs-mito-hollyhock/6jjrrzt
2026-10-13 16:02:21,455 INFO app.collect.fotmob [fotmob] 기준 XI·과거 통계·선수 3건 ← .com/matches/kawasaki-frontale-vs-mito-hollyhock/6iryk0e
2026-10-13 16:02:21,459 INFO app.collect.fotmob [fotmob] 기준 XI·과거 통계·선수 1건 ← b.com/matches/mito-hollyhock-vs-nagano-parceiro/11tkw4bt
2026-10-13 16:02:21,462 INFO app.collect.fotmob [fotmob] §13-c ② 약한 검사 — 상대를 몰라 우리 팀만 봤다 ['Mito Hollyhock', 'FC Tokyo']
2026-10-13 16:02:21,462 INFO app.collect.fotmob [fotmob] 맥락 5건 · ['h2h', 'form', 'info', 'lineup', 'lineup']
2026-10-13 16:02:21,476 INFO app.collect.fotmob [fotmob] 기준 XI·과거 통계·선수 6건 ← .fotmob.com/matches/fc-tokyo-vs-urawa-red-diamonds/xq63m
2026-10-13 16:02:21,483 INFO app.collect.fotmob [fotmob] 기준 XI·과거 통계·선수 3건 ← ps://www.fotmob.com/matches/fc-tokyo-vs-ehime-fc/6di85lq
2026-10-13 16:02:21,490 INFO app.collect.fotmob [fotmob] 기준 XI·과거 통계·선수 6건 ← www.fotmob.com/matches/fc-tokyo-vs-nagoya-grampus/19tfst
2026-10-13 16:02:21,498 INFO app.collect.fotmob [fotmob] 기준 XI·과거 통계·선수 8건 ← s://www.fotmob.com/matches/fc-tokyo-vs-gamba-osaka/zwiad
2026-10-13 16:02:21,524 INFO app.core.stages.s2_facts [s2] 자동 등록 — 등록 안 한다 — 손 표가 이미 아는 대회다(fotmob 리그 id `224`)
2026-10-13 16:02:22,144 INFO httpx HTTP Request: GET https://data.j-league.or.jp/robots.txt "HTTP/1.1 404 "
2026-10-13 16:02:22,145 INFO app.net [net] robots 404 → `allow` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`data.j-league.or.jp`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:02:22,412 INFO httpx HTTP Request: GET https://data.j-league.or.jp/SFIN03/ "HTTP/1.1 200 "
2026-10-13 16:02:22,482 INFO app.core.stages.s2_facts [s2] 결장 사다리 — fotmob 0건 — 🔴 **0건** — 경기 페이지에 결장 칸이 비었다 / 명단 대조 0건 — 🔴 **0건** — `team:000274` 과거 XI 4경기(<5) / 연맹 징계 0건 — ⬜ 공시 9줄에 **이 경기(10/14) 선수가 없다** / 국내 기사 0건 — ⏸ **변수 단계에서 센다** — 기사 결장 변수(F 하위)의 매체 수를 카드가 적는다
2026-10-13 16:02:22,484 INFO app.core.staterates [staterates] league_JLC — 🔴 `league_JLC` 에 2026-10-14 **이전 판이 없다**(있는 판 0개) — 표 없이 간다 · 옛 파일도 없다
2026-10-13 16:02:22,484 INFO app.core.staterates [staterates] league_JLC — 🔴 `league_JLC` 에 2026-10-14 **이전 판이 없다**(있는 판 0개) — 표 없이 간다 · 옛 파일도 없다
2026-10-13 16:02:22,484 INFO app.core.stages.s2_facts [s2] [2a] 상태 배율 — league:JLC · ⬜ 없다
2026-10-13 16:02:23,496 INFO httpx HTTP Request: GET https://www.eloratings.net/robots.txt "HTTP/1.1 404 Not Found"
2026-10-13 16:02:23,499 INFO app.net [net] robots 404 → `allow` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`www.eloratings.net`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:02:24,041 INFO httpx HTTP Request: GET https://www.eloratings.net/World.tsv "HTTP/1.1 200 OK"
2026-10-13 16:02:24,043 INFO app.collect.elo [elo] 등급 244개 ← https://www.eloratings.net/World.tsv
2026-10-13 16:02:24,068 INFO app.research.subtasks [subtasks] 하위 10개 — A-홈(4유형) · A-원정(4유형) · B-홈(4유형) · B-원정(4유형) · C-홈(4유형) · C-원정(4유형) · D-홈(5유형) · D-원정(5유형) · F-홈(10유형) · F-원정(10유형)
2026-10-13 16:02:27,158 INFO app.core.querywriter [질의] 질의 0개 · 매체 0곳 · 버린 것 0개 · LLM
2026-10-13 16:02:27,417 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=Mito+Hollyhock+FC+Tokyo+injury+news&format=RSS&mkt=en-US "HTTP/1.1 200 OK"
2026-10-13 16:02:27,417 INFO app.search [bing-news] 'Mito Hollyhock FC Tokyo injury news' → 0건
2026-10-13 16:02:27,557 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=Mito+Hollyhock+FC+Tokyo+rotation&format=RSS&mkt=en-US "HTTP/1.1 200 OK"
2026-10-13 16:02:27,563 INFO app.search [bing-news] 'Mito Hollyhock FC Tokyo rotation' → 2건
2026-10-13 16:02:27,778 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=Mito+Hollyhock+FC+Tokyo+record&format=RSS&mkt=en-US "HTTP/1.1 200 OK"
2026-10-13 16:02:27,781 INFO app.search [bing-news] 'Mito Hollyhock FC Tokyo record' → 2건
2026-10-13 16:02:27,922 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=Mito+Hollyhock+FC+Tokyo+record&format=json&language=en-US "HTTP/1.1 200 OK"
2026-10-13 16:02:27,922 INFO app.search [searx] 'Mito Hollyhock FC Tokyo record' → 20건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'CAPTCHA'})
2026-10-13 16:02:27,923 INFO app.search [search] 병렬 합계 22건(날짜 있는 것 2건) (SearXNG:20건 · Bing뉴스:2건)
2026-10-13 16:02:27,923 INFO app.core.stages.s3_docs [s3] 같은 검색을 나눠 썼다 — 'FC Tokyo Mito Hollyhock record' → 22건
2026-10-13 16:02:28,061 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=Mito+Hollyhock+FC+Tokyo+injury+news&format=json&language=en-US "HTTP/1.1 200 OK"
2026-10-13 16:02:28,061 INFO app.search [searx] 'Mito Hollyhock FC Tokyo injury news' → 20건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'CAPTCHA'})
2026-10-13 16:02:28,062 INFO app.search [search] 병렬 합계 20건(날짜 있는 것 0건) (SearXNG:20건 · Bing뉴스:0건)
2026-10-13 16:02:28,062 INFO app.core.stages.s3_docs [s3] 같은 검색을 나눠 썼다 — 'FC Tokyo Mito Hollyhock injury news' → 20건
2026-10-13 16:02:28,073 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=Mito+Hollyhock+FC+Tokyo+rotation&format=json&language=en-US "HTTP/1.1 200 OK"
2026-10-13 16:02:28,074 INFO app.search [searx] 'Mito Hollyhock FC Tokyo rotation' → 20건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'CAPTCHA'})
2026-10-13 16:02:28,074 INFO app.search [search] 병렬 합계 22건(날짜 있는 것 2건) (SearXNG:20건 · Bing뉴스:2건)
2026-10-13 16:02:28,074 INFO app.core.stages.s3_docs [s3] 같은 검색을 나눠 썼다 — 'FC Tokyo Mito Hollyhock rotation' → 22건
2026-10-13 16:02:28,328 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=Mito+Hollyhock+FC+Tokyo+retirement+ceremony&format=RSS&mkt=en-US "HTTP/1.1 200 OK"
2026-10-13 16:02:28,328 INFO app.search [bing-news] 'Mito Hollyhock FC Tokyo retirement ceremony' → 0건
2026-10-13 16:02:28,365 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=Mito+Hollyhock+FC+Tokyo+return&format=RSS&mkt=en-US "HTTP/1.1 200 OK"
2026-10-13 16:02:28,380 INFO app.search [bing-news] 'Mito Hollyhock FC Tokyo return' → 2건
2026-10-13 16:02:28,687 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=Mito+Hollyhock+FC+Tokyo+retirement+ceremony&format=json&language=en-US "HTTP/1.1 200 OK"
2026-10-13 16:02:28,689 INFO app.search [searx] 'Mito Hollyhock FC Tokyo retirement ceremony' → 20건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'CAPTCHA'})
2026-10-13 16:02:28,689 INFO app.search [search] 병렬 합계 20건(날짜 있는 것 0건) (SearXNG:20건 · Bing뉴스:0건)
2026-10-13 16:02:28,690 INFO app.core.stages.s3_docs [s3] 같은 검색을 나눠 썼다 — 'FC Tokyo Mito Hollyhock retirement ceremony' → 20건
2026-10-13 16:02:28,809 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=Mito+Hollyhock+FC+Tokyo+return&format=json&language=en-US "HTTP/1.1 200 OK"
2026-10-13 16:02:28,810 INFO app.search [searx] 'Mito Hollyhock FC Tokyo return' → 20건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'CAPTCHA'})
2026-10-13 16:02:28,811 INFO app.search [search] 병렬 합계 22건(날짜 있는 것 2건) (SearXNG:20건 · Bing뉴스:2건)
2026-10-13 16:02:28,811 INFO app.core.stages.s3_docs [s3] 같은 검색을 나눠 썼다 — 'FC Tokyo Mito Hollyhock return' → 22건
2026-10-13 16:02:28,872 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=Mito+Hollyhock+FC+Tokyo+%EA%B2%B0%EC%9E%A5&format=RSS&mkt=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:28,873 INFO app.search [bing-news] 'Mito Hollyhock FC Tokyo 결장' → 0건
2026-10-13 16:02:28,969 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=Mito+Hollyhock+FC+Tokyo+%EA%B8%B0%EB%A1%9D&format=json&language=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:28,970 INFO app.search [searx] 'Mito Hollyhock FC Tokyo 기록' → 20건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'CAPTCHA'})
2026-10-13 16:02:29,005 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=Mito+Hollyhock+FC+Tokyo+%EB%A1%9C%ED%85%8C%EC%9D%B4%EC%85%98&format=RSS&mkt=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:29,006 INFO app.search [bing-news] 'Mito Hollyhock FC Tokyo 로테이션' → 3건
2026-10-13 16:02:29,526 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=Mito+Hollyhock+FC+Tokyo+%EA%B2%B0%EC%9E%A5&format=json&language=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:29,528 INFO app.search [searx] 'Mito Hollyhock FC Tokyo 결장' → 20건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'CAPTCHA'})
2026-10-13 16:02:29,529 INFO app.search [search] 병렬 합계 20건(날짜 있는 것 0건) (SearXNG:20건 · Bing뉴스:0건)
2026-10-13 16:02:29,529 INFO app.core.stages.s3_docs [s3] 같은 검색을 나눠 썼다 — 'FC Tokyo Mito Hollyhock 결장' → 20건
2026-10-13 16:02:29,574 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=Mito+Hollyhock+FC+Tokyo+%EA%B8%B0%EB%A1%9D&format=RSS&mkt=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:29,574 INFO app.search [bing-news] 'Mito Hollyhock FC Tokyo 기록' → 1건
2026-10-13 16:02:29,574 INFO app.search [search] 병렬 합계 21건(날짜 있는 것 1건) (SearXNG:20건 · Bing뉴스:1건)
2026-10-13 16:02:29,575 INFO app.core.stages.s3_docs [s3] 같은 검색을 나눠 썼다 — 'FC Tokyo Mito Hollyhock 기록' → 21건
2026-10-13 16:02:29,929 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=Mito+Hollyhock+FC+Tokyo+%EC%9D%80%ED%87%B4+%EA%B2%BD%EA%B8%B0&format=RSS&mkt=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:29,931 INFO app.search [bing-news] 'Mito Hollyhock FC Tokyo 은퇴 경기' → 0건
2026-10-13 16:02:29,939 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=Mito+Hollyhock+FC+Tokyo+%EB%A1%9C%ED%85%8C%EC%9D%B4%EC%85%98&format=json&language=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:29,941 INFO app.search [searx] 'Mito Hollyhock FC Tokyo 로테이션' → 20건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'CAPTCHA'})
2026-10-13 16:02:29,941 INFO app.search [search] 병렬 합계 23건(날짜 있는 것 3건) (SearXNG:20건 · Bing뉴스:3건)
2026-10-13 16:02:29,941 INFO app.core.stages.s3_docs [s3] 같은 검색을 나눠 썼다 — 'FC Tokyo Mito Hollyhock 로테이션' → 23건
2026-10-13 16:02:30,356 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=Mito+Hollyhock+FC+Tokyo+%EC%9D%80%ED%87%B4+%EA%B2%BD%EA%B8%B0&format=json&language=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:30,357 INFO app.search [searx] 'Mito Hollyhock FC Tokyo 은퇴 경기' → 20건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'CAPTCHA'})
2026-10-13 16:02:30,357 INFO app.search [search] 병렬 합계 20건(날짜 있는 것 0건) (SearXNG:20건 · Bing뉴스:0건)
2026-10-13 16:02:30,357 INFO app.core.stages.s3_docs [s3] 같은 검색을 나눠 썼다 — 'FC Tokyo Mito Hollyhock 은퇴 경기' → 20건
2026-10-13 16:02:30,371 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EB%B3%B5%EA%B7%80&format=json&language=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:30,372 INFO app.search [searx] '미토 FC 도쿄 복귀' → 0건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'CAPTCHA'})
2026-10-13 16:02:30,552 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EA%B8%B0%EB%A1%9D&format=RSS&mkt=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:30,554 INFO app.search [bing-news] '미토 FC 도쿄 기록' → 0건
2026-10-13 16:02:31,081 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EA%B2%B0%EC%9E%A5&format=json&language=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:31,081 INFO app.search [searx] '미토 FC 도쿄 결장' → 0건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'access denied'})
2026-10-13 16:02:31,183 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EA%B2%B0%EC%9E%A5&format=RSS&mkt=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:31,184 INFO app.search [bing-news] '미토 FC 도쿄 결장' → 0건
2026-10-13 16:02:31,354 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EA%B8%B0%EB%A1%9D&format=json&language=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:31,355 INFO app.search [searx] '미토 FC 도쿄 기록' → 0건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'CAPTCHA'})
2026-10-13 16:02:32,200 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EB%B3%B5%EA%B7%80&format=RSS&mkt=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:32,201 INFO app.search [bing-news] '미토 FC 도쿄 복귀' → 0건
2026-10-13 16:02:44,673 INFO httpx HTTP Request: GET https://api.gdeltproject.org/api/v2/doc/doc?query=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EA%B2%B0%EC%9E%A5&mode=artlist&format=json&maxrecords=20&timespan=7d&sort=datedesc "HTTP/1.1 429 Too Many Requests"
2026-10-13 16:02:44,678 INFO app.search [gdelt] 429 — Please limit requests to one every 5 seconds or contact kalev.leetaru5@gmail.com for larger queries.
2026-10-13 16:02:45,593 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EA%B2%B0%EC%9E%A5&format=json&language=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:45,597 INFO app.search [searx] '미토 FC 도쿄 결장' → 0건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'Suspended: access denied'})
2026-10-13 16:02:45,782 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EA%B2%B0%EC%9E%A5&format=RSS&mkt=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:45,788 INFO app.search [bing-news] '미토 FC 도쿄 결장' → 0건
2026-10-13 16:02:45,829 INFO app.readtext [readtext] BM25 0점 — 질의 'def_absence absence_att pitcher_state fatigue' 가 어느 문단에도 없다
2026-10-13 16:02:45,831 INFO app.readtext [readtext] BM25 0점 — 질의 'def_absence absence_att pitcher_state fatigue' 가 어느 문단에도 없다
Batches:   0%|          | 0/2 [00:00<?, ?it/s]Batches:  50%|█████     | 1/2 [00:00<00:00,  6.63it/s]Batches: 100%|██████████| 2/2 [00:00<00:00,  3.50it/s]Batches: 100%|██████████| 2/2 [00:00<00:00,  3.77it/s]
2026-10-13 16:02:46,468 INFO app.core.stages.s3_docs [s3] 같은 검색을 나눠 썼다 — 'FC 도쿄 미토 결장' → 0건
2026-10-13 16:02:46,471 INFO app.readtext [readtext] BM25 0점 — 질의 'def_absence absence_att pitcher_state fatigue' 가 어느 문단에도 없다
2026-10-13 16:02:46,472 INFO app.readtext [readtext] BM25 0점 — 질의 'def_absence absence_att pitcher_state fatigue' 가 어느 문단에도 없다
Batches:   0%|          | 0/2 [00:00<?, ?it/s]Batches: 100%|██████████| 2/2 [00:00<00:00,  5.30it/s]Batches: 100%|██████████| 2/2 [00:00<00:00,  5.30it/s]
2026-10-13 16:02:47,209 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EB%A1%9C%ED%85%8C%EC%9D%B4%EC%85%98&format=RSS&mkt=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:47,209 INFO app.search [bing-news] '미토 FC 도쿄 로테이션' → 0건
2026-10-13 16:02:47,752 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EB%A1%9C%ED%85%8C%EC%9D%B4%EC%85%98&format=json&language=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:47,756 INFO app.search [searx] '미토 FC 도쿄 로테이션' → 0건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'Suspended: access denied'})
2026-10-13 16:02:48,578 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EB%A1%9C%ED%85%8C%EC%9D%B4%EC%85%98&format=json&language=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:48,581 INFO app.search [searx] '미토 FC 도쿄 로테이션' → 0건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'Suspended: access denied'})
2026-10-13 16:02:50,042 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EB%A1%9C%ED%85%8C%EC%9D%B4%EC%85%98&format=RSS&mkt=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:50,045 INFO app.search [bing-news] '미토 FC 도쿄 로테이션' → 0건
Batches:   0%|          | 0/2 [00:00<?, ?it/s]Batches: 100%|██████████| 2/2 [00:00<00:00,  4.14it/s]Batches: 100%|██████████| 2/2 [00:00<00:00,  4.14it/s]
2026-10-13 16:02:50,637 INFO app.core.stages.s3_docs [s3] 같은 검색을 나눠 썼다 — 'FC 도쿄 미토 로테이션' → 0건
Batches:   0%|          | 0/2 [00:00<?, ?it/s]Batches: 100%|██████████| 2/2 [00:00<00:00,  5.09it/s]Batches: 100%|██████████| 2/2 [00:00<00:00,  5.09it/s]
2026-10-13 16:02:51,135 INFO httpx HTTP Request: GET https://api.gdeltproject.org/api/v2/doc/doc?query=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EB%B3%B5%EA%B7%80&mode=artlist&format=json&maxrecords=20&timespan=7d&sort=datedesc "HTTP/1.1 429 Too Many Requests"
2026-10-13 16:02:51,135 INFO httpx HTTP Request: GET https://api.gdeltproject.org/api/v2/doc/doc?query=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EA%B8%B0%EB%A1%9D&mode=artlist&format=json&maxrecords=20&timespan=7d&sort=datedesc "HTTP/1.1 429 Too Many Requests"
2026-10-13 16:02:51,136 INFO app.search [gdelt] 429 — Please limit requests to one every 5 seconds or contact kalev.leetaru5@gmail.com for larger queries.
2026-10-13 16:02:51,140 INFO app.search [gdelt] 429 — Please limit requests to one every 5 seconds or contact kalev.leetaru5@gmail.com for larger queries.
2026-10-13 16:02:51,474 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EC%9D%80%ED%87%B4+%EA%B2%BD%EA%B8%B0&format=RSS&mkt=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:51,478 INFO app.search [bing-news] '미토 FC 도쿄 은퇴 경기' → 0건
2026-10-13 16:02:51,949 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EA%B8%B0%EB%A1%9D&format=json&language=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:51,950 INFO app.search [searx] '미토 FC 도쿄 기록' → 0건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'Suspended: access denied'})
2026-10-13 16:02:51,959 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EC%9D%80%ED%87%B4+%EA%B2%BD%EA%B8%B0&format=json&language=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:51,959 INFO app.search [searx] '미토 FC 도쿄 은퇴 경기' → 0건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'Suspended: access denied'})
2026-10-13 16:02:51,966 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EB%B3%B5%EA%B7%80&format=json&language=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:51,967 INFO app.search [searx] '미토 FC 도쿄 복귀' → 0건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'Suspended: access denied'})
2026-10-13 16:02:52,193 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EB%B3%B5%EA%B7%80&format=RSS&mkt=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:52,193 INFO app.search [bing-news] '미토 FC 도쿄 복귀' → 0건
2026-10-13 16:02:52,194 INFO app.core.stages.s3_docs [s3] 같은 검색을 나눠 썼다 — 'FC 도쿄 미토 복귀' → 0건
2026-10-13 16:02:52,740 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EC%9D%80%ED%87%B4+%EA%B2%BD%EA%B8%B0&format=json&language=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:52,744 INFO app.search [searx] '미토 FC 도쿄 은퇴 경기' → 0건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'Suspended: access denied'})
2026-10-13 16:02:52,976 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EC%9D%80%ED%87%B4+%EA%B2%BD%EA%B8%B0&format=RSS&mkt=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:52,983 INFO app.search [bing-news] '미토 FC 도쿄 은퇴 경기' → 0건
Batches:   0%|          | 0/2 [00:00<?, ?it/s]Batches: 100%|██████████| 2/2 [00:00<00:00,  3.91it/s]Batches: 100%|██████████| 2/2 [00:00<00:00,  3.91it/s]
2026-10-13 16:02:53,607 INFO app.core.stages.s3_docs [s3] 같은 검색을 나눠 썼다 — 'FC 도쿄 미토 은퇴 경기' → 0건
Batches:   0%|          | 0/2 [00:00<?, ?it/s]Batches: 100%|██████████| 2/2 [00:00<00:00,  4.87it/s]Batches: 100%|██████████| 2/2 [00:00<00:00,  4.87it/s]
2026-10-13 16:02:54,122 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EC%B6%9C%EC%A0%84+%EC%A0%95%EC%A7%80&format=RSS&mkt=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:54,123 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EC%B6%9C%EC%A0%84+%EC%A0%95%EC%A7%80&format=json&language=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:54,123 INFO app.search [bing-news] '미토 FC 도쿄 출전 정지' → 0건
2026-10-13 16:02:54,123 INFO app.search [searx] '미토 FC 도쿄 출전 정지' → 0건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'Suspended: access denied'})
2026-10-13 16:02:54,722 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EA%B8%B0%EB%A1%9D&format=RSS&mkt=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:54,723 INFO app.search [bing-news] '미토 FC 도쿄 기록' → 0건
Batches:   0%|          | 0/2 [00:00<?, ?it/s]Batches: 100%|██████████| 2/2 [00:00<00:00,  4.81it/s]Batches: 100%|██████████| 2/2 [00:00<00:00,  4.81it/s]
2026-10-13 16:02:55,246 INFO app.core.stages.s3_docs [s3] 같은 검색을 나눠 썼다 — 'FC 도쿄 미토 기록' → 0건
Batches:   0%|          | 0/2 [00:00<?, ?it/s]Batches: 100%|██████████| 2/2 [00:00<00:00,  5.44it/s]Batches: 100%|██████████| 2/2 [00:00<00:00,  5.43it/s]
2026-10-13 16:02:55,708 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EC%B6%9C%EC%A0%84+%EC%A0%95%EC%A7%80&format=json&language=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:55,709 INFO app.search [searx] '미토 FC 도쿄 출전 정지' → 0건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'Suspended: access denied'})
2026-10-13 16:02:55,863 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EC%B6%9C%EC%A0%84+%EC%A0%95%EC%A7%80&format=RSS&mkt=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:02:55,867 INFO app.search [bing-news] '미토 FC 도쿄 출전 정지' → 0건
Batches:   0%|          | 0/2 [00:00<?, ?it/s]Batches: 100%|██████████| 2/2 [00:00<00:00,  3.06it/s]Batches: 100%|██████████| 2/2 [00:00<00:00,  3.06it/s]
2026-10-13 16:02:56,681 INFO app.core.stages.s3_docs [s3] 같은 검색을 나눠 썼다 — 'FC 도쿄 미토 출전 정지' → 0건
Batches:   0%|          | 0/2 [00:00<?, ?it/s]Batches: 100%|██████████| 2/2 [00:00<00:00,  3.16it/s]Batches: 100%|██████████| 2/2 [00:00<00:00,  3.16it/s]
2026-10-13 16:02:57,529 INFO httpx HTTP Request: GET https://www.sofascore.com/robots.txt "HTTP/1.1 403 Forbidden"
2026-10-13 16:02:57,530 INFO app.net [net] robots 403 → `deny` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`www.sofascore.com`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:02:57,585 INFO httpx HTTP Request: GET https://www.sofascore.com/football/team/mito-hollyhock/21901 "HTTP/1.1 403 Forbidden"
2026-10-13 16:02:57,679 INFO httpx HTTP Request: GET https://www.espn.com.sg/robots.txt "HTTP/1.1 200 OK"
2026-10-13 16:02:57,686 INFO app.net [net] robots 200 → `read` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`www.espn.com.sg`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:02:58,427 INFO httpx HTTP Request: GET https://www.espn.com.sg/football/team/stats/_/id/131701/mito_hollyhock "HTTP/1.1 200 OK"
2026-10-13 16:02:59,746 INFO app.readtext [readtext] 본문 346자 · 발행 2026-10-13 · https://www.espn.com.sg/football/team/stats/_/id/131701/mito
2026-10-13 16:02:59,796 INFO httpx HTTP Request: GET https://www.fotmob.com/teams/162195/fixtures/mito-hollyhock "HTTP/1.1 200 OK"
2026-10-13 16:02:59,934 INFO app.readtext [readtext] 본문 1243자 · 발행 2026-09-02 · https://www.fotmob.com/teams/162195/fixtures/mito-hollyhock
2026-10-13 16:03:00,982 INFO httpx HTTP Request: GET https://www.espn.com.sg/football/team/_/id/131701/mito-hollyhock "HTTP/1.1 200 OK"
2026-10-13 16:03:01,262 INFO app.readtext [readtext] 본문 701자 · 발행 2019-05-08 · https://www.espn.com.sg/football/team/_/id/131701/mito-holly
2026-10-13 16:03:01,416 INFO httpx HTTP Request: GET https://www.ysscores.com/robots.txt "HTTP/1.1 200 OK"
2026-10-13 16:03:01,417 INFO app.net [net] robots 200 → `read` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`www.ysscores.com`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:03:02,616 INFO httpx HTTP Request: GET https://www.ysscores.com/en/match/5803671/Mito-HollyHock-vs-Tokyo-Verdy "HTTP/1.1 200 OK"
2026-10-13 16:03:02,881 INFO app.readtext [readtext] 본문 652자 · 발행 2026-01-01 · https://www.ysscores.com/en/match/5803671/Mito-HollyHock-vs-
2026-10-13 16:03:07,086 INFO httpx HTTP Request: GET https://www.betexplorer.com/robots.txt "HTTP/1.1 200 OK"
2026-10-13 16:03:07,087 INFO app.net [net] robots 200 → `read` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`www.betexplorer.com`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:03:08,268 INFO httpx HTTP Request: GET https://www.betexplorer.com/football/team/mito/GliRsh4P/ "HTTP/1.1 200 OK"
2026-10-13 16:03:08,733 INFO app.readtext [readtext] 본문 1280자 · 발행 2026-01-01 · https://www.betexplorer.com/football/team/mito/GliRsh4P/
2026-10-13 16:03:09,106 INFO httpx HTTP Request: GET https://simple.wikipedia.org/robots.txt "HTTP/1.1 200 OK"
2026-10-13 16:03:09,106 INFO app.net [net] robots 200 → `read` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`simple.wikipedia.org`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:03:10,080 INFO httpx HTTP Request: GET https://simple.wikipedia.org/wiki/Mito_HollyHock "HTTP/1.1 200 OK"
2026-10-13 16:03:10,217 INFO app.readtext [readtext] 본문 608자 · 발행 2010-04-16 · https://simple.wikipedia.org/wiki/Mito_HollyHock
2026-10-13 16:03:10,394 INFO httpx HTTP Request: GET https://www.foxsports.com/robots.txt "HTTP/1.1 200 OK"
2026-10-13 16:03:10,396 INFO app.net [net] robots 200 → `read` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`www.foxsports.com`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:03:10,454 INFO httpx HTTP Request: GET https://www.foxsports.com/soccer/mito-hollyhock-team-standings "HTTP/1.1 200 OK"
2026-10-13 16:03:10,575 INFO app.readtext [readtext] 본문 1528자 · 발행 2026-10-13 · https://www.foxsports.com/soccer/mito-hollyhock-team-standin
2026-10-13 16:03:11,295 INFO httpx HTTP Request: GET https://www.soccerpunter.com/robots.txt "HTTP/1.1 200 OK"
2026-10-13 16:03:11,295 INFO app.net [net] robots 200 → `read` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`www.soccerpunter.com`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:03:12,200 INFO httpx HTTP Request: GET https://www.soccerpunter.com/team/Mito-Hollyhock/17806/ "HTTP/1.1 429 Too Many Requests"
2026-10-13 16:03:12,249 INFO httpx HTTP Request: GET https://www.fotmob.com/teams/162195/overview/mito-hollyhock "HTTP/1.1 200 OK"
2026-10-13 16:03:12,565 INFO app.readtext [readtext] 본문 8566자 · 발행 2026-09-02 · https://www.fotmob.com/teams/162195/overview/mito-hollyhock
2026-10-13 16:03:12,633 INFO httpx HTTP Request: GET https://www.espn.com/robots.txt "HTTP/1.1 200 OK"
2026-10-13 16:03:12,634 INFO app.net [net] robots 200 → `read` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`www.espn.com`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:03:13,124 INFO httpx HTTP Request: GET https://www.espn.com/soccer/match/_/gameId/401877502/fc-tokyo-mito-hollyhock "HTTP/1.1 200 OK"
2026-10-13 16:03:13,407 INFO app.readtext [readtext] 본문 401자 · 발행 2026-04-24 · https://www.espn.com/soccer/match/_/gameId/401877502/fc-toky
2026-10-13 16:03:15,866 INFO httpx HTTP Request: GET https://www.espn.com/soccer/match/_/gameId/401877585/mito-hollyhock-fc-tokyo "HTTP/1.1 200 OK"
2026-10-13 16:03:16,205 INFO app.readtext [readtext] 본문 401자 · 발행 2026-04-24 · https://www.espn.com/soccer/match/_/gameId/401877585/mito-ho
2026-10-13 16:03:16,812 INFO httpx HTTP Request: GET https://www.espn.ph/robots.txt "HTTP/1.1 200 OK"
2026-10-13 16:03:16,815 INFO app.net [net] robots 200 → `read` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`www.espn.ph`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:03:18,005 INFO httpx HTTP Request: GET https://www.espn.ph/football/team/_/id/131701/mito-hollyhock "HTTP/1.1 200 OK"
2026-10-13 16:03:18,381 INFO app.readtext [readtext] 본문 701자 · 발행 2019-05-08 · https://www.espn.ph/football/team/_/id/131701/mito-hollyhock
2026-10-13 16:03:18,433 INFO httpx HTTP Request: GET https://www.fotmob.com/id/matches/tokyo-verdy-vs-mito-hollyhock/6iju39e "HTTP/1.1 200 OK"
2026-10-13 16:03:18,648 INFO app.readtext [readtext] 본문 4053자 · 발행 2026-01-01 · https://www.fotmob.com/id/matches/tokyo-verdy-vs-mito-hollyh
2026-10-13 16:03:19,575 INFO httpx HTTP Request: GET https://www.footlive.com/robots.txt "HTTP/1.1 200 OK"
2026-10-13 16:03:19,579 INFO app.net [net] robots 200 → `read` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`www.footlive.com`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:03:20,496 INFO httpx HTTP Request: GET https://www.footlive.com/h2h/mito-hollyhock-vs-fc-tokyo/ "HTTP/1.1 200 OK"
2026-10-13 16:03:20,927 INFO app.readtext [readtext] 본문 403자 · 발행 2026-10-01 · https://www.footlive.com/h2h/mito-hollyhock-vs-fc-tokyo/
2026-10-13 16:03:21,726 INFO httpx HTTP Request: GET https://www.espn.co.uk/robots.txt "HTTP/1.1 200 OK"
2026-10-13 16:03:21,730 INFO app.net [net] robots 200 → `read` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`www.espn.co.uk`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:03:22,248 INFO httpx HTTP Request: GET https://www.espn.co.uk/football/team/_/id/131701/mito-hollyhock "HTTP/1.1 200 OK"
2026-10-13 16:03:22,641 INFO app.readtext [readtext] 본문 701자 · 발행 2019-05-08 · https://www.espn.co.uk/football/team/_/id/131701/mito-hollyh
2026-10-13 16:03:22,687 INFO httpx HTTP Request: GET https://www.fotmob.com/id/matches/fc-tokyo-vs-mito-hollyhock/6dhxfyq "HTTP/1.1 200 OK"
2026-10-13 16:03:22,882 INFO app.readtext [readtext] 본문 4409자 · 발행 2026-09-09 · https://www.fotmob.com/id/matches/fc-tokyo-vs-mito-hollyhock
2026-10-13 16:03:26,126 INFO httpx HTTP Request: GET https://www.fotmob.com/id/matches/kawasaki-vs-mito-hollyhock/6iryk0e "HTTP/1.1 308 Permanent Redirect"
2026-10-13 16:03:27,572 INFO httpx HTTP Request: GET https://www.fotmob.com/id/matches/kawasaki-frontale-vs-mito-hollyhock/6iryk0e "HTTP/1.1 200 OK"
2026-10-13 16:03:27,868 INFO app.readtext [readtext] 본문 5491자 · 발행 2026-09-12 · https://www.fotmob.com/id/matches/kawasaki-vs-mito-hollyhock
2026-10-13 16:03:28,054 INFO httpx HTTP Request: GET https://www.youtube.com/robots.txt "HTTP/1.1 200 OK"
2026-10-13 16:03:28,056 INFO app.net [net] robots 200 → `read` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`www.youtube.com`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:03:28,321 INFO httpx HTTP Request: GET https://www.youtube.com/watch?v=kV1gWmUR734 "HTTP/1.1 200 OK"
2026-10-13 16:03:28,845 INFO app.readtext [readtext] 본문 274자 · 발행 2026-02-14 · https://www.youtube.com/watch?v=kV1gWmUR734
2026-10-13 16:03:29,349 INFO httpx HTTP Request: GET https://www.espn.ph/football/team/_/id/131701 "HTTP/1.1 200 OK"
2026-10-13 16:03:29,725 INFO app.readtext [readtext] 본문 701자 · 발행 2019-05-08 · https://www.espn.ph/football/team/_/id/131701
2026-10-13 16:03:30,072 INFO httpx HTTP Request: GET https://en.wikipedia.org/robots.txt "HTTP/1.1 200 OK"
2026-10-13 16:03:30,074 INFO app.net [net] robots 200 → `read` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`en.wikipedia.org`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:03:30,472 INFO httpx HTTP Request: GET https://en.wikipedia.org/wiki/Mito_HollyHock "HTTP/1.1 200 OK"
2026-10-13 16:03:30,906 INFO app.readtext [readtext] 본문 3966자 · 발행 2006-02-05 · https://en.wikipedia.org/wiki/Mito_HollyHock
2026-10-13 16:03:31,461 INFO httpx HTTP Request: GET https://www.espn.com.au/robots.txt "HTTP/1.1 200 OK"
2026-10-13 16:03:31,466 INFO app.net [net] robots 200 → `read` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`www.espn.com.au`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:03:32,376 INFO httpx HTTP Request: GET https://www.espn.com.au/football/team/_/id/131701/mito-hollyhock "HTTP/1.1 200 OK"
2026-10-13 16:03:32,713 INFO app.readtext [readtext] 본문 701자 · 발행 2019-05-08 · https://www.espn.com.au/football/team/_/id/131701/mito-holly
2026-10-13 16:03:33,533 INFO httpx HTTP Request: GET https://kids.kiddle.co/robots.txt "HTTP/1.1 200 OK"
2026-10-13 16:03:33,539 INFO app.net [net] robots 200 → `read` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`kids.kiddle.co`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:03:35,032 INFO httpx HTTP Request: GET https://kids.kiddle.co/Mito_HollyHock "HTTP/1.1 200 OK"
2026-10-13 16:03:35,314 INFO app.readtext [readtext] 본문 3140자 · 발행 2025-10-17 · https://kids.kiddle.co/Mito_HollyHock
2026-10-13 16:03:35,405 INFO httpx HTTP Request: GET https://www.espn.in/robots.txt "HTTP/1.1 200 OK"
2026-10-13 16:03:35,406 INFO app.net [net] robots 200 → `read` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`www.espn.in`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:03:35,968 INFO httpx HTTP Request: GET https://www.espn.in/football/team/_/id/131701/mito-hollyhock "HTTP/1.1 200 OK"
2026-10-13 16:03:36,289 INFO app.readtext [readtext] 본문 701자 · 발행 2019-05-08 · https://www.espn.in/football/team/_/id/131701/mito-hollyhock
2026-10-13 16:03:37,347 INFO httpx HTTP Request: GET https://prosport.uz/robots.txt "HTTP/1.1 403 Forbidden"
2026-10-13 16:03:37,348 INFO app.net [net] robots 403 → `deny` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`prosport.uz`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:03:37,506 INFO httpx HTTP Request: GET https://prosport.uz/en/match/55110/mito-hollyhock-fc-tokyo "HTTP/1.1 403 Forbidden"
2026-10-13 16:03:39,234 INFO httpx HTTP Request: GET https://www.fotmob.com/id/matches/mito-hollyhock-vs-iwaki-fc/6og1kc23 "HTTP/1.1 200 OK"
2026-10-13 16:03:39,382 INFO app.readtext [readtext] 본문 4940자 · 발행 2025-09-20 · https://www.fotmob.com/id/matches/mito-hollyhock-vs-iwaki-fc
2026-10-13 16:03:39,384 INFO app.research.subtasks [subtasks] 하위 10개 — A-홈(4유형) · A-원정(4유형) · B-홈(4유형) · B-원정(4유형) · C-홈(4유형) · C-원정(4유형) · D-홈(5유형) · D-원정(5유형) · F-홈(10유형) · F-원정(10유형)
2026-10-13 16:03:39,906 INFO httpx HTTP Request: GET https://www.bing.com/news/search?q=Hollyhock+Japanese+%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EB%A1%9C%ED%85%8C%EC%9D%B4%EC%85%98&format=RSS&mkt=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:03:39,911 INFO app.search [bing-news] 'Hollyhock Japanese 미토 FC 도쿄 로테이션' → 0건
2026-10-13 16:03:40,421 INFO httpx HTTP Request: GET http://127.0.0.1:8888/search?q=Hollyhock+Japanese+%EB%AF%B8%ED%86%A0+FC+%EB%8F%84%EC%BF%84+%EB%A1%9C%ED%85%8C%EC%9D%B4%EC%85%98&format=json&language=ko-KR "HTTP/1.1 200 OK"
2026-10-13 16:03:40,423 INFO app.search [searx] 'Hollyhock Japanese 미토 FC 도쿄 로테이션' → 7건 (정지 중인 엔진 {'google': 'Suspended: access denied', 'google cse': 'Suspended: too many requests', 'naver': 'Suspended: access denied', 'qwant': 'Suspended: access denied'})
2026-10-13 16:03:40,423 INFO app.search [search] 병렬 합계 7건(날짜 있는 것 0건) (SearXNG:7건 · Bing뉴스:0건)
Batches:   0%|          | 0/1 [00:00<?, ?it/s]Batches: 100%|██████████| 1/1 [00:00<00:00,  9.27it/s]Batches: 100%|██████████| 1/1 [00:00<00:00,  9.25it/s]
2026-10-13 16:03:40,877 INFO httpx HTTP Request: GET https://megainspiration.co.kr/robots.txt "HTTP/1.1 200 OK"
2026-10-13 16:03:40,878 INFO app.net [net] robots 200 → `read` — §4-7 은 모든 호스트에 **같은 규칙**을 쓴다(`megainspiration.co.kr`). ⚠️ 301 이면 **최종 호스트**의 robots 를 읽는다(최대 5번)
2026-10-13 16:03:41,906 INFO httpx HTTP Request: GET https://megainspiration.co.kr/players/j1/399074/ "HTTP/1.1 200 OK"
2026-10-13 16:03:41,949 INFO app.readtext [readtext] 본문 900자 · 발행 2026-10-05 · https://megainspiration.co.kr/players/j1/399074/
2026-10-13 16:03:44,974 INFO httpx HTTP Request: GET https://megainspiration.co.kr/players/j1/313270/ "HTTP/1.1 200 OK"
2026-10-13 16:03:45,039 INFO app.readtext [readtext] 본문 286자 · 발행 2026-10-05 · https://megainspiration.co.kr/players/j1/313270/
2026-10-13 16:03:45,074 INFO app.net [net] robots 못 읽었다 spodb.spojoy.com: [SSL: SSLV3_ALERT_HANDSHAKE_FAILURE] ssl/tls alert handshake failure (_ssl.c:1010) — 허용으로 본다
2026-10-13 16:03:45,105 INFO app.core.stages.s4_extract [s4] 추출 — 문서 1건 → 후보 0개 · 🔴 **후보 0개** — 문서 1건 중 1개 하위에 물었고 건진 것이 없다(모델이 못 건졌거나 스키마가 버렸다)
2026-10-13 16:03:45,142 INFO app.core.stages.s2d_strategy [s2d] 전략 입력 — 확정 {'home': False, 'away': False} · 사실 {'home': 0, 'away': 0}
2026-10-13 16:03:45,142 INFO app.core.stages.s2d_strategy [s2d] **확정 XI 전** — home: 🔴 **확정 XI 전 — 전략 분석 없음**(§1) · 지금 XI 는 `예상` · away: 🔴 **확정 XI 전 — 전략 분석 없음**(§1) · 지금 XI 는 `예상`
2026-10-13 16:03:45,888 INFO app.core.stages.s2e_matchup [s2e] Elo 를 못 찾은 팀 4곳 — ['Ehime FC', 'Fukushima United', 'Kyoto Sangyo University', 'Nagano Parceiro']
2026-10-13 16:03:46,314 INFO app.core.stages.s2e_matchup [s2e] Elo 를 못 찾은 팀 4곳 — ['Ehime FC', 'Fukushima United', 'Kyoto Sangyo University', 'Nagano Parceiro']
2026-10-13 16:03:46,315 INFO app.core.stages.s2e_matchup [s2e] 상성 — 축1 폼 home 0.837, away 2.25 · 축3 발동 1건 · 발동 ['T10']
2026-10-13 16:03:46,320 INFO app.core.matchup [S2] 상성 — axis0 -0.43 · axis1 -0.94 · axis2 -0.00 · axis3 -0.15 → 종합 away 중 · XI predicted · 지문 c1e5aa2d439b
⚽ Mito Hollyhock vs FC Tokyo · League Cup · 10/14(수) 19:00
📋 라인업 예상 — 18:00 이후 `/재분석`
🔴 **자료 부족 카드 — 판단에 쓰지 말 것**(블록 3 에 경기당 총골·핵심 선수 가 없다)

【헤드라인】 방향 못 정함 — 기준이 없다 · 보드를 주면 판정
【이유】 맞대결 6경기 Mito Hollyhock 0승 1무 5패(상대 5승). 우리 열은 방향 못 정함 — 기준이 없다 로 잡힌다.
⚔️ **상성** — **FC Tokyo** 중
 축0 전력: -0.43(중) · home 🔴 **대체값 — Hugo Leonardo**(1명 · 같은 리그…
 축1 폼: -0.94(강) · 보정 득실차/경기 홈 0.837 · 원정 2.25 → r 가중 home…
 축2 전술: -0.00(없음) · 6축 차 -0.0036(공격 − 상대 수비 · 크기 0.15) · 발동…
 축3 골 내용: -0.15(약) · 발동 1건(규칙당 0.15) · 🔴 임시
📊 우리 열이 비었다 — 기준이 없다(시나리오 비율을 쓰지 않는다)
🎯 예상 못 골랐다 — 시나리오가 없다
🧪 반증 0조건: 무너짐 0 · 미확인 0 → 조건부
⚠️ 뒤집히는 길: 반대 결과를 그린 갈래가 없다 — 세트가 한쪽으로만 쏠렸다
🆕 **새 사실(72시간)** — 🔴 0건
🎯 보드 판정: 걸 줄 없음 — 보드가 없다(보드를 주면 판정한다)
[📖 자세히] [🧩 시나리오] [💹 시장 비교] [🔄 재분석]
[버튼] 📖 자세히 🧩 시나리오 / 💹 시장 비교 🔄 재분석 / 🔔 라인업 나오면 다시 분석

==================================================================
[§8 수치] 벽시계 1.6분 (상한 6분) ✓
[§8 수치] 비용 $0.0000 (상한 $0.5) ✓
[§8 수치] 예산 뒤 — 월 $8.0619 · 오늘(UTC) $0.0002
