"""[BAT-9] KBO 타자의 홈런·볼넷·삼진을 `table2`(타석별 결과)에서 읽는다.

🔴 **왜.** KBO 공식 `arrHitter.table3` 은 다섯 열뿐이다
   `[타수, 안타, 타점, 득점, 타율]`. 그래서 BAT-2 이후 KBO 만
   `hr/bb/so` 가 **전부 NULL** 이었다 — 실측 653행 중 0건.
   MLB·NPB 는 8칸을 다 준다(582/582 · 439/439). 자료3 이 리그마다 다른
   두께로 나가고 있었다.

   같은 응답의 `table2` 에 **타석별 결과 코드**가 있다. 실측 2026-09-09,
   KBO 9월 62경기 전수:
       서로 다른 표기 81종 · 1,537칸
       홈런  좌홈 · 우홈 · 중홈 · 좌중홈 · 우중홈   (전부 `홈` 으로 끝난다)
       삼진  삼진 · 스낫(스트라이크낫아웃)
       볼넷  4구 · 고4(고의4구)
       사구  사구                     ← 볼넷이 아니다

⚠️ **한 이닝에 두 타석이면 한 칸에 합쳐진다.** `사구<br />/ 삼진`.
   구분자는 `<br />/` 하나뿐이고 62경기에 10칸 있었다. 나누지 않으면
   두 타석이 **둘 다** 사라진다 — 대조에서 삼진·4사구가 1~2씩 모자랐다.

🔴 **검증은 같은 응답이 갖고 있다.** 상대 투수(`arrPitcher`)의 피홈런·삼진·
   4사구 합계가 그 팀 타자들의 홈런·삼진·(볼넷+사구)와 같아야 한다.
   그래서 파서가 **스스로 대조하고 어긋나면 알린다** — 손으로 적은 코드
   목록이 원본을 못 따라가는 순간을 잡는 유일한 방법이다.
"""
from __future__ import annotations

import json


def _tbl(rows):
    return json.dumps({"rows": [{"row": [{"Text": c} for c in r]} for r in rows],
                       "tfoot": []}, ensure_ascii=False)


def _hitter(names, nums, pas):
    return {"table1": _tbl(names), "table2": _tbl(pas), "table3": _tbl(nums)}


#: arrPitcher 헤더 17열 (실측 2026-08-28). **`headers` 가 따로 있다** —
#  `rows` 는 선수부터다. 처음에 이걸 빼먹어 파서가 0건을 돌려줬고, 그러면
#  대조 자체가 안 도는데 테스트는 "조용하다"고 실패했다.
_PIT_HEAD = ["선수명", "등판", "결과", "승", "패", "세", "이닝", "타자", "투구수",
             "타수", "피안타", "홈런", "4사구", "삼진", "실점", "자책", "평균자책점"]


def _pitcher(rows):
    return {"table": json.dumps({
        "headers": [{"row": [{"Text": c} for c in _PIT_HEAD]}],
        "rows": [{"row": [{"Text": c} for c in r]} for r in rows],
        "tfoot": []}, ensure_ascii=False)}


def _p(name, hr, bb4, k):
    return [name, "선발", "", "", "", "", "6", "24", "90", "20",
            "5", str(hr), str(bb4), str(k), "2", "2", "3.00"]


def _box(pas_away, pit_home, *, n_away=1):
    names = [[str(i + 1), "중", f"타자{i+1}"] for i in range(n_away)]
    nums = [["4", "1", "0", "0", "0.300"] for _ in range(n_away)]
    return {
        "arrHitter": [_hitter(names, nums, pas_away),
                      _hitter([["1", "중", "홈타자"]], [["4", "1", "0", "0", "0.300"]],
                              [["삼진", "", "", "", "", "", "", "", ""]])],
        # 홈 타자는 `삼진` 하나뿐이므로 원정 투수도 그렇게 맞춘다 —
        # 픽스처가 앞뒤가 안 맞으면 홈 쪽 대조가 늘 울린다.
        "arrPitcher": [_pitcher([_p("원정투수", 0, 0, 1)]), _pitcher(pit_home)],
    }


def test_홈런_볼넷_삼진을_읽는다():
    from app.collectors.kbo_boxscore import parse_batting

    box = _box([["좌홈", "4구", "삼진", "", "", "", "", "", ""]],
               [_p("홈투수", 1, 1, 1)])
    b = parse_batting(box)["away"][0]
    assert (b["hr"], b["bb"], b["so"]) == (1, 1, 1), b


def test_한_칸에_두_타석이면_둘_다_센다():
    """🔴 `<br />/` 로 합쳐진다. 나누지 않으면 둘 다 사라진다."""
    from app.collectors.kbo_boxscore import parse_batting

    box = _box([["사구<br />/ 삼진", "4구", "", "", "", "", "", "", ""]],
               [_p("홈투수", 0, 2, 1)])          # 4사구 = 볼넷1 + 사구1
    b = parse_batting(box)["away"][0]
    assert b["so"] == 1 and b["bb"] == 1, b
    assert not parse_batting(box).get("_mismatch"), "대조가 맞는데 경보를 냈다"


def test_사구는_볼넷이_아니다():
    from app.collectors.kbo_boxscore import parse_batting

    box = _box([["사구", "", "", "", "", "", "", "", ""]], [_p("홈투수", 0, 1, 0)])
    b = parse_batting(box)["away"][0]
    assert b["bb"] == 0, b


def test_스트라이크낫아웃도_삼진이다():
    from app.collectors.kbo_boxscore import parse_batting

    box = _box([["스낫", "", "", "", "", "", "", "", ""]], [_p("홈투수", 0, 0, 1)])
    assert parse_batting(box)["away"][0]["so"] == 1


def test_투수_기록과_어긋나면_알린다():
    """🔴 손으로 적은 코드 목록이 원본을 못 따라가는 순간을 이것만이 잡는다."""
    from app.collectors.kbo_boxscore import parse_batting

    box = _box([["삼진", "", "", "", "", "", "", "", ""]],
               [_p("홈투수", 0, 0, 5)])          # 투수는 삼진 5, 타자표는 1
    out = parse_batting(box)
    assert out.get("_mismatch"), "타자표와 투수표가 어긋나는데 조용하다"


def test_행수가_다르면_지어내지_않는다():
    from app.collectors.kbo_boxscore import parse_batting

    box = _box([["삼진", "", "", "", "", "", "", "", ""]], [_p("홈투수", 0, 0, 1)],
               n_away=2)                          # table2 는 1행, table1/3 은 2행
    rows = parse_batting(box)["away"]
    assert len(rows) == 2
    assert rows[1]["hr"] is None and rows[1]["so"] is None, rows[1]
