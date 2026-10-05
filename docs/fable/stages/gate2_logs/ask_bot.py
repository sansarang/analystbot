"""🔴 **봇에게 묻는다** — 내가 분석하지 않는다.

사용자 지시 2026-10-04: *"너가 돌리는게 아니라... 봇이 예측을 하는거다."*

⚠️ 종전 스크립트는 `analyze.answer` 를 **직접** 불렀다 — 그것은 **프로브**다.
   봇의 명령 파싱(`vs` 가르기)·`SLATE_DAYS`·답 쪼개기를 건너뛴다.
🔴 그래서 여기서는 봇의 **핸들러 자체**(`app.bot.main.cmd_analyze`)를 부른다.
   사람이 텔레그램에 `/analyze 밀워키 브루어스 vs 샌디에이고 파드리스` 를 친 것과
   같은 경로다.
"""
import asyncio, logging, sys

logging.basicConfig(level=logging.INFO)


class Msg:
    """🔴 텔레그램 `Message` 대역 — 봇이 쓰는 두 칸(`text`·`answer`)만 있다."""

    def __init__(self, text: str):
        self.text = text
        self.out: list[str] = []

    async def answer(self, body: str) -> None:
        self.out.append(body)


async def main() -> None:
    from app.bot.main import cmd_analyze
    # 🔴🔴 **`/analyze` 접두를 붙인다**(실측 2026-10-04).
    #
    #  ⚠️ `cmd_analyze` 는 `(m.text or "").split()[1:]` 로 **첫 낱말을 버린다**
    #     (텔레그램이 `/analyze 팀 vs 상대` 로 주기 때문이다). 🔴 접두 없이
    #     주면 **첫 낱말이 사라진다**:
    #
    #       "북마케도니아 vs 스코틀랜드"  →  arg="vs 스코틀랜드"
    #         → 두 낱말이라 team="vs", opponent="스코틀랜드"
    #         → 🔴 `name_unresolved` (팀이 `vs` 다)
    #
    #  ⚠️ MLB·KBO 는 **운으로** 돌았다("밀워키 브루어스 vs …" → "브루어스" 가
    #     별칭표에 있었다). 🔴 작업지시 §2-3 이 경고한 바로 그 꼴이다 —
    #     하네스가 실제 경로와 **어긋나 거짓 통과**를 만들었다.
    m = Msg("/analyze " + " ".join(sys.argv[1:]))
    print(f"@@@SENT@@@ {m.text}")
    await cmd_analyze(m)
    print("@@@CARD@@@")
    print("\n".join(m.out))


asyncio.run(main())
