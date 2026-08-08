# -*- coding: utf-8 -*-
"""gzip 조각파일이 중간에 끊겼는지 보고, 끊겼으면 읽히는 데까지만 남긴다 (2026-08-08).

왜 필요한가
  수집기는 `gzip.open(..., "at")` 로 **덧붙이기**를 한다. 정상 종료면 안전하지만,
  전원이 갑자기 나가면 마지막 gzip 멤버가 잘린 채 남는다. 그러면
    ① 그 파일을 읽을 때 예외가 나고,
    ② 수집기의 재개 로직이 그 파일 전체를 통째로 버려서 **이미 받은 밤을 다시 받는다**,
    ③ 그 뒤에 또 덧붙이면 깨진 조각이 파일 가운데에 영영 남는다.

무엇을 하나
  파일마다 한 줄씩 읽어 보고, 도중에 끊기면 **읽힌 줄까지만** 새로 써서 갈아 끼운다.
  줄 단위로 다시 압축하므로 잘린 조각은 사라지고 나머지는 그대로다.

쓰는 법
    python -X utf8 verify_repair_v2.py            # 검사만
    python -X utf8 verify_repair_v2.py --fix      # 끊긴 파일을 고친다
"""
import glob
import gzip
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "v2")
FIX = "--fix" in sys.argv


def scan(path):
    """(정상 줄 수, 끊겼나, 사유)"""
    good = 0
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                json.loads(line)          # 줄 자체가 깨졌으면 여기서 걸린다
                good += 1
    except Exception as e:
        return good, True, f"{type(e).__name__}: {str(e)[:60]}"
    return good, False, ""


def repair(path, keep):
    """읽히는 keep 줄까지만 남기고 다시 쓴다."""
    rows = []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                if len(rows) >= keep:
                    break
                line = line.strip()
                if line:
                    rows.append(line)
    except Exception:
        pass
    bak = path + f".broken.{int(time.time())}"
    os.rename(path, bak)
    with gzip.open(path, "wt", encoding="utf-8") as fo:
        for r in rows:
            fo.write(r + "\n")
    return bak, len(rows)


files = sorted(glob.glob(os.path.join(DATA, "*.jsonl.gz")))
print(f"검사 대상 {len(files)}개")
bad = []
tot = 0
for p in files:
    good, broken, why = scan(p)
    tot += good
    if broken:
        bad.append((p, good, why))
        print(f"  ★ 끊김 {os.path.basename(p)} — 읽힌 줄 {good:,} · {why}")
print(f"정상 줄 합계 {tot:,} · 끊긴 파일 {len(bad)}개")

if bad and FIX:
    print("\n고치는 중 (원본은 .broken.<시각> 으로 남긴다)")
    for p, good, _ in bad:
        bak, n = repair(p, good)
        print(f"  {os.path.basename(p)}: {n:,}줄로 다시 씀 · 원본 {os.path.basename(bak)}")
    print("완료 — 수집기를 다시 돌리면 빠진 밤부터 이어받는다")
elif bad:
    print("\n고치려면 --fix 를 붙여 다시 실행")
else:
    print("끊긴 파일 없음")
