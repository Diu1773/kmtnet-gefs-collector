# -*- coding: utf-8 -*-
"""GEFS 수집 워커 v2 — 풀스펙: 31층(a+b)·4사이트·전시각 리드·TCDC/PWAT(컨트롤).
설계 (2026-07-25):
- 우선순위 2패스: pass1=야간+전조 리드(시잉 MOS 우선) → pass2=나머지 시각
- 저장: data/v2/{YYYY-MM}_m{M}.jsonl.gz — 월별 샤딩(깃 이력 비대 방지)·gzip 스트림 append(중단 안전)
- 행: 사이트별 1행, 레벨값은 고정순서 배열(콤팩트), 소수 2자리 반올림
- 재개: (cycle,lead) 키가 이 멤버 gz들에 있으면 스킵 / 3회 실패 키 기록 스킵
- 러너 디스크: 사이클마다 herbie 캐시 청소
- push: v4 검증 로직(autostash·abort·랜덤백오프) 재사용
"""
import argparse, datetime as dt, glob, gzip, json, os, shutil, subprocess, time
import numpy as np

REPO = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(REPO, "data", "v2")
SITES = {  # lon은 0~360
    "paranal": (-24.6275, 289.5956),
    "ctio":    (-30.1690, 289.1946),
    "saao":    (-32.3790, 20.8107),
    "sso":     (-31.2720, 149.0620),
}
LEV_A = [10, 50, 100, 200, 250, 500, 700, 850, 925, 1000]
LEV_B = [1, 2, 3, 5, 7, 20, 30, 70, 150, 300, 350, 400, 450, 550, 600, 650, 750, 800, 900, 950, 975]
LEVELS = sorted(LEV_A + LEV_B)          # 31층 고정 순서 (행의 t/u/v 배열 순서)
V12_START = dt.date(2020, 9, 23)        # GEFSv12 운영 전환

def sh(*args):
    return subprocess.run(list(args), cwd=REPO, capture_output=True, text=True)

def commit_push(msg):
    import random
    sh("git", "add", "data")
    r = sh("git", "commit", "-m", msg)
    if "nothing to commit" in (r.stdout + r.stderr): return True
    for i in range(10):
        sh("git", "rebase", "--abort")
        r2 = sh("git", "pull", "--rebase", "--autostash")
        if r2.returncode != 0:
            st = sh("git", "status", "--short")
            print(f"pull 실패 {i+1}: {r2.stderr.strip()[-150:]} | {st.stdout.strip()[:120]}", flush=True)
        p = sh("git", "push")
        if p.returncode == 0: return True
        print(f"push 재시도 {i+1}: {p.stderr.strip()[-120:]}", flush=True)
        time.sleep(np.random.uniform(2, 8) * (1 + i * 0.5))
    print("push 실패 10회 — 다음 커밋 때 재시도", flush=True)
    return False

def purge_cache():
    for d in (os.path.expanduser("~/data"), os.path.expanduser("~/.cache/herbie")):
        shutil.rmtree(d, ignore_errors=True)

def rd(x): return None if x is None or not np.isfinite(x) else round(float(x), 2)

def extract_points(H, search, want_vars):
    """search로 레코드 받고 4사이트 최근접점 추출 → {var: {lev: {site: val}}} (지표는 lev=None)"""
    out = {}
    dss = H.xarray(search, remove_grib=True)
    if not isinstance(dss, list): dss = [dss]
    for ds in dss:
        pts = {s: ds.sel(latitude=la, longitude=lo, method="nearest") for s, (la, lo) in SITES.items()}
        for var in ds.data_vars:
            if want_vars and var not in want_vars: continue
            ref = pts["paranal"]
            if "isobaricInhPa" in ref[var].coords:
                lvs = np.atleast_1d(ref["isobaricInhPa"].values).astype(int)
                for s, p in pts.items():
                    vv = np.atleast_1d(p[var].values).ravel()
                    for i, L in enumerate(lvs):
                        out.setdefault(var, {}).setdefault(int(L), {})[s] = float(vv[i])
            else:
                for s, p in pts.items():
                    out.setdefault(var, {}).setdefault(None, {})[s] = float(np.atleast_1d(p[var].values).ravel()[0])
    return out

def fetch_unit(cycle, fxx, member, retry=3):
    """1단위 = 상층 a+b(4사이트 31층 t/u/v) + 지표(a) + [컨트롤] 0.25° TCDC/PWAT"""
    from herbie import Herbie
    for k in range(retry + 1):
        try:
            acc = {}
            Ha = Herbie(cycle, model="gefs", member=member, fxx=fxx, product="atmos.5", verbose=False)
            for var, lev, sv in _iter(extract_points(Ha, r":(TMP|UGRD|VGRD):(\d+) mb", ("t", "u", "v"))): acc.setdefault(var, {})[lev] = sv
            sfc = extract_points(Ha, r":(UGRD|VGRD):10 m above|:TMP:2 m above|:RH:2 m above|:PRES:surface", None)
            Hb = Herbie(cycle, model="gefs", member=member, fxx=fxx, product="atmos.5b", verbose=False)
            for var, lev, sv in _iter(extract_points(Hb, r":(TMP|UGRD|VGRD):(\d+) mb", ("t", "u", "v"))): acc.setdefault(var, {})[lev] = sv
            ext = None
            if member == 0:
                try:
                    H25 = Herbie(cycle, model="gefs", member=0, fxx=fxx, product="atmos.25", verbose=False)
                    ext = extract_points(H25, r":(TCDC|PWAT):", None)
                except Exception: ext = None
            return acc, sfc, ext
        except Exception as e:
            s = str(e)
            if "Slow Down" in s or "503" in s or "429" in s: time.sleep(10 * (k + 1)); continue
            if k >= retry: return None
            time.sleep(4)
    return None

def _iter(d):
    for var, levs in d.items():
        for lev, sv in levs.items():
            yield var, lev, sv

def rows_from(cycle, valid, member, fxx, acc, sfc, ext):
    rows = []
    for s in SITES:
        r = {"site": s, "cycle": cycle, "valid": valid, "member": member, "lead": fxx, "lv": LEVELS}
        for var in ("t", "u", "v"):
            r[var] = [rd(acc.get(var, {}).get(L, {}).get(s)) for L in LEVELS]
        for var, levs in sfc.items():
            for lev, sv in levs.items():
                r[f"sfc_{var}"] = rd(sv.get(s))
        u10, v10 = r.get("sfc_u10"), r.get("sfc_v10")
        if u10 is not None and v10 is not None: r["sfc_ws10"] = rd(float(np.hypot(u10, v10)))
        if ext:
            for var, levs in ext.items():
                for lev, sv in levs.items():
                    r[{"tcc": "tcdc"}.get(var.lower(), var.lower())] = rd(sv.get(s))
        rows.append(r)
    return rows

def leads_for(day, night_first):
    v12 = day >= V12_START
    step = 3 if v12 else 6
    allL = list(range(step, 169, step))
    night = sorted({h for d0 in range(0, 8) for h in ([d0*24+x for x in (0,3,6,9)] if v12 else [d0*24+x for x in (0,6)]) if step <= h <= 168}
                   | ({d0*24 - 6 for d0 in range(1, 8)} | {d0*24 - 3 for d0 in range(1, 8)} if v12 else {d0*24 - 6 for d0 in range(1, 8)}))
    night = [h for h in night if step <= h <= 168 and h % step == 0]
    return night if night_first else [h for h in allL if h not in set(night)]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--member", type=int, required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--budget-min", type=float, default=310)
    ap.add_argument("--commit-every-min", type=float, default=22)
    ap.add_argument("--seg", default="s0", help="레인 태그 — fails 파일 분리 + 커밋 스태거")
    ap.add_argument("--stagger", type=int, default=0, help="커밋주기 오프셋(분) — 레인별 고유값")
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
                        if r["site"] == "paranal": done.add((r["cycle"], r["lead"]))
                    except Exception: pass
        except Exception: pass
    fails_path = os.path.join(DATA, f"fails_m{M}_{a.seg}.json")
    fails = json.load(open(fails_path, encoding="utf-8")) if os.path.exists(fails_path) else {}

    t0 = time.time(); last_commit = t0; n_ok = n_skip = n_fail = 0
    d0 = dt.date.fromisoformat(a.start); d1 = dt.date.fromisoformat(a.end)
    stop = False
    for night_first in (True, False):                       # pass1: 야간+전조 / pass2: 나머지
        if stop: break
        day = d0
        while day <= d1 and not stop:
            cycle = f"{day.isoformat()} 00:00"
            outp = os.path.join(DATA, f"{day.strftime('%Y-%m')}_m{M}.jsonl.gz")
            for fxx in leads_for(day, night_first):
                if (time.time() - t0) / 60 > a.budget_min: stop = True; break
                key = (cycle, fxx); ks = f"{cycle}|{fxx}"
                if key in done or fails.get(ks, 0) >= 3: n_skip += 1; continue
                got = fetch_unit(cycle, fxx, M)
                if got is None:
                    fails[ks] = fails.get(ks, 0) + 1; n_fail += 1
                    print(f"FAIL {cycle} f{fxx} ({fails[ks]}회)", flush=True); continue
                valid = (dt.datetime.combine(day, dt.time()) + dt.timedelta(hours=fxx)).strftime("%Y-%m-%d %H:%M")
                with gzip.open(outp, "at", encoding="utf-8") as fo:   # gzip 스트림 append (중단 안전)
                    for r in rows_from(cycle, valid, M, fxx, *got):
                        fo.write(json.dumps(r, ensure_ascii=False) + "\n")
                done.add(key); n_ok += 1
                if n_ok % 50 == 0:
                    print(f"진행 m{M} p{1 if night_first else 2}: {cycle} f{fxx} · ok {n_ok} · {(time.time()-t0)/60:.0f}분", flush=True)
                if (time.time() - last_commit) / 60 > a.commit_every_min:
                    json.dump(fails, open(fails_path, "w", encoding="utf-8"))
                    commit_push(f"v2 m{M}/{a.seg} p{1 if night_first else 2} @ {cycle} (ok {n_ok})")
                    last_commit = time.time()
            purge_cache()
            day += dt.timedelta(days=1)
    json.dump(fails, open(fails_path, "w", encoding="utf-8"))
    commit_push(f"v2 m{M}/{a.seg} 세션종료 (ok {n_ok} skip {n_skip} fail {n_fail})")
    print(f"세션 종료 m{M}: ok {n_ok} · skip {n_skip} · fail {n_fail} · {(time.time()-t0)/60:.0f}분")

if __name__ == "__main__":
    main()
