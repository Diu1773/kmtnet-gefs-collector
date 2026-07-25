# gefs-collector

KMTNet 시잉 예보용 GEFS 앙상블 무인 수집기 (GitHub Actions).
NOAA GEFS 공공데이터(AWS Open Data)에서 Paranal 지점 예보 피처를 추출해 `data/gefs_ens.jsonl`에 누적.
관측 라벨은 여기 없음 — 본 레포는 공공 기상데이터 추출값만 저장.

## 저장 구조 (v2, 2026-07-25)
- `data/v2/{YYYY-MM}_m{M}.jsonl.gz` — 월별·멤버별 gzip (행=사이트별: paranal/ctio/saao/sso, 31층 t/u/v 배열 + 지표 + tcdc/pwat[컨트롤])
- `data/legacy_v1/` — 구스펙(3층·일단위·파라날) 보존분. 신규 분석은 v2만 사용 권장
- 백필 완료 후 1회 컴팩션(이력 스쿼시) 예정 — 클론 크기 관리
