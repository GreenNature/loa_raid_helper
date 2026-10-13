# 클라우드 개발 환경 시작

기존 체크아웃 `/workspace/loa_raid_helper`를 사용함. 클라우드 작업은 이미 격리된 환경이므로 사용자가 명시적으로 요청하지 않는 한 Git worktree를 만들지 않음. 프로젝트 코드는 해당 체크아웃에서 개발하며 기존 변경을 보존함. 코드를 임의로 초기화하거나 원격으로 덮어쓰지 않음.

Python 3.12 개발 환경은 `/workspace/.venvs/loa-raid-helper`에 설치되어 있음. 설치된 의존성과 파일은 환경 스냅샷 대상이지만 실행 중인 Qt 창·작업 스레드는 새 작업에 유지되지 않음. 별도 데이터베이스·백엔드 서비스·API 키는 필요하지 않음.

## 기본 검증

저장소 루트에서 다음 명령을 실행함.

```bash
cd /workspace/loa_raid_helper
export PIP_CACHE_DIR=/workspace/.cache/pip
export XDG_CACHE_HOME=/workspace/.cache
/workspace/.venvs/loa-raid-helper/bin/python -m pip check
QT_QPA_PLATFORM=offscreen /workspace/.venvs/loa-raid-helper/bin/python -m pytest -q
QT_QPA_PLATFORM=offscreen /workspace/.venvs/loa-raid-helper/bin/python -m loa_raid_helper --smoke-test
```

통합 검증은 CPU OCR로 합성 HP 180·175를 읽고, 기믹 안내 1회, 버프 인식, 대기실 클래스 인식, Qt 위젯 표시를 확인한 뒤 종료함. 현재 인스턴스에서 전체 테스트 107개와 통합 검증이 통과함. 음성 엔진이 없는 클라우드에서는 화면 안내가 유지되는 경로를 검증하며 한국어 실제 재생은 Windows에서 확인함.

의존성이 없거나 바뀌면 저장된 설치 스크립트 또는 `/workspace/loa-raid-helper-setup.sh`를 실행함. 이 스크립트는 고정된 `requirements-lock.txt` 설치, 로컬 패키지 등록, 의존성 검사와 통합 검증을 수행함. 앱 소스·설정·잠금 파일을 자동 변경하지 않음.

## UI·이미지 인식

그래픽 화면이 있는 환경에서는 다음 명령으로 데모를 시작함. 시작 후 실제 CPU OCR 작업 스레드가 대기실·레이드 합성 화면을 인식함.

```bash
/workspace/.venvs/loa-raid-helper/bin/python -m loa_raid_helper --demo
```

화면 서버가 없는 클라우드에서는 지속 실행하는 데모 대신 위의 `--smoke-test`를 사용함. localhost 미리보기 링크를 만들지 않음. 저장 이미지 분석은 `--analyze <이미지> --config <JSON>` 또는 `tools/evaluate.py`를 사용함. 새 프로필과 템플릿은 Git 제외 경로 `local/`에 보관하며 [보정 문서](calibration.md)를 따름.

실제 게임 리소스는 포함되어 있지 않음. `raid_anchor`와 `boss_anchor`를 포함한 프로필을 보정해야 기믹 안내가 활성화됨. 기본 설정으로 임의의 화면 숫자를 보스 HP로 안내하지 않음. 게임 화면 캡처, DPI·다중 모니터, 입력 통과, 한국어 음성, 실제 레이드 인식률은 [Windows 문서](windows.md)에 따라 별도로 검증함.

## 패키징

```bash
cd /workspace/loa_raid_helper
/workspace/.venvs/loa-raid-helper/bin/python -m PyInstaller --noconfirm loa_raid_helper.spec
QT_QPA_PLATFORM=offscreen ./dist/LoaRaidHelper/LoaRaidHelper --smoke-test
```

현재 Linux 빌드와 패키징된 실행 파일의 OCR·안내·UI 통합 검증을 확인함. 소스가 바뀌면 위 명령으로 다시 빌드함. Windows `.exe`는 Windows에서 빌드하며, Linux 결과로 Windows 배포 성공을 주장하지 않음. 저장된 환경 설정은 게시와 별개이며 새 작업에서의 스냅샷 복원은 아직 검증하지 않았음.
