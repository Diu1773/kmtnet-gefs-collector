# -*- coding: utf-8 -*-
"""GEFS 백필 워커 — 멤버 1개 담당, 2017~2023 순차 수집 (GitHub Actions 릴레이용).
- 재개형: data/gefs_ens_{year}_m{M}.jsonl 의 기존 키(cycle,member,lead)는 스킵
- 멤버별 파일 분리 → 병렬 잡 간 같은 파일을 안 건드려 push 충돌 원천 차단
- 중간 커밋: --commit-every-min 마다 add/commit/push(rebase 재시도 5회) — 머신 사망 시 손실 최소화
- 영구 결측 대응: 3회 실패한 키는 data/fails_m{M}.json에 기록하고 이후 스킵 (무한 재시도 방지)
- 시간 예산: --budget-min 넘으면 곱게 커밋하고 종료 (다음 크론이 이어받음)
"""
import argparse, datetime as dt, json, os, subprocess, sys, time
from collect import fetch, make_feats   # 1일치 검증(2026-07-24)과 동일 경로 재사용

REPO = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(REPO, "data")

def sh(*args):
    return subprocess.run(list(args), cwd=REPO, capture_output=True, text=True)

def commit_push(msg):
    import random
    sh("git", "add", "data")
    r = sh("git", "commit", "-m", msg)
    if "nothing to commit" in (r.stdout + r.stderr): return True
    for i in range(10):                       # [v2] 5→10회 + 랜덤 백오프 (동시시작 경합 대응)
        sh("git", "pull", "--rebase")         # [v2] push 전에 먼저 rebase
        p = sh("git", "push")
        if p.returncode == 0: return True
        print(f"push 재시도 {i+1}: {p.stderr.strip()[-200:]}", flush=True)   # [v3] 에러 노출
        time.sleep(random.uniform(2, 8) * (1 + i * 0.5))
    print("push 실패 10회 — 다음 커밋 때 재시도", flush=True)
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--member", type=int, required=True)
    ap.add_argument("--start", default="2017-01-01")
    ap.add_argument("--end", default="2023-12-31")
    ap.add_argument("--leads", default="24,48,72,96,120,144,168")
    ap.add_argument("--budget-min", type=float, default=320)
    ap.add_argument("--commit-every-min", type=float, default=25)
    a = ap.parse_args()
    M = a.member
    a.commit_every_min += M * 4               # [v2] 멤버별 커밋주기 어긋내기 (25,29,33,37,41분) — 경합 원천 완화
    leads = [int(x) for x in a.leads.split(",")]
    os.makedirs(DATA, exist_ok=True)

    # 재개 상태 로드 (이 멤버의 모든 연도 파일 + 실패 기록)
    done = set()
    for fn in os.listdir(DATA):
        if fn.startswith("gefs_ens_") and fn.endswith(f"_m{M}.jsonl"):
            for line in open(os.path.join(DATA, fn), encoding="utf-8"):
                try:
                    r = json.loads(line); done.add((r["cycle"], r["lead"]))
                except Exception: pass
    fails_path = os.path.join(DATA, f"fails_m{M}.json")
    fails = json.load(open(fails_path, encoding="utf-8")) if os.path.exists(fails_path) else {}

    t0 = time.time(); last_commit = t0; n_ok = n_skip = n_fail = 0
    d0 = dt.date.fromisoformat(a.start); d1 = dt.date.fromisoformat(a.end)
    day = d0
    stop = False
    while day <= d1 and not stop:
        cycle = f"{day.isoformat()} 00:00"
        out = os.path.join(DATA, f"gefs_ens_{day.year}_m{M}.jsonl")
        with open(out, "a", encoding="utf-8") as fo:
            for fxx in leads:
                if (time.time() - t0) / 60 > a.budget_min:
                    stop = True; break
                key = (cycle, fxx); ks = f"{cycle}|{fxx}"
                if key in done or fails.get(ks, 0) >= 3:
                    n_skip += 1; continue
                g = fetch(cycle, fxx, M)
                if g is None:
                    fails[ks] = fails.get(ks, 0) + 1; n_fail += 1
                    print(f"FAIL {cycle} f{fxx} ({fails[ks]}회)", flush=True); continue
                valid = (dt.datetime.combine(day, dt.time()) + dt.timedelta(hours=fxx)).strftime("%Y-%m-%d %H:%M")
                row = {"cycle": cycle, "valid": valid, "member": M, "lead": fxx, **make_feats(g)}
                fo.write(json.dumps(row, ensure_ascii=False) + "\n"); fo.flush()
                n_ok += 1
                if n_ok % 50 == 0:
                    print(f"진행 m{M}: {cycle} · ok {n_ok} · {(time.time()-t0)/60:.0f}분", flush=True)
                if (time.time() - last_commit) / 60 > a.commit_every_min:
                    json.dump(fails, open(fails_path, "w", encoding="utf-8"))
                    commit_push(f"backfill m{M} @ {cycle} (ok {n_ok})")
                    last_commit = time.time()
        day += dt.timedelta(days=1)

    json.dump(fails, open(fails_path, "w", encoding="utf-8"))
    commit_push(f"backfill m{M} 세션 종료 @ {day.isoformat()} (ok {n_ok} skip {n_skip} fail {n_fail})")
    print(f"세션 종료 m{M}: ok {n_ok} · skip {n_skip} · fail {n_fail} · {(time.time()-t0)/60:.0f}분 · 마지막 {day.isoformat()}")
    if day > d1 and n_ok == 0 and n_fail == 0:
        print(f"멤버 {M} 백필 완료 상태 — 더 받을 것 없음")

if __name__ == "__main__":
    main()
