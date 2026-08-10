# -*- coding: utf-8 -*-
"""리드 **하나만** 골라 받는 좁은 백필 — 2024~ 라벨 구간을 학습에 쓰려고 (2026-08-08).

리드는 `--lead` 로 고른다. **기본값 24** 이므로 2026-08-08 의 리드24 백필 명령은
한 글자도 안 바꾸고 그대로 돈다 (파일 이름만 `backfill_lead24.py` → `backfill_lead.py`).

왜 따로 만드나
  라벨(DIMM·MASS)은 이미 2015~2026 이 다 있는데 **GEFS 가 2017~2023 뿐**이라
  학습에 쓰는 밤이 2,180 밤에서 막혀 있다. 통계리포트 §9.5 가 재 보니
  밤을 2배로 모으면 총시잉 상관이 +0.054 오른다 — 지금 가장 값어치 있는 다음 걸음이다.

  그런데 `worker_v2.py` 는 하루에 리드를 30개 넘게 받는다(2024년부터는 3시간 간격).
  한 단위가 약 160초라 노트북에서 전체 스펙은 몇 달이 걸린다.
  그래서 **필요한 리드만 하나씩** 받는다.

  2026-08-08 에는 리드24(1일)만 받았다. 2026-08-10 에 리드 **72(3일)·168(7일)** 을 더 받는다 —
  §9.5 의 「밤을 늘리면 오른다」가 1일에서만 검증돼 있어서, 리포트가 중심축으로 쓰는
  **리드 1·3·7일** 세 점의 밤 수가 서로 달랐기 때문이다(1일 10년 vs 3·7일 7년).

worker_v2.py 를 고치지 않는다
  fetch_unit·rows_from·purge_cache 를 그대로 가져다 쓴다. 출력 파일도 같은 규약
  (`data/v2/{YYYY-MM}_m{M}.jsonl.gz`)이라 기존 적재 경로가 그대로 읽는다.

git 은 기본으로 건드리지 않는다
  `--commit-every-min` 을 주지 않으면 로컬에 쌓기만 한다. GitHub Actions 에서는 러너가
  사라지므로 그 값을 줘서 주기적으로 commit·push 해야 한다 (worker_v2 의 함수를 그대로 쓴다).

속도 (2026-08-08 실측)
  1 단위(1밤 × 1멤버 × 1리드) 약 160초. 노트북 5프로세스 병렬로 **시간당 30개** 뿐이다
  (CPU/디스크 경합이라 병렬 이득이 1.3배밖에 안 난다). GitHub Actions 는 같은 일을
  **시간당 800개** 한다(backfill_v2.yml 주석). 950일 × 5멤버 = 4,750단위이므로
  **노트북 6일 vs Actions 6시간**이다. 정공법은 Actions 다.

쓰는 법 (멤버마다 프로세스 하나 — 스레드로 돌리면 eccodes 가 깨진다, 2026-08-08 실측)
    python -X utf8 backfill_lead.py --member 1 --start 2024-01-01 --end 2026-08-07
    python -X utf8 backfill_lead.py --member 1 --lead 72 --start 2024-01-01 --end 2024-12-31
    python -X utf8 backfill_lead.py --member 1 ... --commit-every-min 20   # Actions 용

⚠ `--seg` 는 레인마다 달라야 한다. 실패 기록을 `fails_m{M}_{seg}.json` 에 쓰기 때문에
  같은 seg 를 쓰는 두 레인이 서로의 기록을 덮어쓴다. 리드까지 섞이면 더 위험하므로
  기본값을 `L{lead}` 로 두었다 (리드24 → `L24`, 리드72 → `L72`).
"""
import argparse
import datetime as dt
import gzip
import json
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from worker_v2 import DATA, commit_push, fetch_unit, purge_cache, rows_from    # noqa: E402



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--member", type=int, required=True)
    ap.add_argument("--lead", type=int, default=24,
                    help="받을 리드(시간). 기본 24 — 2026-08-08 명령과 동일하게 돈다")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--budget-min", type=float, default=1e9, help="이 분을 넘기면 곱게 종료")
    ap.add_argument("--commit-every-min", type=float, default=0,
                    help="0 이면 git 을 안 건드린다. Actions 처럼 러너가 사라지는 곳에서만 준다")
    ap.add_argument("--seg", default=None,
                    help="fails 파일 태그 — 레인끼리 안 겹치게. 비우면 L{lead}")
    ap.add_argument("--stagger", type=int, default=0,
                    help="커밋주기 오프셋(분) — 레인끼리 push 경합을 어긋내려고")
    a = ap.parse_args()
    M = a.member
    LEAD = a.lead
    if not a.seg:
        a.seg = f"L{LEAD}"
    a.commit_every_min += a.stagger if a.commit_every_min else 0
    d0 = dt.date.fromisoformat(a.start); d1 = dt.date.fromisoformat(a.end)
    os.makedirs(DATA, exist_ok=True)

    # 재개 — 이미 받은 (cycle, lead) 는 건너뛴다
    done = set()
    import glob
    for fn in glob.glob(os.path.join(DATA, f"*_m{M}.jsonl.gz")):
        try:
            with gzip.open(fn, "rt", encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                        if r["site"] == "paranal": done.add((r["cycle"], r["lead"]))
                    except Exception: pass
        except Exception: pass

    fails_path = os.path.join(DATA, f"fails_m{M}_{a.seg}.json")
    fails = json.load(open(fails_path, encoding="utf-8")) if os.path.exists(fails_path) else {}

    t0 = time.time(); last_commit = t0; n_ok = n_skip = n_fail = 0
    total = (d1 - d0).days + 1
    print(f"■ 리드{LEAD} 백필 m{M} · {d0} ~ {d1} ({total}일) · 이미 있는 키 {len(done):,}", flush=True)
    day = d0
    while day <= d1:
        if (time.time() - t0) / 60 > a.budget_min:
            print("시간 예산 초과 — 종료", flush=True); break
        cycle = f"{day.isoformat()} 00:00"
        key = (cycle, LEAD); ks = f"{cycle}|{LEAD}"
        if key in done or fails.get(ks, 0) >= 3:
            n_skip += 1; day += dt.timedelta(days=1); continue
        got = fetch_unit(cycle, LEAD, M)
        if got is None:
            fails[ks] = fails.get(ks, 0) + 1; n_fail += 1
            print(f"FAIL {cycle} ({fails[ks]}회)", flush=True)
        else:
            valid = (dt.datetime.combine(day, dt.time()) + dt.timedelta(hours=LEAD)).strftime("%Y-%m-%d %H:%M")
            outp = os.path.join(DATA, f"{day.strftime('%Y-%m')}_m{M}.jsonl.gz")
            with gzip.open(outp, "at", encoding="utf-8") as fo:      # 중단 안전 append
                for r in rows_from(cycle, valid, M, LEAD, *got):
                    fo.write(json.dumps(r, ensure_ascii=False) + "\n")
            done.add(key); n_ok += 1
        if (n_ok + n_fail) % 10 == 0 and (n_ok + n_fail):
            el = (time.time() - t0) / 60
            rem = (d1 - day).days
            eta = el / max(1, n_ok + n_fail) * rem
            print(f"진행 m{M}: {cycle} · ok {n_ok} fail {n_fail} · {el:.0f}분 경과 · "
                  f"남은 {rem}일 ≈ {eta/60:.1f}시간", flush=True)
            json.dump(fails, open(fails_path, "w", encoding="utf-8"))
        if a.commit_every_min and (time.time() - last_commit) / 60 > a.commit_every_min:
            json.dump(fails, open(fails_path, "w", encoding="utf-8"))
            commit_push(f"lead{LEAD} m{M}/{a.seg} @ {cycle} (ok {n_ok})")
            last_commit = time.time()
        purge_cache()
        day += dt.timedelta(days=1)
    json.dump(fails, open(fails_path, "w", encoding="utf-8"))
    if a.commit_every_min:
        commit_push(f"lead{LEAD} m{M}/{a.seg} 세션종료 (ok {n_ok} skip {n_skip} fail {n_fail})")
    print(f"■ 끝 m{M}: ok {n_ok} · skip {n_skip} · fail {n_fail} · {(time.time()-t0)/60:.0f}분", flush=True)


if __name__ == "__main__":
    main()
