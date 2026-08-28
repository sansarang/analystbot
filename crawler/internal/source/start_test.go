package source

import (
	"testing"
	"time"
)

func TestParseNaverStart(t *testing.T) {
	kst := time.FixedZone("KST", 9*3600)
	got, ok := parseNaverStart("2026-08-28T18:30:00", kst)
	if !ok {
		t.Fatal("parse failed")
	}
	if got.Hour() != 18 || got.Minute() != 30 {
		t.Fatalf("got %v", got)
	}
}

func TestParseNaverStartRFC3339KeepsOffset(t *testing.T) {
	kst := time.FixedZone("KST", 9*3600)
	got, ok := parseNaverStart("2026-08-28T18:30:00+09:00", kst)
	if !ok || got.In(kst).Hour() != 18 {
		t.Fatalf("KST offset 파싱 실패: %v %v", got, ok)
	}
}

func TestParseYahooClockSkipsFinals(t *testing.T) {
	if npbUpcoming("神宮 ヤクルト 巨人 6 - 8 試合終了") {
		t.Fatal("종료 경기를 예정으로 봤다")
	}
	kst := time.FixedZone("KST", 9*3600)
	got, ok := parseYahooClock("神宮 ヤクルト 巨人 18:00 (予)山野", "2026-08-28", kst)
	if !ok || got.Hour() != 18 {
		t.Fatalf("18:00 파싱 실패: %v %v", got, ok)
	}
}

func TestParseYahooClockUsesFirstClockFromLiveInner(t *testing.T) {
	// 실측 2026-08-28 gm_card inner. 점수가 없는 예정이라 시계는 하나다.
	kst := time.FixedZone("KST", 9*3600)
	inner := "横浜 DeNA 中日 18:00 見どころ (予)尾形 (予)髙橋宏"
	got, ok := parseYahooClock(inner, "2026-08-28", kst)
	if !ok || got.Hour() != 18 || got.Minute() != 0 {
		t.Fatalf("실측 inner 시계 실패: %v %v", got, ok)
	}
}

func TestKBOUpcoming(t *testing.T) {
	if !kboUpcoming("경기전") {
		t.Fatal("경기전은 예정이다")
	}
	if kboUpcoming("경기종료") || kboUpcoming("경기중") {
		t.Fatal("종료·진행 중을 예정으로 봤다")
	}
}

func TestKeepKBOGameDropsEtcCategory(t *testing.T) {
	// 실측 2026-08-28: 팀명 빈 kbaseballetc 가 13:00/17:00으로 섞여 있다.
	if keepKBOGame("kbaseballetc", "삼성", "KT", "x") {
		t.Fatal("kbaseballetc를 1군으로 봤다")
	}
	if !keepKBOGame("kbo", "삼성", "KT", "20260828KTSS02026") {
		t.Fatal("1군 kbo를 버렸다")
	}
	if !keepKBOGame("", "삼성", "KT", "x") {
		t.Fatal("categoryId 없는 옛 응답을 버리면 안 된다")
	}
	if keepKBOGame("kbo", "", "", "x") {
		t.Fatal("팀명 없는 경기를 넣었다")
	}
}
