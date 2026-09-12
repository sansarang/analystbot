# SOC-10 — 위성이 찾은 것을 DB에 넣는다. 제미나이가 알아서 가져다 쓴다.

사용자 지시 2026-09-13: "부상자 명단 라인업 등등 경기와 관련된 내용을 db에
저장하면 된다..그리고 제미나이가 판단해서 가져다 쓰면 된다..그게 우리
원칙이다..시스템을 복잡하게 만들려고 애쓰지 말아라"

## 왜

그 원칙은 이미 `dbref.py` 머리말에 있다 — "경기 관련 DB를 통째로 주고, AI가
그 안에서 필요한 걸 찾아 쓰게 한다". **축구 자료만 그 통 안에 없다.**

실측 2026-09-13 (운영 12경기): 제미나이 12글 중 11글이 "확인하지 못했다"로
끝났다. `dbref.ITEMS` 9종이 전부 야구다(타순·선발투수·불펜·박스스코어).
그런데 위성은 Transfermarkt 부상표와 Flashscore 선발을 실제로 가져왔다 —
**캐시에만 있고 DB 통에 없었다.**

## ① 읽는 곳 전부
```
dbref.ITEMS → bundle(jg) → matchup.<fn>(jg)     전부 동기, jg 에서 읽는다
prompts 의 DB_MENU 는 ITEMS 에서 자동 생성       (손으로 안 적는다)
lineups 테이블 — SOC-9 가 flashscore 선발을 이미 쓴다
```

## ② 상태
| 상태 | 성격 |
|---|---|
| `lineups` 행 `source='transfermarkt' status='injury'` | 부상자를 `scratches` 에 |
| `engine/soccer_db.attach` | DB → `jg["soccer_lineup"]·["soccer_injuries"]` |
| `matchup.soccer_lineup_payload` · `soccer_injury_payload` | DB 칸 2종 |
| `dbref.ITEMS` +2 | 야구 9종은 그대로 |

🔴 새 테이블·새 컬럼 없다. `lineups.scratches` 가 결장자 자리다.
🔴 고르는 일을 코드가 하지 않는다 — 통에 넣고 제미나이가 고른다.

## ③ 분기
종목 분기 없음. payload 는 `jg` 에 값이 있으면 내고 없으면 빈손이다.

## ④ 조용히 실패하는가
| 위험 | 대응 |
|---|---|
| 🔴 야구 DB 메뉴가 바뀐다 | 9종 전수를 계약으로 고정 |
| 🔴 빈 값이 "있다"로 읽힌다 | 빈 payload 는 행을 만들지 않는다(기존 규칙) + 계약 |
| DB가 없어 판정이 죽는다 | `attach` 는 pool 없으면 조용히 통과. 계약 |
| 아무도 attach 를 안 부른다 | `_judge_v3` 소스에 호출 단언 |

⚠️ 못 잰 것: 제미나이가 그 칸을 실제로 **요청하는가**. 다음 실행에서 `DB있음`·`본것` 으로 잰다.

## ⑤ 사본
- 테이블·충돌키를 새로 정하지 않는다.
- 메뉴 문자열을 프롬프트에 손으로 적지 않는다 — `ITEMS` 가 원본이다.
