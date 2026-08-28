package gate

import (
	"strings"
	"testing"

	"analystbot/crawler/internal/diff"
)

// 실제 수집값(2026-08-26 광주). 게이트가 **정상 데이터를 버리지 않는지**가
// 통과보다 중요하다 — 새 가드는 반대 방향 위험을 함께 측정한다(규율).
var realKBO = map[string]string{
	"home_pitcher": "황동하",
	"away_pitcher": "로드리게스",
	"lineup_home":  "이호연-박상준-김도영-카스트로-나성범-하주석-김호령-김태군-박정우",
	"lineup_away":  "황성빈-나승엽-레이예스-한동희-고승민-한태양-전민재-손성빈-장두성",
	"stadium":      "광주",
	"status":       "경기전",
	"home_w":       "61", "home_l": "50", "home_d": "2", "home_g": "113",
}

func TestRealDataPassesUntouched(t *testing.T) {
	clean, drops := Apply(diff.Snapshot{"Lotte Giants@Kia Tigers": realKBO})
	if len(drops) != 0 {
		t.Fatalf("정상 데이터를 버렸다: %v", drops)
	}
	if len(clean["Lotte Giants@Kia Tigers"]) != len(realKBO) {
		t.Fatalf("필드가 사라졌다: %d → %d", len(realKBO), len(clean["Lotte Giants@Kia Tigers"]))
	}
}

func TestEmptyValuesAreNotViolations(t *testing.T) {
	// 선발·라인업은 경기 임박까지 비어 있는 것이 **정상**이다.
	// 이걸 폐기하면 매일 오전 전 경기가 통째로 날아간다.
	in := diff.Snapshot{"A@B": {
		"home_pitcher": "", "away_pitcher": "", "lineup_home": "", "lineup_away": "",
		"stadium": "잠실",
	}}
	_, drops := Apply(in)
	if len(drops) != 0 {
		t.Fatalf("빈 값을 위반으로 판정했다: %v", drops)
	}
}

func TestUnknownFieldPassesThrough(t *testing.T) {
	// 미등록 필드를 폐기하면 수집 확대가 조용히 멈춘다.
	_, drops := Apply(diff.Snapshot{"A@B": {"brand_new_field": "무엇이든"}})
	if len(drops) != 0 {
		t.Fatalf("미등록 필드를 버렸다: %v", drops)
	}
}

// ---------------------------------------------------------------- 게이트 ① 물리

func TestPhysicalGate(t *testing.T) {
	cases := []struct{ field, value, want string }{
		{"home_era", "189.00", "물리 범위"},     // 실사고: 齋藤 響介
		{"away_era", "4.82", ""},            // 정상
		{"home_pitches_l3", "250", "물리 범위"}, // 한 투수가 3경기 250구는 불가능
		{"home_pitches_l3", "78", ""},
		{"home_rank", "0", "물리 범위"},
		{"home_rank", "13", "물리 범위"},
		{"home_rank", "4", ""},
		{"home_pitcher", "황동하7", "숫자가 섞임"}, // 컬럼 밀림
		{"home_pitcher", "황동하", ""},
		{"starter_status", "たぶん", "허용 값"},
		{"starter_status", "확정", ""},
		{"home_ip_avg", "abc", "숫자가 아님"},
	}
	for _, c := range cases {
		got := checkPhysical(c.field, c.value)
		if c.want == "" && got != "" {
			t.Errorf("%s=%q 정상인데 폐기됨: %s", c.field, c.value, got)
		}
		if c.want != "" && !strings.Contains(got, c.want) {
			t.Errorf("%s=%q → %q, %q 포함 기대", c.field, c.value, got, c.want)
		}
	}
}

func TestLineupMustBeNine(t *testing.T) {
	short := strings.Join(strings.Split("가-나-다-라-마-바-사-아", "-"), "-") // 8명
	if msg := checkPhysical("lineup_home", short); !strings.Contains(msg, "8명") {
		t.Errorf("8명 라인업을 통과시켰다: %q", msg)
	}
	if msg := checkPhysical("lineup_home", realKBO["lineup_home"]); msg != "" {
		t.Errorf("정상 9명을 버렸다: %s", msg)
	}
	// NPB는 한 글자 포지션(投·指·遊). 한글 "3루수"는 숫자라 이름이 폐기된다.
	npb := "山田 哲人(捕)-塩見 泰隆(中)-村上 宗隆(三)-サンタナ(右)-オスナ(一)-西川 輝矢(左)-長岡 秀樹(遊)-山野 太一(投)-山崎 晃大朗(二)"
	if msg := checkPhysical("lineup_home", npb); msg != "" {
		t.Errorf("NPB 9명을 버렸다: %s", msg)
	}
}

// ---------------------------------------------------------------- 게이트 ② 일관성

func TestRecordConsistencyProvesSnapshotTime(t *testing.T) {
	// 61+50+2 = 113 ✅ — 이 검사가 스냅샷 시점을 증명한다(2026-08-27 실측)
	if bad := consistency(realKBO); len(bad) != 0 {
		t.Fatalf("정합한 전적을 버렸다: %v", bad)
	}
	broken := map[string]string{"home_w": "61", "home_l": "50", "home_d": "2", "home_g": "120"}
	bad := consistency(broken)
	for _, k := range []string{"home_w", "home_l", "home_d", "home_g"} {
		if _, ok := bad[k]; !ok {
			t.Errorf("%s가 폐기되지 않았다 — 전적 블록은 통째로 버려야 한다", k)
		}
	}
}

func TestDuplicateInLineupIsDropped(t *testing.T) {
	dup := "김도영-박상준-김도영-카스트로-나성범-하주석-김호령-김태군-박정우"
	bad := consistency(map[string]string{"lineup_home": dup})
	if msg, ok := bad["lineup_home"]; !ok || !strings.Contains(msg, "김도영") {
		t.Errorf("타순 중복을 못 잡았다: %v", bad)
	}
}

func TestSameStarterBothSidesIsDropped(t *testing.T) {
	bad := consistency(map[string]string{"home_pitcher": "네일", "away_pitcher": "네일"})
	if len(bad) != 2 {
		t.Errorf("양 팀 선발 동일인을 못 잡았다: %v", bad)
	}
}

func TestDropsAreRecordedNotSilent(t *testing.T) {
	// 조용한 폐기는 조용한 오염만큼 위험하다 — 무엇을 왜 버렸는지 남아야 한다.
	_, drops := Apply(diff.Snapshot{"A@B": {"home_era": "189.00"}})
	if len(drops) != 1 {
		t.Fatalf("폐기 기록 %d건", len(drops))
	}
	d := drops[0]
	if d.Game != "A@B" || d.Field != "home_era" || d.Value != "189.00" ||
		d.Gate != "물리" || d.Reason == "" {
		t.Errorf("폐기 기록이 부실하다: %+v", d)
	}
	if !strings.Contains(d.String(), "189.00") {
		t.Errorf("사람이 읽을 문장에 값이 없다: %s", d)
	}
}

func TestApplyDoesNotMutateInput(t *testing.T) {
	in := diff.Snapshot{"A@B": {"home_era": "189.00", "home_pitcher": "네일"}}
	Apply(in)
	if len(in["A@B"]) != 2 {
		t.Errorf("원본이 수정됐다 — 게이트가 정상 데이터를 버리는지 비교할 수 없게 된다")
	}
}
