# -*- coding: utf-8 -*-
"""GEFS 앙상블 수집기 — 파라날 점 피처 추출 (GitHub Actions 무인 실행용).
사이클(날짜) × 멤버 × 리드를 받아 data/gefs_ens.jsonl에 append (중복 키 스킵 = 재개형).
라벨(DIMM)은 여기 없음 — 학습 시 로컬에서 조인 (관측자료는 이 공개 레포에 안 올림).
출처: NOAA GEFS (AWS Open Data, atmos.5) via Herbie. 기존 수치모델/GEFS/scripts/gefs_daily.py와 동일 추출 경로.
"""
import argparse, json, os, sys, time
import numpy as np

LAT, LON = -24.6275, 289.5956          # Paranal (ESO) — gefs_daily.py와 동일
UP_LEVELS = (250, 500, 700)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "gefs_ens.jsonl")

def fetch(cycle, fxx, member, retry=3):
    from herbie import Herbie
    for k in range(retry + 1):
        try:
            H = Herbie(cycle, model="gefs", member=member, fxx=fxx, product="atmos.5", verbose=False)
            g = {}
            dss = H.xarray(r":(TMP|UGRD|VGRD):(250|500|700) mb", remove_grib=True)
            if not isinstance(dss, list): dss = [dss]
            for ds in dss:
                p = ds.sel(latitude=LAT, longitude=LON, method="nearest")
                if "isobaricInhPa" in p.coords:
                    lv = np.atleast_1d(p.isobaricInhPa.values).astype(int)
                    for var in ("t", "u", "v"):
                        if var in p:
                            vv = np.atleast_1d(p[var].values).ravel()
                            for i, L in enumerate(lv):
                                if int(L) in UP_LEVELS: g[f"{var}{int(L)}"] = float(vv[i])
            sfc = H.xarray(r":(UGRD|VGRD):10 m above|:TMP:2 m above|:RH:2 m above|:PRES:surface", remove_grib=True)
            if not isinstance(sfc, list): sfc = [sfc]
            for ds in sfc:
                p = ds.sel(latitude=LAT, longitude=LON, method="nearest")
                for k2, v2 in p.data_vars.items():
                    try: g[f"sfc_{k2}"] = float(np.atleast_1d(v2.values).ravel()[0])
                    except Exception: pass
            need = [f"{v}{L}" for v in "tuv" for L in UP_LEVELS]
            if not all(kk in g for kk in need): return None
            return g
        except Exception as e:
            s = str(e)
            if "Slow Down" in s or "503" in s or "429" in s:
                time.sleep(10 * (k + 1)); continue
            if k >= retry: return None
            time.sleep(4)
    return None

def make_feats(g):
    ws = lambda L: float(np.hypot(g[f"u{L}"], g[f"v{L}"]))
    f = {"ws700": ws(700), "ws500": ws(500), "ws250": ws(250),
         "fa_ushear": abs(ws(250) - ws(700)), "fa_ushear2": abs(ws(500) - ws(700)),
         "fa_tgrad_lo": g["t700"] - g["t500"], "fa_tgrad_hi": g["t500"] - g["t250"], "t500": g["t500"]}
    for kk, vv in g.items():
        if kk.startswith("sfc_"): f[kk] = vv
    if "sfc_u10" in g and "sfc_v10" in g:
        f["sfc_ws10"] = float(np.hypot(g["sfc_u10"], g["sfc_v10"]))
    return f

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="cycle date YYYY-MM-DD (00 UTC)")
    ap.add_argument("--members", default="0,1,2,3,4")
    ap.add_argument("--leads", default="24,48,72,96,120,144,168")
    ap.add_argument("--budget-min", type=float, default=330, help="시간 예산(분) — 넘으면 안전 종료(다음 크론이 이어받음)")
    a = ap.parse_args()
    members = [int(x) for x in a.members.split(",")]
    leads = [int(x) for x in a.leads.split(",")]
    cycle = f"{a.date} 00:00"

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT, encoding="utf-8"):
            try:
                r = json.loads(line); done.add((r["cycle"], r["member"], r["lead"]))
            except Exception: pass

    t0 = time.time(); n_ok = n_skip = n_fail = 0
    with open(OUT, "a", encoding="utf-8") as fo:
        for m in members:
            for fxx in leads:
                if (time.time() - t0) / 60 > a.budget_min:
                    print(f"시간예산 초과 — 안전 종료 (ok {n_ok})"); return
                key = (cycle, m, fxx)
                if key in done:
                    n_skip += 1; continue
                g = fetch(cycle, fxx, m)
                if g is None:
                    n_fail += 1; print(f"FAIL {cycle} m{m} f{fxx}", flush=True); continue
                import datetime as dt
                valid = (dt.datetime.fromisoformat(a.date) + dt.timedelta(hours=fxx)).strftime("%Y-%m-%d %H:%M")
                row = {"cycle": cycle, "valid": valid, "member": m, "lead": fxx, **make_feats(g)}
                fo.write(json.dumps(row, ensure_ascii=False) + "\n"); fo.flush()
                n_ok += 1
                print(f"OK   {cycle} m{m} f{fxx}  ws250={row['ws250']:.1f}  ({time.time()-t0:.0f}s)", flush=True)
    print(f"완료: ok {n_ok} · skip {n_skip} · fail {n_fail} · {time.time()-t0:.0f}s")

if __name__ == "__main__":
    main()
