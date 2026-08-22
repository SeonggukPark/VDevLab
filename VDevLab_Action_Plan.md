# VDevLab 실행 액션 플랜

> 마지막 갱신: 2026-08-22
> 출품 마감: 2026-08-27
> 현재 단계: Phase 10/10 Release 준비 — `v0.1.0-rc1` 후보 commit 동결 완료
> 현재 브랜치: `codex/record-rc1-tag`
> 다음 실행: RC 기준 3분 시연 영상 촬영과 영상 명령·README 일치 확인

## 체크 규칙

- `[x]`는 코드 작성만이 아니라 해당 완료 조건까지 검증된 경우에만 표시한다.
- Linux kernel 작업은 Ubuntu VM의 빌드·실행·kernel log 확인 후 완료 처리한다.
- 기능을 완료할 때 관련 테스트, 문서, Issue/PR 상태도 같은 작업에서 갱신한다.
- 각 Phase의 Gate를 통과하기 전에는 다음 Phase를 주 작업으로 진행하지 않는다.
- 일정이 지연되면 P1부터 제거하며 문서·라이선스·관리 증거는 삭제하지 않는다.

## 평가 기준 대응

| 평가항목 | 저장소에 남길 핵심 증거 |
|---|---|
| 구조 및 코드 완성도 | 모듈 구조, 테스트, CI, end-to-end 데모, 오류 처리 |
| 오픈소스 발전 가능성 | License, CONTRIBUTING, ROADMAP, versioned schema, 기여 이슈 |
| 개발 문서 구체성 | 검증된 Quick Start, architecture, fault/scenario reference, ADR |
| 프로젝트 혁신성 | 실제 kernel I/O fault, retry contract, recovery latency, causal timeline |
| 프로젝트 관리 | Issue → branch → PR → CI → self-review → merge → release 기록 |

---

## Phase 0 — 현재 구현 기준선

- [x] Character Device와 `/dev/vdevlab0` 등록 코드
- [x] `kfifo` 기반 read/write 코드
- [x] blocking/non-blocking I/O 코드
- [x] wait queue와 기본 `poll()` 코드
- [x] ioctl fault set/get/clear UAPI
- [x] fault control utility 기본 명령
- [x] 공개 GitHub 저장소
- [x] GitHub 작업 이슈 #1~#5

## Phase 1 — Deterministic Kernel Fault Contract

### 소스 구현

- [x] Issue #1용 로컬 기능 브랜치 생성
- [x] fault UAPI에 `repeat` 추가
- [x] `set eio <count>` 제어 명령 추가
- [x] EIO 횟수의 lock 기반 차감과 자동 정상화 구현
- [x] EIO·delay를 consumer read 경로로 제한
- [x] injection write가 EIO count를 소비하지 않도록 분리
- [x] blocked read의 EIO/disconnect wake 조건 구현
- [x] `poll()`의 EIO `POLLERR` 반환 구현
- [x] disconnect의 `POLLERR | POLLHUP` 유지
- [x] invalid fault config가 기존 상태를 변경하지 않도록 검증 순서 구현
- [x] fault semantics 설계 문서 작성
- [x] PR self-review 템플릿 작성
- [x] Linux 소스와 스크립트의 LF 규칙 추가

### 자동 검증 환경

- [x] root 통합 Makefile
- [x] tools Makefile
- [x] contract tests Makefile
- [x] counted EIO 정확성 테스트 코드
- [x] injection write 비소비 테스트 코드
- [x] EIO 후 정상 payload 복구 테스트 코드
- [x] invalid config 상태 보존 테스트 코드
- [x] blocked read wake-up 테스트 코드
- [x] blocked poll wake-up 테스트 코드
- [x] module cleanup·kernel log 검사 스크립트
- [x] GitHub Actions Ubuntu kernel/userspace compile workflow 작성
- [x] kernel·userspace build artifact `.gitignore` 작성
- [x] 로컬 shell syntax 검사
- [x] Make 명령 구성 dry-run
- [x] `git diff --check`

### Ubuntu VM Gate

- [x] 실행 중인 VMware Ubuntu와 SSH 포트 확인
- [x] Ubuntu VM snapshot 또는 깨끗한 검증 환경 준비
- [x] `make contract-test`로 kernel module 빌드
- [x] control utility와 contract test 빌드
- [x] expected EIO 3회와 observed EIO 3회 일치
- [x] injection write의 EIO count 소비 0회
- [x] 네 번째 read에서 queued payload 정상 수신
- [x] blocked read가 EIO로 즉시 wake-up
- [x] blocked poll이 `POLLERR`로 즉시 wake-up
- [x] invalid repeat 0이 `EINVAL`로 거부됨
- [x] module unload 후 `/dev/vdevlab0` 제거
- [x] kernel warning/oops/lockdep 0건
- [x] 실제 테스트 로그 저장

### GitHub Gate

- [x] 관련 Issue에 설계와 완료 조건 갱신
- [x] 검증 가능한 단위로 commit
- [x] 원격 branch push
- [x] Issue #1과 연결된 Draft PR 생성
- [x] PR에 Ubuntu 환경과 테스트 로그 첨부
- [x] PR self-review checklist 완료
- [x] CI 또는 수동 Gate 결과 확인
- [x] PR merge 및 Issue 상태 갱신

---

## Phase 2 — Kernel Fault 기능 완성

- [x] delay가 read당 한 번만 적용되는지 검증
- [x] monotonic clock으로 실제 delay 측정
- [x] delay 허용 오차 기준 확정
- [x] partial-read UAPI 추가
- [x] partial-read 반환 크기와 경계 처리
- [x] disconnect 중 read/write의 `ENODEV` 검증
- [x] disconnect 중 blocked read/write wake-up 검증
- [x] reconnect 동작 정의와 구현
- [x] fault 상태와 FIFO를 함께 초기화하는 full reset
- [x] 지원하지 않는 ioctl의 `ENOTTY` 검증
- [x] fault config 범위 오류의 `EINVAL` 검증
- [x] module load/unload 20회 반복
- [x] kernel warning/oops/lockdep 0건
- [x] fault model 문서와 실제 동작 일치 확인
- [x] Kernel fault 완성 PR merge

### Phase 2 Gate

- [x] EIO·delay·partial read·disconnect가 독립적으로 설정·조회·해제됨
- [x] 두 번 연속 테스트에서 fault/FIFO 상태가 누적되지 않음

---

## Phase 3 — Sample Application과 Kernel Smoke Test

- [x] `examples/vtemp_monitor.c` 구현
- [x] `/dev/vdevlab0` open 및 `poll()` 대기
- [x] 정상 온도 구조화 로그
- [x] 80도 이상 `THERMAL_WARNING`
- [x] EIO 최대 3회 retry
- [x] 정상화 시 `RECOVERY_SUCCESS`
- [x] disconnect 시 `DEVICE_DISCONNECTED`
- [x] 모든 앱 로그에 monotonic timestamp 포함
- [x] normal/non-blocking/poll/fault smoke test
- [x] smoke test 10회 연속 실행
- [x] sample application·smoke test PR merge

### Phase 3 Gate

- [x] EIO 3회 → retry 3회 → 정상 복구 로그가 실제 kernel device에서 생성됨

---

## Phase 4 — YAML Schema와 Parser

- [x] `pyproject.toml`과 `vdevlab` CLI entry point
- [x] `schema_version` 필드 정의
- [x] `ms`, `s` duration parser
- [x] device/application/scenario/assertions 필수 필드 검증
- [x] 이벤트별 허용 필드와 자료형 검증
- [x] fault별 인자 범위 검증
- [x] 시간 역전과 빈 scenario 거부
- [x] 오류 위치를 포함한 `ScenarioError`
- [x] 정상·오류 parser 단위 테스트
- [x] `docs/scenario-format.md`
- [x] Parser PR merge

### Phase 4 Gate

- [x] 잘못된 YAML이 실행 전에 정확한 필드 위치와 원인으로 거부됨

---

## Phase 5 — Scenario Runner

- [x] `time.monotonic()` 기반 scheduler
- [x] ioctl device backend
- [x] 정상 데이터 injection write
- [x] EIO/delay/partial/disconnect/reconnect dispatch
- [x] application process group 실행
- [x] stdout/stderr 동시 캡처
- [x] process exit code 수집
- [x] 전체 timeout
- [x] Ctrl+C cleanup
- [x] dispatch failure cleanup
- [x] timeout process 종료와 강제 종료 fallback
- [x] 모든 종료 경로에서 fault clear/reset
- [x] scheduler와 fake backend 단위 테스트
- [x] Runner PR merge

### Phase 5 Gate

- [x] 실제 `normal.yaml`이 runner를 통해 처음부터 끝까지 실행됨

---

## Phase 6 — Recovery Assertion과 Causal JSON Report

- [x] observed EIO 횟수 계산
- [x] application retry 횟수 계산
- [x] fault injection timestamp 기록
- [x] first error timestamp 기록
- [x] recovery timestamp와 latency 계산
- [x] retry count assertion
- [x] recovery latency assertion
- [x] stdout contains/not-contains assertion
- [x] process exit-code assertion
- [x] disconnect assertion
- [x] kernel warning assertion
- [x] PASS·FAIL·ERROR·TIMEOUT 모두 JSON 생성
- [x] JSON `schema_version` 추가
- [x] report serialization 단위 테스트
- [x] 의도적 PASS report 예제 저장
- [x] 의도적 FAIL report 예제 저장
- [x] Assertion/report PR merge

### Phase 6 Gate

- [x] fault → errno → retry → recovery의 인과 타임라인이 JSON 하나에 기록됨

---

## Phase 7 — End-to-End Demo와 CI

- [x] `examples/scenarios/normal.yaml`
- [x] `examples/scenarios/recovery.yaml`
- [x] `examples/scenarios/disconnect.yaml`
- [x] `scripts/setup.sh`
- [x] `scripts/load.sh`
- [x] `scripts/unload.sh`
- [x] `scripts/demo.sh`
- [x] demo 실패 경로 cleanup trap
- [x] GitHub Actions kernel/userspace compile 통과
- [x] GitHub Actions 사용자 공간 단위 테스트 통과
- [x] CI badge
- [x] `sudo ./scripts/demo.sh` 5회 연속 실행
- [x] 종료 후 test process 0
- [x] 종료 후 fault state 0
- [x] 종료 후 device node 0
- [x] Demo/CI PR merge

### Phase 7 Gate

- [x] 한 명령으로 build → fault injection → assertion → report → cleanup 완료

---

## Phase 8 — 오픈소스 발전 가능성과 관리 증거

- [x] root `LICENSE`
- [x] kernel과 사용자 공간 license 범위 명시
- [x] 모든 소스 SPDX 확인
- [x] `CONTRIBUTING.md`
- [x] `ROADMAP.md`
- [x] `CHANGELOG.md`
- [x] `THIRD_PARTY_NOTICES.md`
- [x] `DEPENDENCIES.md`
- [x] Issue template
- [x] bug/feature PR template 구체화
- [x] labels: `bug`, `enhancement`, `kernel`, `cli`, `docs`
- [x] `good first issue` 최소 1개
- [x] `help wanted` 후보 최소 1개
- [x] scenario/report versioning 정책
- [x] 외부 contributor용 사용자 공간 test 절차
- [x] GitHub Milestone과 Issue #1~#5 상태 갱신
- [x] Public 저장소 비로그인 clone 확인

### Phase 8 Gate

- [x] 새로운 기여자가 README와 CONTRIBUTING만으로 test와 PR 준비 가능

---

## Phase 9 — 개발 문서와 혁신성 설명

- [x] README 30초 소개
- [x] README 3분 Quick Start
- [x] README demo output과 JSON 예제
- [x] `docs/architecture.md`
- [x] `docs/alternatives.md`
- [x] ADR: kernel module 선택 이유
- [x] ADR: data fault를 read에만 적용한 이유
- [x] 지원 Ubuntu/kernel 범위
- [x] 알려진 제한사항
- [x] QEMU 비교
- [x] Renode 비교
- [x] umockdev 비교
- [x] CUSE 비교
- [x] Linux fault injection 비교
- [x] VDevLab이 적합하지 않은 사용 사례 명시
- [x] 모든 README 명령 실제 재검증

### Phase 9 Gate

- [x] 제3자가 문서만 보고 10분 안에 demo를 시작할 수 있음

---

## Phase 10 — Release와 제출

- [x] 결과보고서 초안
- [x] 문제·대상 사용자·해결 방식 정리
- [x] 아키텍처 그림
- [x] 기존 도구 비교표
- [x] 정량 테스트 결과
- [x] clean Ubuntu VM clone
- [x] README 절차로 build/demo/cleanup
- [x] `v0.1.0-rc1` tag
- [ ] RC 기준 3분 시연 영상 촬영
- [ ] 영상 명령과 README 일치 확인
- [ ] 치명적 결함만 수정
- [ ] 최종 `v0.1.0` tag
- [ ] GitHub Release
- [ ] 전체 소스 압축본
- [ ] 제출 commit hash 기록
- [ ] 결과보고서·소스 checksum 기록
- [ ] 저장소·영상 공개 범위 확인
- [ ] 제출 폼 URL과 commit 대조
- [ ] 접수 완료 화면과 접수 번호 보관
- [ ] 제출 파일 별도 백업

### Final Gate

- [ ] 결과보고서·3분 영상·전체 소스코드를 2026-08-27까지 제출

---

## P1 — 제출 이후 또는 여유 시간

- [ ] delay 전용 시나리오
- [ ] partial-read 전용 시나리오
- [ ] JUnit XML
- [ ] 100회 반복 안정성 테스트
- [ ] backend extension interface
- [ ] umockdev backend 검토
- [ ] i2c-stub 연동 검토
- [ ] 성능·latency 통계 확장

## 일정 지연 시 축소 순서

1. partial-read 전용 데모 제거
2. delay 전용 데모 제거
3. 별도 reconnect 명령을 clear alias로 단순화
4. stdout-not-contains 같은 부가 assertion 제거
5. CLI subcommand를 `run` 중심으로 축소

끝까지 유지:

- 실제 kernel read/poll path
- counted EIO
- retry count assertion
- recovery latency
- causal JSON timeline
- normal/recovery/disconnect demo
- README, License, CONTRIBUTING
- Issue/PR/CI/Release 기록

## 검증 기록

Gate를 통과할 때 아래 표에 실제 증거를 추가한다.

| 날짜 | Phase/Gate | 환경 | 결과 | Commit/PR/로그 |
|---|---|---|---|---|
| 2026-08-17 | 로컬 정적 검사 | Windows/PowerShell | shell syntax·Make dry-run·diff check 통과 | 로컬 브랜치, Ubuntu 실행 대기 |
| 2026-08-17 | Ubuntu VM 접근 확인 | VMware/Ubuntu | VM·SSH 포트 확인, 기존 인증 정보 없어 runtime 미실행 | SSH 인증 준비 필요, Gate 미완료 |
| 2026-08-18 | GitHub Gate | Ubuntu/GitHub Actions | kernel module·userspace compile 및 clean target 통과 | Issue #1, Draft PR #6, CI run 32042544936 |
| 2026-08-18 | Phase 2 소스 구현 | Windows·Ubuntu CI | partial read·reconnect·full reset 구현, delay 허용 기준 문서화 | Commit 80f913a, CI run 32088619189 통과, runtime 대기 |
| 2026-08-18 | Phase 3 소스 구현 | Windows·Ubuntu CI | poll monitor·구조화 로그·retry/recovery·smoke runner 구현 | Commit 04d400e, CI run 32091074911 통과, runtime 대기 |
| 2026-08-18 | Phase 4 Gate | Windows·Ubuntu CI | parser 테스트 36개·YAML 3종·CLI 검증 통과 | Commits 64652b7, 96460a9, CI run 32128583841 |
| 2026-08-18 | Phase 1~3 Ubuntu VM Gate | VMware Ubuntu 22.04, kernel 6.8.0-136-generic | parser 36개, kernel contract, module lifecycle 20회, smoke 10회 통과; 신규 kernel warning 0건; module·device·process cleanup 확인 | [PR #6 검증 기록](https://github.com/SeonggukPark/VDevLab/pull/6#issuecomment-5327820341), VM `logs/kernel-contract-20260818T114131Z.log`, `logs/vtemp-smoke-20260818T114357Z-{1..10}.jsonl` |
| 2026-08-18 | Phase 1~4 Merge Gate | GitHub | CI와 Ubuntu VM Gate 통과 후 기반 기능 병합, Issue #1에 다음 단계 기록 | PR #6, merge `a120ac2`, [Issue #1 갱신](https://github.com/SeonggukPark/VDevLab/issues/1#issuecomment-5327855287) |
| 2026-08-18 | Phase 5 scheduler/backend | Windows/Python 3 | absolute monotonic deadline, 지연 누적 방지, YAML 순서, fault dispatch, ioctl 구조체, 부분 write·EINTR·close 검증; 전체 54개 테스트 통과 | `issue-1/scenario-runner`, `python_tests/test_runner.py` |
| 2026-08-19 | Phase 5 application process | Windows/Python 3 | process group, stdout/stderr 병렬 drain, 대용량 출력, UTF-8 replacement, 종료 코드 수집 검증; 전체 62개 테스트 통과 | `issue-1/scenario-runner`, `python_tests/test_runner.py` |
| 2026-08-19 | Phase 5 timeout | Windows/Python 3 | timeout 감지, 정상 종료 유예, process group 강제 종료 fallback, TIMEOUT 결과 플래그 검증; 전체 68개 테스트 통과 | `issue-1/scenario-runner`, `python_tests/test_runner.py` |
| 2026-08-19 | Phase 5 cleanup | Windows/Python 3 | 정상·timeout·dispatch failure·Ctrl+C 경로의 process 종료와 device reset/close 검증; 전체 71개 테스트 통과 | `issue-1/scenario-runner`, `python_tests/test_runner.py` |
| 2026-08-19 | Phase 5 Ubuntu VM Gate | VMware Ubuntu 22.04, kernel 6.8.0-136-generic | `normal.yaml` end-to-end 실행, MONITOR_STARTED·온도 25/42, exit 0, timeout false, fault none, module·device·process cleanup 확인 | Commit `894649a`, [PR #7 runtime 기록](https://github.com/SeonggukPark/VDevLab/pull/7#issuecomment-5338375659) |
| 2026-08-19 | Phase 5 Merge Gate | GitHub | 76개 테스트, Ubuntu kernel end-to-end, CI 통과 후 Scenario Runner 병합 | PR #7, merge `ae1dd96`, CI run 32223452813 |
| 2026-08-19 | Phase 6 recovery analysis·timing | Windows·Ubuntu/Python 3 | JSONL event 검증, EIO·retry 횟수, 최초 오류·복구 시각과 latency, event count/within assertion 검증; 절대 monotonic dispatch 시각과 recovery latency 상한 추가; 양 환경 전체 106개 테스트 통과 | Commits `5fbe707`, `7a23e92`, `src/vdevlab/analysis.py` |
| 2026-08-19 | Phase 6 causal JSON report | Windows·Ubuntu/Python 3 | PASS·FAIL·ERROR·TIMEOUT 분류, schema v1, fault→error→recovery timeline, exit-code assertion, 안정적 JSON serialization과 CLI 파일 출력 검증; 양 환경 전체 118개 테스트 통과 | Commit `5826940`, `src/vdevlab/report.py` |
| 2026-08-19 | Phase 6 assertion 확장·report 예제 | Windows·Ubuntu/Python 3 | stdout 포함·제외, disconnect, kernel warning assertion 구현과 PASS/FAIL schema 예제 고정; 양 환경 전체 138개 테스트 통과, kernel runtime 대기 | Commits `9239259`, `5dfff58`, PR #8 |
| 2026-08-19 | Phase 7 setup·CI | Ubuntu VM·GitHub Actions | setup 한 번으로 venv 설치, 138개 테스트, YAML 3종 검증, kernel/userspace build 통과; 신규 스크립트 Bash 구문과 CI clean target 통과 | Commit `03b42e0`, CI run 32259081736, PR #8 |
| 2026-08-19 | Phase 6·7 runtime Gate | VMware Ubuntu 22.04, kernel 6.8.0-136-generic | 초기 TIMEOUT과 sub-ms 인과 순서 문제 발견·수정; demo 5회 연속, recovery/disconnect report 각 5개 PASS, kernel warning 0건, causal order 정상, fault·process·module·device cleanup 확인 | Commit `f290314`, VM `logs/demo-gate-20260819T135349Z-{1..5}.log`, PR #8 |
| 2026-08-19 | Phase 6·7 Merge Gate | GitHub | causal report, assertions, one-command demo, Ubuntu runtime 증거와 CI 통과 후 main 병합; Issue #1 완료 처리 | PR #8, merge `aa00587`, CI run 32260935437 |
| 2026-08-19 | Issue #2 clean clone setup | VMware Ubuntu 22.04 | 공개 HTTPS 비인증 clone 후 README setup 실행; 139개 테스트, YAML 3종, kernel/userspace build 통과, 생성물 ignore와 clean worktree 확인 | Commit `af63495`, PR #9, `/tmp/vdevlab-clean.gH6TYx` 임시 검증 후 제거 |
| 2026-08-20 | 제출 문서 준비 | Windows 11, Microsoft Word 2021 | 공식 양식 안내 페이지 제거, 본문 4쪽·SBOM·AI 활용 명세 작성, DOCX/PDF 7쪽 전부 렌더 검토, root GPL-2.0-only LICENSE 추가, Python 테스트 139개 통과 | `submission/` 준비본과 제출 체크리스트, 사용자 확인 항목은 명시적 placeholder 유지 |
| 2026-08-22 | Phase 8 기여 기반 정리 | Windows 11·Python 3 | CONTRIBUTING·ROADMAP·CHANGELOG·의존성·서드파티 고지·Issue/PR 양식 추가, source 27개 SPDX 확인, YAML parse·139개 테스트·시나리오 3종 검증·diff check 통과 | `issue-2/reproducible-environment` 미커밋 작업 트리; Ubuntu fresh clone은 공개 clone 성공 후 sudo 인증에서 중단 |
| 2026-08-22 | PR #9 clean-clone runtime Gate | VMware Ubuntu 22.04, kernel 6.8.0-136-generic | 공개 HTTPS clone에서 PR head `9156687` checkout 후 README demo 완료; recovery/disconnect schema v1 report 모두 PASS, 전체 assertion 통과, kernel warning 0건, module·device·monitor process cleanup과 clean worktree 확인 | PR #9, VM `/tmp/vdevlab-final.5ke6kK`, `reports/{recovery,disconnect}-20260821T184312Z.json`; 기본 main은 아직 `aa00587` |
| 2026-08-22 | PR #9 Phase 8 최종 Gate | VMware Ubuntu 22.04·GitHub Actions | 공개 branch clone `fae857a`에서 pinned dependency 설치, 139개 테스트·YAML 3종·kernel/userspace build와 전체 demo 통과; report assertion 15개 PASS, kernel warning 0건, module·device·process·worktree cleanup 확인; CI 통과 | PR #9, CI run 32515214256, VM `/tmp/vdevlab-phase8.TnDlqk`, `reports/{recovery,disconnect}-20260821T185754Z.json` |
| 2026-08-22 | Phase 8 Merge·Contributor Gate | GitHub·VMware Ubuntu 22.04 | PR #9 self-review·CI 후 squash merge, Issue #2 자동 종료; `v0.1.0` milestone과 필수 labels 생성, good-first/help-wanted 이슈 공개; public main `b97e03d` fresh clone setup에서 pinned install·139 tests·YAML 3종·전체 build·clean worktree 통과 | PR #9 merge `b97e03d`, CI runs 32515214256·32516157826, Issues #10·#11 |
| 2026-08-22 | Phase 9 설계 문서 | Windows 11·공식 upstream 문서·GitHub Actions | architecture·대안 비교·ADR 2개 작성, 지원 범위·제한·부적합 사례 명시; Markdown 상대 링크·139개 테스트·YAML 3종·diff check·CI 통과 후 merge | PR #12, merge `64962ca`, CI run 32570692152, `docs/architecture.md`, `docs/alternatives.md`, `docs/adr/` |
| 2026-08-22 | Phase 9 main fresh-clone Gate | VMware Ubuntu 22.04, kernel 6.8.0-138-generic | public main `64962ca` clone 후 pinned install·139개 테스트·YAML 3종·전체 build·개별 load/unload·전체 demo 통과; report assertion 15개 PASS, kernel warning 0건, module·device·process·worktree cleanup 확인 | VM `/tmp/vdevlab-rc-prep.Z7pyQb`, `reports/{recovery,disconnect}-20260822T114405Z.json` |
