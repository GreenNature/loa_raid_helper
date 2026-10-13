# 로스트아크 레이드 헬퍼

게임 화면의 HP 숫자와 아이콘을 읽어 기믹 안내, 버프 오버레이, 대기실 클래스별 시너지를 표시하는 Python 데스크톱 앱의 초기 구현임. 게임 프로세스의 메모리를 읽거나 입력을 자동화하지 않음.

현재 실제 게임 아이콘과 검증된 레이드 데이터는 포함하지 않음. 기본 프로필은 인식을 활성화하지 않으며, 직접 캡처한 화면으로 ROI와 템플릿을 보정해야 함. `--demo`는 자체 생성 이미지와 **가상의 데모 보스**로 세 가지 흐름을 확인하는 모드임. 실제 게임 인식률을 증명하지 않음.

## 실행

Python **3.12**를 사용함. Anaconda에서는 `conda create -n loa-helper python=3.12`와 `conda activate loa-helper`로 환경을 만들 수 있음. 일반 Python에서는 `python -m venv .venv` 이후 Windows의 `.venv\Scripts\activate` 또는 Linux의 `source .venv/bin/activate`를 사용함.

```bash
python -m pip install -r requirements-lock.txt
python -m pip install --no-deps --no-build-isolation -e .
python -m loa_raid_helper --demo
```

기본 설정은 다음 명령으로 생성하며 기존 파일은 덮어쓰지 않음.

```bash
python -m loa_raid_helper --init-config local/profile.json
python tools/calibrate.py --help
python -m loa_raid_helper --config local/profile.json
```

실제 모니터링은 Windows의 창 모드 또는 테두리 없는 창 모드에서 확인해야 함. HP ROI, 레이드 앵커, 보스 앵커를 등록해야 음성 기믹 안내가 활성화됨. 한국어 음성은 운영체제에 한국어 TTS 음성이 설치되어 있어야 하며, 없으면 화면 안내를 계속 사용함.

## 검증·배포

```bash
python -m pytest -q
python -m loa_raid_helper --smoke-test
python -m PyInstaller --noconfirm --clean loa_raid_helper.spec
```

`--smoke-test`는 실제 CPU OCR 모델, 합성 이미지 템플릿, 안내 중복 방지, Qt 화면 표시를 확인함. 외부 모델 다운로드 없이 설치 패키지에 포함된 모델을 사용함. Windows 실행 파일은 **Windows에서 빌드**해야 함. Linux 빌드 결과는 Linux용이며 Windows 배포를 검증하지 않음. 결과 폴더는 `dist/LoaRaidHelper`임.

클라우드 개발 환경은 `/workspace/loa_raid_helper`와 `/workspace/.venvs/loa-raid-helper`를 사용함. 화면이 없는 환경에서는 `QT_QPA_PLATFORM=offscreen`으로 UI를 검증함. 프로세스는 환경 스냅샷에 유지되지 않으므로 새 작업에서 필요 시 다시 실행함.

## 문서

- [구조와 인터페이스](docs/architecture.md)
- [인식 기술 선정과 학습 도입 기준](docs/recognition.md)
- [ROI·템플릿 보정과 평가](docs/calibration.md)
- [Windows 실행·음성·배포](docs/windows.md)
- [클라우드 시작·검증 절차](docs/cloud-environment.md)

주요 의존성의 라이선스와 OCR 모델 이용 조건은 별도 배포 전에 확인해야 함. 실제 화면 캡처, DPI·다중 모니터, 클릭 통과, 한국어 음성, 실제 레이드 판별은 Windows 실기 검증 대상으로 남아 있음.
