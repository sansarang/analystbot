#!/bin/bash
# UserPromptSubmit — 매 턴 머리에 **지금**을 박는다.
#
# 🔴 실사고 2026-09-13: 봇이 오늘(9/13 13:30 JST) 소뱅 경기 대신 **어제(9/12
#    18:00)** 행을 판정했다. 사용자 지적: "빗나간 게 아니라 봇이 어제 경기를
#    판정한 겁니다. 판단이 갈린 게 아니라 입력이 틀렸어요. 오늘은 일요일이다."
#    세 시간대를 눈앞에 두면 "오늘"을 착각할 자리가 줄어든다.
# ⚠️ NPB=JST · KBO/발송=KST · MLB/DB=UTC. 셋을 한 줄에 같이 본다.
echo "[NOW] UTC=$(date -u +%FT%TZ) KST=$(TZ=Asia/Seoul date '+%F %T %a') JST=$(TZ=Asia/Tokyo date '+%F %T %a')"
