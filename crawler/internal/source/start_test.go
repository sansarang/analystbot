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

func TestKBOUpcoming(t *testing.T) {
	if !kboUpcoming("경기전") {
		t.Fatal("경기전은 예정이다")
	}
	if kboUpcoming("경기종료") || kboUpcoming("경기중") {
		t.Fatal("종료·진행 중을 예정으로 봤다")
	}
}
