package source

import "testing"

func TestSnapshotKeySplitsDoubleheader(t *testing.T) {
	a := snapshotKey("LG Twins", "Doosan Bears", "G1")
	b := snapshotKey("LG Twins", "Doosan Bears", "G2")
	if a == b {
		t.Fatal("같은 카드 더블헤더 키가 같다")
	}
	if snapshotKey("A", "B", "") != "A@B" {
		t.Fatal("game_id 없으면 옛 키를 써야 한다")
	}
}
