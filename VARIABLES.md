# GEFS 제공 변수 전수 목록 — 수집 스펙의 근거

> 2026-07-29 Herbie inventory 실측. v11은 cycle `2019-06-01 00Z`, v12는 `2023-06-01 00Z`, member 0, fxx 24.
> **이 파일이 "무엇을 받을 수 있는가"의 정본이다. 수집 스펙을 바꾸기 전에 여기부터 본다.**
> 재생성: `scratchpad/gefs_inventory.py` 방식 (`Herbie(...).inventory()` 로 variable×level 집계)

## 왜 이 파일이 생겼나

v2 수집 스펙(31층·4사이트·전리드)을 정할 때 **연직 층 수만 전수 조사하고 변수 축은 조사하지 않았다.**
그 결과 기압면에서 기온·u·v 셋만 받게 됐고, 습도·경계층고도·마찰속도·지오포텐셜고도가 통째로 빠졌다.
(교정 원문: *"오마이갓... 변수들 다 알아보고 넣으라고 했것만.."* — 2026-07-29)

## 현재 수집 중 (worker_v2.py)

| 산출물 | 변수 | 층 |
|---|---|---|
| atmos.5 | TMP, UGRD, VGRD | 10층 (`LEV_A`) |
| atmos.5 | UGRD/VGRD 10m, TMP 2m, RH 2m, PRES surface | 지표 |
| atmos.5b | TMP, UGRD, VGRD | 21층 (`LEV_B`) |
| atmos.25 (m0만) | TCDC, PWAT | 전층적분 |

→ 기압면 총 31층 × 3변수. **atmos.25는 v11에 없다**(Herbie가 product 미인식) — TCDC/PWAT이 2020-09부터인 이유.

## 제공되는데 안 받는 것 — 우선순위순

### A급 (지표층이 우리 시잉의 주 레버 → 직접 겨냥)

| 변수 | 산출물 | 층 | 의미 |
|---|---|---|---|
| **HPBL** | atmos.5b | surface | 경계층 높이. 우리 WRF 파일럿에서 야간 90~200 m로 측정된 그 층 |
| **FRICV** | atmos.5b | surface | 마찰속도 u* — 지표 난류 강도 그 자체 |
| **GUST** | atmos.5b | surface | 돌풍. 평균풍이 못 담는 난류 성분 |
| **VRATE** | atmos.5b | PBL | 환기율 (경계층 혼합 강도) |

### B급 (제대로 된 안정도 지수를 만들려면 필수)

| 변수 | 산출물 | 층 | 의미 |
|---|---|---|---|
| **HGT** | atmos.5 11층 / atmos.5b 15~20층 | 기압면 | 지오포텐셜 고도. **이게 있어야 층 두께를 알고 N²·리처드슨 수를 미터당으로 계산**한다. 현재 온도차(t700−t500)만 쓰는 이유가 이것의 부재 |
| **VVEL** | atmos.5b | 20~30층 | 연직속도 |
| **ABSV** | atmos.5b | 26층 | 절대와도 |

### C급 (습도 — 값어치는 있으나 비쌈)

| 변수 | 산출물 | 층 | 비고 |
|---|---|---|---|
| RH | atmos.5 10층 / atmos.5b 22층 | 기압면 | 층별 상대습도. 22층 추가 시 다운로드 +30%↑ |
| SPFH | atmos.5b | 32층(v11) / 37층(v12) | 비습 — 수증기량 자체로는 RH보다 나음 |
| DPT | atmos.5b | 2 m, 30-0 mb | 이슬점 |

### 받을 수 있으나 파라날에선 값어치 낮다고 판단

| 변수 | 판단 근거 |
|---|---|
| CAPE / CIN / LFTX / 4LFTX / PLI | 초건조 사막 고지대라 대류가 사실상 없음 → 거의 항상 0 부근, 분산이 없어 GBM이 쓸 게 없을 것. **미검증 판단** — 2차 패스 때 한 달치로 분산부터 확인하면 확정됨 |
| APCP / PRATE / CRAIN / CSNOW 등 강수 | 파라날 연강수량 극소 |
| SOILW / TSOIL / WEASD / ICEC | 지표 상태 — 시잉과 경로가 멀다 |
| O3MR / TOZNE / BRTMP / 복사 플럭스류 | 시잉과 직접 관계 희박 |

## 2차 패스 스펙 (백필 완주 후 별도 레인)

**확정 추가**: HPBL, FRICV, GUST, HGT (+VRATE)
— 전부 지표이거나 층 수가 적어 비용 대략 +5~10%.

**보류**: RH 22층 — 비용 +30%↑. 먼저 지금 데이터로 PWAT·2m 습도가 MOS에 실제로 기여하는지 보고 결정.
(사용자 판단 대기, 2026-07-29)

**지금 스펙을 바꾸지 않는 이유**: 백필 진행 중(54%)에 변수를 추가하면 이미 받은 구간과 스키마가
어긋나 재개 로직(`(cycle,lead)` 키 스킵)이 새 변수를 영영 안 받는다. 완주 후 2차 패스가 안전하다.

## 전체 목록 (실측 원본)

- **atmos.5** (30종, v11·v12 동일): APCP, CAPE, CFRZR, CICEP, CIN, CRAIN, CSNOW, DLWRF, DSWRF,
  HGT(11층), ICETK, LHTFL, PRES, PRMSL, PWAT, RH(10층), SHTFL, SNOD, SOILW, TCDC, TMAX, TMIN,
  TMP(10층), TSOIL, UGRD(12층), ULWRF, USWRF, VGRD(12층), VVEL(850mb), WEASD
- **atmos.5b** (v11 68종 / v12 71종): 4LFTX, 5WAVH, ABSV(26층), ACPCP, ALBDO, APTMP(v12),
  BRTMP, CAPE, CDUVB, CIN, CLMR/CLWMR(26층), CNWAT, CPOFP, CPRAT, CWAT, CWORK, DPT, DUVB, FLDCP,
  FRICV, GFLUX, GUST, HGT(15~20층), HINDEX, HLCY, HPBL, ICAHT, ICEC, ICIP, ICSEV, LAND, LFTX,
  MNTSF, MSLET, NCPCP, O3MR(18층), PEVPR, PLI, PLPL, POT, PRATE, PRES, PVORT, PWAT, RH(22층),
  SFCR, SNOHF(v12), SNOWC(v12), SOILL, SOILW, SPFH(32~37층), SUNSD, TCDC, TMP(22~27층), TOZNE,
  TSOIL, U-GWD, UFLX, UGRD(20~25층), USTM, USWRF, V-GWD, VFLX, VGRD(20~25층), VIS, VRATE,
  VSTM, VVEL(20~30층), VWSH, WATR, WILT
- **atmos.25** (v12만, 35종): 지표 위주 — CAPE, CIN, DPT2m, GUST, HLCY, PWAT, RH2m, TCDC,
  TMP2m, UGRD10m, VGRD10m, VIS, HGT(cloud ceiling) 등
