package diff

import "testing"

func TestFirstRunIsNotAllNew(t *testing.T) {
	// ⚠️ 첫 수집을 "전부 신규"로 내보내면 매일 첫 실행마다 알림이 폭주한다.
	got := Compare(nil, Snapshot{"A@B": {"home_pitcher": "임찬규"}})
	if len(got) != 0 {
		t.Fatalf("첫 수집인데 변화 %d건이 나왔다: %v", len(got), got)
	}
}

func TestDetectsStarterChange(t *testing.T) {
	old := Snapshot{"NC@LG": {"home_pitcher": "임찬규", "lineup": "확정"}}
	new := Snapshot{"NC@LG": {"home_pitcher": "최원태", "lineup": "확정"}}
	got := Compare(old, new)
	if len(got) != 1 {
		t.Fatalf("변화 1건이어야 하는데 %d건: %v", len(got), got)
	}
	c := got[0]
	if c.Field != "home_pitcher" || c.From != "임찬규" || c.To != "최원태" || c.Kind != "changed" {
		t.Fatalf("변화 내용이 틀렸다: %+v", c)
	}
}

func TestDetectsAddedAndRemoved(t *testing.T) {
	old := Snapshot{"A@B": {"lineup": "예상"}}
	new := Snapshot{"A@B": {"lineup": "", "home_pitcher": "구창모"}}
	got := Compare(old, new)
	if len(got) != 2 {
		t.Fatalf("2건이어야 하는데 %d건: %v", len(got), got)
	}
	kinds := map[string]string{}
	for _, c := range got {
		kinds[c.Field] = c.Kind
	}
	if kinds["home_pitcher"] != "added" || kinds["lineup"] != "removed" {
		t.Fatalf("종류가 틀렸다: %v", kinds)
	}
}

func TestNewGameIsNotAChange(t *testing.T) {
	// 더블헤더 편성 등으로 경기가 늘어난 것은 '변화'가 아니다
	old := Snapshot{"A@B": {"home_pitcher": "X"}}
	new := Snapshot{"A@B": {"home_pitcher": "X"}, "C@D": {"home_pitcher": "Y"}}
	if got := Compare(old, new); len(got) != 0 {
		t.Fatalf("새 경기가 변화로 잡혔다: %v", got)
	}
}

func TestOutputIsDeterministic(t *testing.T) {
	old := Snapshot{"B@A": {"home_pitcher": "1", "lineup": "x"},
		"A@C": {"home_pitcher": "2"}}
	new := Snapshot{"B@A": {"home_pitcher": "9", "lineup": "y"},
		"A@C": {"home_pitcher": "8"}}
	first := Compare(old, new)
	for i := 0; i < 20; i++ {
		if got := Compare(old, new); len(got) != len(first) || got[0] != first[0] {
			t.Fatal("같은 입력인데 결과 순서가 달라졌다 — 비교·테스트가 불가능해진다")
		}
	}
}

func TestNotableFiltersNoise(t *testing.T) {
	changes := []Change{
		{Game: "A@B", Field: "home_pitcher", Kind: "changed"},
		{Game: "A@B", Field: "weather", Kind: "changed"},
		{Game: "A@B", Field: "lineup_home", Kind: "added"},
		{Game: "A@B", Field: "starter_status", Kind: "changed"},
		{Game: "A@B", Field: "stadium", Kind: "changed"},
	}
	got := Notable(changes)
	if len(got) != 3 {
		t.Fatalf("선발·라인업·선발상태만 남아야 하는데 %d건: %v", len(got), got)
	}
	// 합본 `lineup`은 폐기됐다 — 남아 있으면 홈/원정 구분 없는 옛 형식이 산다
	if len(Notable([]Change{{Game: "A@B", Field: "lineup", Kind: "added"}})) != 0 {
		t.Error("옛 합본 lineup 필드가 아직 알림 대상이다")
	}
}
