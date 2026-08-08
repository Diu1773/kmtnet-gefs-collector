# -*- coding: utf-8 -*-
"""GEFS 3차 패스 수집기 (v2y) — **층별 습도(SPFH) + 층별 운량(TCDC 저·중·고)** (2026-08-04).

왜 이제 받나 — `VARIABLES.md` 2차 패스 스펙에 이렇게 적혀 있었다:

    보류: RH 22층 — 비용 +30%↑. 먼저 지금 데이터로 PWAT·2m 습도가 MOS에 실제로
    기여하는지 보고 결정. (사용자 판단 대기, 2026-07-29)

그 조건이 2026-08-04 에 측정으로 충족됐다 (`기상수치모델/스케줄링/V2_실험결과.md`):

  §12  구름 tcdc·pwat 을 시잉 피처로 넣어도 무익 — F3 위에서 Δr=+0.001 (p=0.398)
  §11  격자 지표 2 m RH 는 기상탑 실측과 편향 +61.8%p (v12 격자면 764 m — 사이트
       2,635 m 보다 **1,871 m 낮다**. v11 격자면은 2,087 m 였고 v12 전환 때 더 낮아졌다).
       MOS 로 보정하면 MAE 55→7.5%p 로 좋아지지만, **정상 고도의 습도를 대리변수
       (층 기온차로 만든 역전 지표)로만 본다** — 진짜 변수가 없다.
  §13  그리고 층별 습도는 GEFS 에 **있다**. 우리가 요청하지 않은 것이다:
         pgrb2a  RH 10층 (700·850·925 포함)
         pgrb2b  RH 16층 + **SPFH 31층 = v2 수집 31층 전부**

## RH 가 아니라 SPFH 를 받는다

RH 는 `SPFH · 층기압 · 층기온` 으로 계산된다. **층 기온은 이미 다 갖고 있고 층 기압은
층 이름 자체**이므로 RH 는 파생 가능하다 — 반면 SPFH 는 RH 로부터 같은 정확도로 복원되지
않는다(포화수증기압 식과 얼음/물 기준 차이가 곱해진다). 그리고 비습은 **기단이 오르내려도
보존되는 양**이라 "그 공기가 얼마나 습한가"를 고도 차이와 무관하게 나타낸다 —
격자면이 1,871 m 낮은 이 문제에 정확히 맞는 변수다.

  · SPFH 31층 = pgrb2b **한 파일**에서 단위당 5.87 MB
  · RH 26층   = pgrb2a+pgrb2b **두 파일**에서 4.82 MB, 층도 5개 모자란다
  → SPFH 만 받는다. RH 가 필요하면 Magnus 로 만든다 (`spfh_to_rh()` 아래).

⚠ 이렇게 만든 RH 는 NCEP 이 파일에 담은 RH 와 **소수점 수준에서 다르다**
  (NCEP 은 얼음 기준 포화를 섞어 쓴다). MOS 입력으로는 무해하지만,
  "GEFS RH 값"으로 인용하면 안 된다.

## 층별 운량도 같이 받는다 (사용자 지시 2026-08-04)

*"구름도 상중하 운들도 좀 나눠서 보면 좋을듯, 상층운은 넓고 지속적인 구름이니"* — 맞다.
그리고 **같은 파일(pgrb2b)에 있어서 추가 비용이 거의 없다**:

| 항목 | MB/단위 | SPFH 대비 |
|---|---:|---:|
| SPFH 31층 | 5.87 | — |
| TCDC 저·중·고 | 0.39 | +7% |
| **+ 경계층운** | **0.53** | **+9%** |

천문에서 층이 갈리는 이유는 **차단 방식이 다르기 때문**이다:

  고층운(권운)   얇고 넓고 지속적 → 투과율만 깎는다. 관측은 되지만 **측광 불가**
  중층운         부분 차단
  저층운(층운)   완전 차단
  경계층운       파라날의 주 위협 — 태평양 해양층. 단 **역전층 아래에 갇히면 정상은 맑다**

★ 우리 격자는 **격자면이 764 m** 다 (사이트 2,635 m). 그래서 격자의 '저층운'은
  **정상보다 아래**일 수 있다 — 발밑 구름은 관측에 무해하다. 지금 쓰는 전 대기 TCDC
  하나로는 「발밑 해양층」과 「머리 위 권운」을 **구분할 수 없다**. 층을 나눠야 갈린다.

**전 대기 운량도 같은 0.5° 격자로 함께 받는다** — 기존 `tcdc` 는 atmos.25(0.25°)라
격자점이 다르고, 실제로 안 맞았다 (2023-08-07 00Z: 전 대기 13% 인데 층별이 전부 0%).
층별 값을 검증할 기준선이 있어야 한다. `cld.tot05` 로 저장한다 (+0.16 MB).

⚠ **운량은 순간값이 아니라 6시간 평균**이다 (GRIB 라벨 `18-24 hour ave fcst`).
  지금 쓰는 전 대기 TCDC 도 마찬가지다 — 화면에 "그 시각 구름"처럼 쓰면 안 된다.
  대류운(convective)은 받지 않는다: 초건조 사막 고지대라 사실상 0 이다 (VARIABLES.md).

## 작업 목록을 v2 에서 만든다

리드·사이클을 여기서 새로 정하지 않는다. **v2 가 실제로 받아 둔 (cycle, lead) 를 읽어서**
그 중 야간 유효시각인 것만 돌린다. 그래야 조인이 100% 맞는다 — 우리가 쓰는 표본은
`_data_v2.rows()` 가 고르는 그 표본이고, 거기 없는 (cycle,lead) 에 습도를 받아도 못 쓴다.

## 비용 (2026-08-04 실측 .idx 바이트)

| 층 범위 | 층수 | MB/단위 | 야간표본 5멤버 | m0 만 |
|---|---:|---:|---:|---:|
| 500~1000 hPa (하부) | 13 | 2.63 | 674 GB | 135 GB |
| 250~1000 hPa | 18 | 3.58 | 918 GB | 184 GB |
| **31층 전부** | 31 | 5.87 | **1,504 GB** | 301 GB |

야간 표본 = 파라날 야간 유효시각(00·03·06·09Z) 단위 262,397개(5멤버) / 52,486개(m0).
정상 2,635 m ≈ 730 hPa · 500 hPa ≈ 5,600 m — 그 위 수증기는 지상 습도에 거의 무관하고
권운·투과율은 PWAT 로 이미 받는다. 그래도 **기본값은 31층 전부**다 (사용자 지시
2026-08-04: "왜 고도별로 습도를 안받았데 다 받아야지"). 줄이려면 `--levels` 로.

저장: `data/v2y/{YYYY-MM}_m{M}.jsonl.gz` — v2·v2x 와 같은 구조.
      조인 키 `(cycle, lead, member, site)`.
재개: 이 멤버의 v2y gz 들에 `(cycle,lead)` 키가 있으면 스킵 (v2x 와 동일).
      ⚠ 그래서 **층 목록을 중간에 바꾸면 안 된다** — 이미 받은 단위는 새 층을 영영 안 받는다
      (v2 에서 실제로 당한 함정. VARIABLES.md 참조). 층을 늘리려면 또 다른 패스로.
push: `worker_v2.commit_push` 재사용.

    python -X utf8 worker_v2y.py --member 0 --start 2021-01-01 --end 2021-12-31
    python -X utf8 worker_v2y.py --member 0 --start 2021-01-01 --end 2021-12-31 --levels 500-1000
    python -X utf8 worker_v2y.py --member 0 --start 2021-01-01 --end 2021-01-07 --dry-run
"""
import argparse, datetime as dt, glob, gzip, json, os, time
import numpy as np
from worker_v2 import SITES, LEVELS, commit_push, purge_cache, rd

REPO = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(REPO, "data", "v2y")
V2DATA = os.path.join(REPO, "data", "v2")
# 야간 유효시각 — 사이트마다 다르므로 **합집합**을 쓴다 (한 번 내려받으면 4사이트를 다 뽑는다).
# 파라날/CTIO 는 00·03·06·09Z, SAAO 는 18·21·00·03Z, SSO 는 09·12·15·18Z 부근.
NIGHT_HOURS_UNION = (0, 3, 6, 9, 12, 15, 18, 21)

# 층별 운량 — (GRIB 층 이름, 저장 키, 한글). 전부 pgrb2b, SPFH 와 같은 파일이다.
# 대류운은 뺀다 (파라날에서 사실상 0). 475 mb 단일층도 뺀다 (층 두께 정보가 아니다).
CLOUD_LAYERS = [("low cloud layer", "low", "저층운"),
                ("middle cloud layer", "mid", "중층운"),
                ("high cloud layer", "high", "고층운"),
                ("boundary layer cloud layer", "bl", "경계층운")]


def parse_levels(spec):
    """`--levels` 해석. 'all' | '500-1000' | '700,750,850' — v2 의 31층 안에서만 고른다."""
    if not spec or spec == "all":
        return list(LEVELS)
    if "-" in spec and "," not in spec:
        lo, hi = (int(x) for x in spec.split("-"))
        return [L for L in LEVELS if lo <= L <= hi]
    want = {int(x) for x in spec.split(",")}
    bad = want - set(LEVELS)
    if bad:
        raise SystemExit(f"v2 수집 31층에 없는 층: {sorted(bad)} (있는 층: {LEVELS})")
    return [L for L in LEVELS if L in want]


def spfh_to_rh(q_kg_kg, t_k, p_hpa):
    """비습 → 상대습도 (%). Magnus (Alduchov & Eskridge 1996) 물 기준.

    ⚠ NCEP 파일의 RH 와 소수점 수준에서 다르다 (얼음 기준 혼용). 파생값임을 밝히고 쓸 것.
    """
    q = np.asarray(q_kg_kg, float)
    tc = np.asarray(t_k, float) - 273.15
    p = np.asarray(p_hpa, float)
    e = q * p / (0.622 + 0.378 * q)
    es = 6.1094 * np.exp(17.625 * tc / (tc + 243.04))
    return 100.0 * e / np.maximum(es, 1e-9)


def worklist(member, start, end, hours=NIGHT_HOURS_UNION, leads=None):
    """v2 가 받아 둔 (cycle, lead) 중 유효시각이 밤인 것. **여기서 새로 만들지 않는다.**

    반환: [(cycle_str, lead_int, valid_str), ...] 사이클 순.
    """
    d0, d1 = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    seen, out = set(), []
    pat = os.path.join(V2DATA, f"*_m{member}.jsonl.gz")
    for fn in sorted(glob.glob(pat)):
        ym = os.path.basename(fn)[:7]
        try:
            fy, fm = int(ym[:4]), int(ym[5:7])
        except ValueError:
            continue
        # 월 파일 이름은 **사이클** 기준이다 (수집기 저장 규약) → 범위 밖 달은 건너뛴다
        if dt.date(fy, fm, 1) > d1 or (fy, fm) < (d0.year, d0.month):
            continue
        with gzip.open(fn, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("site") != "paranal":       # 단위는 사이트와 무관 — 중복 제거용
                    continue
                cyc = r["cycle"]
                cd = dt.date.fromisoformat(cyc[:10])
                if not (d0 <= cd <= d1):
                    continue
                lead = int(r["lead"])
                if leads and lead not in leads:
                    continue
                v = dt.datetime.fromisoformat(str(r["valid"]).replace("Z", "+00:00").replace("+00:00", ""))
                if v.hour not in hours:
                    continue
                key = (cyc, lead)
                if key in seen:
                    continue
                seen.add(key)
                out.append((cyc, lead, f"{v:%Y-%m-%d %H:%M}"))
    out.sort()
    return out


def fetch_unit(cycle, fxx, member, levels, retry=3, clouds=True):
    """1단위 = 4사이트 × (SPFH 지정 층 + 층별 운량). pgrb2b 한 파일에서 바이트 범위로만.

    반환: {"q": {사이트: [층별 비습]}, "cld": {사이트: {키: %}}} — 운량을 빼면 cld 는 빈 dict.
    """
    from herbie import Herbie
    for k in range(retry + 1):
        try:
            H = Herbie(cycle, model="gefs", member=member, fxx=fxx,
                       product="atmos.5b", verbose=False)
            ds = H.xarray(r":SPFH:\d+ mb", remove_grib=True)
            if isinstance(ds, list):
                ds = ds[0]
            name = "q" if "q" in ds.data_vars else list(ds.data_vars)[0]
            lv = [int(x) for x in np.atleast_1d(ds[name].isobaricInhPa.values)]
            acc = {}
            for s, (la, lo) in SITES.items():
                p = ds.sel(latitude=la, longitude=lo, method="nearest")
                vv = np.atleast_1d(p[name].values).ravel()
                # 비습은 1e-5 수준이라 소수 2자리 반올림(rd)으로는 전부 0 이 된다 → 유효숫자로
                acc[s] = [(None if L not in lv else float(f"{float(vv[lv.index(L)]):.6g}"))
                          for L in levels]
            cld = {s: {} for s in SITES}
            if clouds:
                # 같은 0.5° 격자의 **전 대기** 운량도 받는다 (pgrb2a). 이게 없으면 층별 값을
                # 검증할 기준이 없다 — 기존 tcdc 는 atmos.25(0.25°)라 **격자점이 다르고**
                # 실제로 안 맞았다 (전 대기 13% 인데 층별이 전부 0%). +0.16 MB.
                try:
                    Ha = Herbie(cycle, model="gefs", member=member, fxx=fxx,
                                product="atmos.5", verbose=False)
                    dt_ = Ha.xarray(":TCDC:entire atmosphere:", remove_grib=True)
                    if isinstance(dt_, list):
                        dt_ = dt_[0]
                    tn = list(dt_.data_vars)[0]
                    for s, (la, lo) in SITES.items():
                        pt = dt_.sel(latitude=la, longitude=lo, method="nearest")
                        cld[s]["tot05"] = rd(float(np.atleast_1d(pt[tn].values).ravel()[0]))
                except Exception:
                    for s in SITES:
                        cld[s]["tot05"] = None
                # 층마다 **개별 search** — 한 번에 뽑으면 어느 층인지 구분이 뭉개진다
                for grib_lev, key, _ko in CLOUD_LAYERS:
                    try:
                        dc = H.xarray(f":TCDC:{grib_lev}:", remove_grib=True)
                        if isinstance(dc, list):
                            dc = dc[0]
                        cn = list(dc.data_vars)[0]
                        for s, (la, lo) in SITES.items():
                            pc = dc.sel(latitude=la, longitude=lo, method="nearest")
                            cld[s][key] = rd(float(np.atleast_1d(pc[cn].values).ravel()[0]))
                    except Exception:
                        for s in SITES:
                            cld[s][key] = None      # 그 사이클에 없는 층 — None 으로 남긴다
            return dict(q=acc, cld=cld)
        except Exception as e:
            m = str(e)
            if "Slow Down" in m or "503" in m or "429" in m:
                time.sleep(10 * (k + 1)); continue
            if k >= retry:
                return None
            time.sleep(4)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--member", type=int, required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--levels", default="all",
                    help="all | 500-1000 | 700,750,850 (v2 의 31층 안에서)")
    ap.add_argument("--leads", default="",
                    help="쉼표로 fxx 지정 (기본: v2 에 있는 야간 단위 전부)")
    # ⚠ 비용을 두 배로 가르는 축이다. 우리가 검증·스케줄링하는 사이트는 파라날뿐이므로
    #   기본은 파라날 야간(00·03·06·09Z). `--hours all` 은 4사이트 밤을 다 덮지만 2배다.
    ap.add_argument("--hours", default="0,3,6,9",
                    help="유효시각 UT (기본 0,3,6,9 = 파라날 밤 · all = 4사이트 합집합 8시각)")
    ap.add_argument("--budget-min", type=float, default=300)
    ap.add_argument("--commit-every-min", type=float, default=22)
    ap.add_argument("--seg", default="y0")
    ap.add_argument("--stagger", type=int, default=0)
    ap.add_argument("--no-clouds", action="store_true",
                    help="층별 운량(저·중·고·경계층)을 받지 않는다 (기본은 받는다 — +0.53 MB/단위)")
    ap.add_argument("--dry-run", action="store_true", help="작업 목록·견적만 내고 끝")
    a = ap.parse_args()
    M = a.member
    a.commit_every_min += a.stagger
    levels = parse_levels(a.levels)
    leads = {int(x) for x in a.leads.split(",")} if a.leads else None
    os.makedirs(DATA, exist_ok=True)

    hours = (NIGHT_HOURS_UNION if a.hours == "all"
             else tuple(int(x) for x in a.hours.split(",")))
    todo = worklist(M, a.start, a.end, hours=hours, leads=leads)
    # 층당 대략 바이트 (2026-08-04 실측: 31층 5.87 MB → 층당 0.189 MB)
    mb_unit = 0.189 * len(levels) + (0.0 if a.no_clouds else 0.53 + 0.16)
    print(f"v2y m{M}/{a.seg}: 습도 {len(levels)}층 {levels}", flush=True)
    print("  운량: " + ("받지 않음" if a.no_clouds else
                       " · ".join(ko for _g, _k, ko in CLOUD_LAYERS)
                       + " + 전대기(0.5°)  (6시간 평균 — 순간값이 아니다)"), flush=True)
    print(f"  유효시각 {hours} UT" + ("  (4사이트 합집합)" if a.hours == "all"
                                     else "  (파라날 밤 — 다른 사이트를 쓸 거면 --hours all)"),
          flush=True)
    print(f"  작업 목록 {len(todo):,} 단위 (v2 야간 단위에서) · 단위당 약 {mb_unit:.2f} MB "
          f"→ 총 약 {len(todo)*mb_unit/1024:.0f} GB", flush=True)
    if a.dry_run:
        for c, f, v in todo[:8]:
            print(f"    {c}  f{f:03d} → valid {v}")
        if len(todo) > 8:
            print(f"    … {len(todo)-8:,} 개 더")
        return

    done = set()
    for fn in glob.glob(os.path.join(DATA, f"*_m{M}.jsonl.gz")):
        try:
            with gzip.open(fn, "rt", encoding="utf-8") as f:
                for line in f:
                    try:
                        r = json.loads(line)
                        if r["site"] == "paranal":
                            done.add((r["cycle"], int(r["lead"])))
                    except Exception:
                        pass
        except Exception:
            pass
    fails_path = os.path.join(DATA, f"fails_m{M}_{a.seg}.json")
    fails = json.load(open(fails_path, encoding="utf-8")) if os.path.exists(fails_path) else {}
    print(f"  기수집 {len(done):,} 단위 · 실패기록 {len(fails)}", flush=True)

    t0 = last = time.time(); ok = skip = fail = 0
    for cyc, fxx, valid in todo:
        if (time.time() - t0) / 60 > a.budget_min:
            print("예산 소진 — 세션 종료", flush=True); break
        fkey = f"{cyc}|{fxx}"
        if (cyc, fxx) in done or fails.get(fkey, 0) >= 3:
            skip += 1; continue
        got = fetch_unit(cyc, fxx, M, levels, clouds=(not a.no_clouds))
        if got is None:
            fails[fkey] = fails.get(fkey, 0) + 1; fail += 1
            print(f"FAIL {cyc} f{fxx:03d} ({fails[fkey]}회)", flush=True)
        else:
            outp = os.path.join(DATA, f"{cyc[:7]}_m{M}.jsonl.gz")
            with gzip.open(outp, "at", encoding="utf-8") as fo:
                for s in SITES:
                    row = {"site": s, "cycle": cyc, "valid": valid, "member": M,
                           "lead": fxx, "q_lv": levels, "q": got["q"][s]}
                    if got["cld"].get(s):
                        # 운량은 **6시간 평균**이다 (GRIB `18-24 hour ave fcst`) — 순간값이 아니다
                        row["cld"] = got["cld"][s]
                        row["cld_note"] = "6h-ave"
                    fo.write(json.dumps(row, ensure_ascii=False) + "\n")
            done.add((cyc, fxx)); ok += 1
            if ok % 50 == 0:
                print(f"진행 m{M}: {cyc} f{fxx:03d} · ok {ok} · "
                      f"{(time.time()-t0)/60:.0f}분 · 약 {ok*mb_unit/1024:.1f} GB", flush=True)
        if (time.time() - last) / 60 > a.commit_every_min:
            json.dump(fails, open(fails_path, "w", encoding="utf-8"))
            commit_push(f"v2y m{M}/{a.seg} @ {cyc} f{fxx:03d} (ok {ok})")
            last = time.time()
        purge_cache()
    json.dump(fails, open(fails_path, "w", encoding="utf-8"))
    commit_push(f"v2y m{M}/{a.seg} 세션종료 (ok {ok} skip {skip} fail {fail})")
    print(f"세션 종료 m{M}: ok {ok} · skip {skip} · fail {fail} · "
          f"{(time.time()-t0)/60:.0f}분 · 약 {ok*mb_unit/1024:.1f} GB")


if __name__ == "__main__":
    main()
