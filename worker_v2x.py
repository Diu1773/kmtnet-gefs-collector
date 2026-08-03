# -*- coding: utf-8 -*-
"""GEFS 2차 패스 수집기 (v2x) — 지표층 난류 변수 + 지오포텐셜 고도 (2026-08-03).

왜: 조건부 편향 오차분석(`사전리서치/seeing-lab/오차분석_20260803.md`) 결론 —
    나쁜 밤의 **순서는 맞히는데(구간 내 r=0.43) 진폭을 못 올린다**(십분위10 편향 −0.477″).
    보정 2종(기하평균·등분위매핑) 모두 실패 → 눈금 문제가 아니라 **재료 부재** 가설.
    그런데 현행 피처에 **지표층 난류 강도를 나타내는 변수가 하나도 없다**.
    GEFS 는 그걸 주는데 v2 수집 스펙에서 빠져 있었다(`VARIABLES.md` A급).
    → WRF(4~6일) 보다 싸게 같은 가설을 시험한다.

수집 대상 (전부 atmos.5b)
  HPBL   surface                     경계층 높이 (실측 23~137 m 변동 확인)
  FRICV  surface                     마찰속도 u* — 지표 난류 강도 그 자체
  GUST   surface                     돌풍 (평균풍이 못 담는 요동)
  VRATE  planetary boundary layer    환기율 (잔잔한 밤 0, 난 밤 500 — 실측 확인)
  HGT    15 공통 기압면               지오포텐셜 고도 → 층 두께 → 미터당 안정도(N²·Ri) 계산용
         v11 16층 ∩ v12 20층 = 15층 (1·2·3·5·7 hPa 는 v11 결측이라 자동 제외됨)

범위: **lead 24h(day1) · 5멤버 · 2017-01-01~2023-12-31** — 가설 시험에 필요한 최소 범위.
      최적 config(26층·00Z·5멤버)와 정확히 같은 표본이라 바로 붙여 비교할 수 있다.
      12,780 단위 → 10레인에서 약 6시간. 가설이 맞으면 전 리드로 확장한다.
저장: data/v2x/{YYYY-MM}_m{M}.jsonl.gz — v2 와 같은 구조. 분석 시 (cycle, lead, member, site) 로 조인.
재개: v2 와 동일 — 이 멤버의 v2x gz 들에 (cycle,lead) 키가 있으면 스킵.
push: worker_v2.commit_push 재사용 (detached HEAD 안전형 · merge 기반).
"""
import argparse, datetime as dt, glob, gzip, json, os, time
import numpy as np
from worker_v2 import SITES, commit_push, purge_cache, rd, sh, DATA as V2DATA

REPO = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(REPO, "data", "v2x")
HGT_LEV = [20, 30, 70, 150, 350, 400, 450, 550, 600, 650, 750, 800, 900, 950, 975]
SFC_VARS = [(r":HPBL:surface:", "hpbl"), (r":FRICV:surface:", "fricv"),
            (r":GUST:surface:", "gust"), (r":VRATE:planetary boundary layer:", "vrate")]
LEAD = 24


def _pt(ds, var, la, lo):
    p = ds.sel(latitude=la, longitude=lo, method="nearest")
    return np.atleast_1d(p[var].values).ravel()


def fetch_unit(cycle, member, retry=3):
    """1단위 = 4사이트 × (지표·PBL 4종 + HGT 15층). 변수별 개별 search 로 이름 모호성 제거."""
    from herbie import Herbie
    for k in range(retry + 1):
        try:
            H = Herbie(cycle, model="gefs", member=member, fxx=LEAD, product="atmos.5b", verbose=False)
            acc = {s: {} for s in SITES}
            for pat, name in SFC_VARS:
                ds = H.xarray(pat, remove_grib=True)
                if isinstance(ds, list): ds = ds[0]
                v = list(ds.data_vars)[0]          # 개별 search 라 변수 1개 — 'unknown' 이름도 안전
                for s, (la, lo) in SITES.items():
                    acc[s][name] = float(_pt(ds, v, la, lo)[0])
            ds = H.xarray(r":HGT:\d+ mb", remove_grib=True)
            if isinstance(ds, list): ds = ds[0]
            lv = [int(x) for x in np.atleast_1d(ds["gh"].isobaricInhPa.values)]
            for s, (la, lo) in SITES.items():
                vv = _pt(ds, "gh", la, lo)
                acc[s]["hgt"] = [rd(float(vv[lv.index(L)])) if L in lv else None for L in HGT_LEV]
            return acc
        except Exception as e:
            m = str(e)
            if "Slow Down" in m or "503" in m or "429" in m:
                time.sleep(10 * (k + 1)); continue
            if k >= retry: return None
            time.sleep(4)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--member", type=int, required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--budget-min", type=float, default=300)
    ap.add_argument("--commit-every-min", type=float, default=22)
    ap.add_argument("--seg", default="x0")
    ap.add_argument("--stagger", type=int, default=0)
    a = ap.parse_args()
    M = a.member
    a.commit_every_min += a.stagger
    os.makedirs(DATA, exist_ok=True)

    done = set()
    for fn in glob.glob(os.path.join(DATA, f"*_m{M}.jsonl.gz")):
        try:
            with gzip.open(fn, "rt", encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                        if r["site"] == "paranal": done.add(r["cycle"])
                    except Exception: pass
        except Exception: pass
    fails_path = os.path.join(DATA, f"fails_m{M}_{a.seg}.json")
    fails = json.load(open(fails_path, encoding="utf-8")) if os.path.exists(fails_path) else {}
    print(f"v2x m{M}/{a.seg}: 기수집 {len(done):,} 사이클 · 실패기록 {len(fails)}", flush=True)

    t0 = last = time.time(); ok = skip = fail = 0
    day = dt.date.fromisoformat(a.start); d1 = dt.date.fromisoformat(a.end)
    while day <= d1:
        if (time.time() - t0) / 60 > a.budget_min: break
        cycle = f"{day.isoformat()} 00:00"
        if cycle in done or fails.get(cycle, 0) >= 3:
            skip += 1; day += dt.timedelta(days=1); continue
        got = fetch_unit(cycle, M)
        if got is None:
            fails[cycle] = fails.get(cycle, 0) + 1; fail += 1
            print(f"FAIL {cycle} ({fails[cycle]}회)", flush=True)
        else:
            valid = (dt.datetime.combine(day, dt.time()) + dt.timedelta(hours=LEAD)).strftime("%Y-%m-%d %H:%M")
            outp = os.path.join(DATA, f"{day.strftime('%Y-%m')}_m{M}.jsonl.gz")
            with gzip.open(outp, "at", encoding="utf-8") as fo:
                for s in SITES:
                    r = {"site": s, "cycle": cycle, "valid": valid, "member": M, "lead": LEAD,
                         "hgt_lv": HGT_LEV}
                    for kk in ("hpbl", "fricv", "gust", "vrate"): r[kk] = rd(got[s].get(kk))
                    r["hgt"] = got[s]["hgt"]
                    fo.write(json.dumps(r, ensure_ascii=False) + "\n")
            done.add(cycle); ok += 1
            if ok % 50 == 0:
                print(f"진행 m{M}: {cycle} · ok {ok} · {(time.time()-t0)/60:.0f}분", flush=True)
        if (time.time() - last) / 60 > a.commit_every_min:
            json.dump(fails, open(fails_path, "w", encoding="utf-8"))
            commit_push(f"v2x m{M}/{a.seg} @ {cycle} (ok {ok})")
            last = time.time()
        purge_cache()
        day += dt.timedelta(days=1)
    json.dump(fails, open(fails_path, "w", encoding="utf-8"))
    commit_push(f"v2x m{M}/{a.seg} 세션종료 (ok {ok} skip {skip} fail {fail})")
    print(f"세션 종료 m{M}: ok {ok} · skip {skip} · fail {fail} · {(time.time()-t0)/60:.0f}분")


if __name__ == "__main__":
    main()
