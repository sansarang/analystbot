"""SOC-7 — 본문 추출이 페이지 앞 1200자를 잘라 **메뉴만** 담았다.

🔴 **실측 2026-09-12 23:00 (운영, 위성 캐시의 실제 라인업 기사 5개 URL).**
   같은 HTML 에 세 방식을 돌려 유용한 본문이 나온 비율:

     현재(앞 1200자)   0/5   ← 전부 내비게이션·광고·쿠키 배너
     <p> 모음          3/5
     최장 블록         4/5
     둘 중 나은 쪽     5/5

   사용자 지적 2026-09-12: "선발 라인업 부상자 명단 배선해라... 인공위성이
   그거를 가지고 있는데 너가 똑같은 실수를 하고 있다."

   실제로 가지고 있었다. 캐시에 이런 것이 들어와 있는데도 —
     Hull City Today Lineup — "Phillips, Targett, Coyle, Herrington, Mendy,
       Crooks, Gourna-Douath, Dahl, Thomas, Cho, Vaz"   ← 선발 11명
     Chelsea XI vs Hull: Predicted lineup, confirmed team news, injury latest
   판정은 매 경기 "확정 선발 라인업을 확인하지 못했다"고 썼다. 본문이 메뉴라
   선별이 버렸기 때문이다(채택 3/24).
"""

from app.collectors.satellite import extract_body

_NAV = ("<nav>메뉴 메뉴 메뉴</nav><header>로고</header>"
        "Skip to main content LATEST NEWS MORE NEWS Upgrade now Advertisement ")


def test_메뉴가_아니라_본문을_집는다():
    """🔴 실측된 결함 그대로 — 앞부분은 메뉴다."""
    html = (_NAV + "<div><p>" + "첼시는 카이세도가 결장한다. " * 6 + "</p></div>")
    out = extract_body(html)
    assert "카이세도" in out
    assert "Skip to main content" not in out, out


def test_쿠키_배너_문단은_고르지_않는다():
    """🔴 실측: Standard 기사의 `<p>` 는 전부 동의 배너였다. 최장 블록에는
    'Pedro Neto ... will celebrate his new contract with a start at left
    wing-back' 이라는 진짜 선발 정보가 있었다."""
    html = ('<p>Allow Exco Player content This content is provided by Exco '
            'Player and may use cookies or similar technologies. Please click '
            "Allow and Continue below to load the content</p>"
            "<div>Pedro Neto was a half-time sub against Leeds, and he "
            "completed the turnaround with a well-taken goal. He will "
            "celebrate his new contract with a start at left wing-back.</div>")
    out = extract_body(html)
    assert "Pedro Neto" in out and "left wing-back" in out, out
    assert "Allow and Continue" not in out, out


def test_문단이_비면_최장_블록으로_간다():
    """🔴 실측: Sports Illustrated 는 `<p>` 가 0개였다."""
    html = _NAV + "<div>" + "Chelsea injury update for the Premier League. " * 4 + "</div>"
    out = extract_body(html)
    assert "injury update" in out, out


def test_둘_다_없으면_종전처럼_통째로_긁는다():
    """⚠️ 반대 위험 — 새 규칙이 못 찾았다고 **빈손을 주면 안 된다.**
    종전에는 적어도 무언가는 왔다."""
    html = "<div>짧다</div>"
    assert "짧다" in extract_body(html)


def test_스크립트와_스타일은_버린다():
    html = ("<script>var x=1;</script><style>.a{}</style>"
            "<div>" + "리버풀은 각포가 훈련을 소화하지 못했다. " * 4 + "</div>")
    out = extract_body(html)
    assert "var x" not in out and ".a{}" not in out
    assert "각포" in out


def test_길이_상한을_지킨다():
    """딥서치 `_fetch_body` 와 같은 1200자."""
    html = "<div>" + ("가" * 5000) + "</div>"
    assert len(extract_body(html)) == 1200


def test_수집기가_새_추출기를_쓴다():
    """🔴 함수만 만들고 배선을 안 하면 운영에서는 아무것도 안 바뀐다."""
    import inspect

    from app.collectors import satellite

    assert "extract_body" in inspect.getsource(satellite._fetch_article_body)
