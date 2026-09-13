"""[야구 모델] 자료13 — 코드가 선발·불펜·타선·환경을 합쳐 승률을 만든다.

⚠️ 이 패키지는 **분석 전용**이다. 운영 경로(`app/engine`·`app/collectors`)를
   건드리지 않고, 저장소도 로컬 SQLite 다(`data/model_baseball.sqlite`).
   운영 접목은 7단계(결정 F·G)에서 `prob.py` 를 통해서만 한다.
"""
