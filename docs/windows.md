# Windows 실행·음성·배포

실제 게임 화면 캡처와 오버레이는 Windows에서 검증해야 함. Linux 클라우드에서는 CPU OCR, 저장 이미지 인식, 안내 정책, Qt offscreen UI, Linux 패키지 실행을 검증할 수 있음. Linux 결과로 Windows 실행 파일이나 실제 게임 호환성을 보장하지 않음.

## Python 3.12 환경

Windows x64와 Python 3.12를 기준으로 함. Anaconda를 사용할 때 저장소 루트에서 다음 명령을 실행함.

```powershell
conda create -n loa-helper python=3.12 pip
conda activate loa-helper
python -m pip install -r requirements-lock.txt
python -m pip install --no-deps --no-build-isolation -e .
python -m loa_raid_helper --demo
```

일반 Python을 사용할 경우 `python -m venv .venv`로 환경을 만들고 PowerShell에서 `.\.venv\Scripts\Activate.ps1`로 활성화한 뒤 동일한 설치 명령을 실행함. 보안 정책으로 활성화가 제한된 PC에서는 정책을 무조건 변경하지 말고 `.\.venv\Scripts\python.exe`를 직접 사용함. 설치 중 TLS·패키지 검증을 비활성화하지 않음.

CPU OCR 모델은 설치된 `rapidocr-onnxruntime` 패키지의 리소스를 사용함. CUDA, 별도 GPU 학습 환경, Tesseract 실행 파일은 현재 필수 구성이 아님. Qt UI에는 PySide6을 사용하며 OpenCV 창은 사용하지 않음.

## 실제 화면 연결

```powershell
python -m loa_raid_helper --init-config local/profile.json
python tools/calibrate.py gui --config local/profile.json --image local/raid.png
python -m loa_raid_helper --config local/profile.calibrated.json
```

창 모드 또는 테두리 없는 창 모드로 실행하고, 모니터 전체에서 캡처된 게임 위치에 ROI를 맞춤. 현재 설정은 지정 모니터 화면 기준이며 게임 창 자동 추적은 제공하지 않음. 해상도나 창 위치를 바꾸면 보정 결과도 확인해야 함. 모니터 번호는 1부터 시작함. 제어 패널의 `모니터링 시작`으로 캡처를 시작하고 X·Y 값으로 오버레이를 캐릭터 옆에 배치함.

오버레이는 고정 위치의 입력 통과 창임. X·Y 조정값은 런타임 값이며 앱을 다시 실행하면 화면 중심 기준 기본 위치로 초기화됨. 독점 전체 화면에서 표시를 보장하지 않음. 입력 통과·항상 위 표시·다중 모니터 좌표는 실제 PC에서 확인함. 오버레이가 캡처에 다시 포함되어 ROI를 가리면 인식 영역 밖으로 옮김. 초기 구현은 Windows 캡처 제외 API를 적용하지 않음.

## 한국어 음성

Windows 설정의 언어·음성 항목에서 한국어 음성 기능을 설치한 뒤 앱을 다시 실행함. 앱은 Qt TextToSpeech에서 사용 가능한 한국어 음성을 선택함. 한국어 음성이나 사용 가능한 음성 엔진이 없으면 제어 패널에 상태를 표시하고 화면 안내를 유지함.

`--demo`에서 모니터링을 시작하고 데모 기믹 안내가 발생할 때 소리를 확인함. 시스템 볼륨, 출력 장치, 음소거 여부도 확인함. 클라우드의 음성 엔진 유무로 사용자의 Windows 음성 설치 여부를 판단하지 않음. 현재 안내 대기열은 최대 3개이며 긴 음성 문장은 최신 안내를 지연시킬 수 있으므로 짧은 문구를 사용함.

## PyInstaller 배포

PyInstaller는 운영체제 간 교차 빌드를 지원하지 않으므로 Windows용 `.exe`는 **Windows에서 빌드함**. Python 환경이 활성화된 저장소 루트에서 실행함.

```powershell
python -m pytest -q
python -m loa_raid_helper --smoke-test
python -m PyInstaller --noconfirm --clean loa_raid_helper.spec
.\dist\LoaRaidHelper\LoaRaidHelper.exe --demo
```

초기 배포는 `onedir` 방식이며 `dist/LoaRaidHelper` 폴더 전체를 전달함. 실행 파일만 떼어 내면 Qt 플러그인·OCR 모델·라이브러리가 누락될 수 있음. spec은 OCR 패키지의 모델·설정 리소스를 수집하고 PyInstaller의 PySide6 훅으로 Qt 의존성을 처리함. Windows에서 `qwindows` 플랫폼 플러그인, 음성 백엔드, ONNX Runtime DLL이 정상 동작하는지 최종 확인함.

사용자 템플릿과 프로필은 외부 파일로 유지함. 예를 들어 배포 폴더 옆에 `local/`을 두고 아래와 같이 실행함. 설정에 있는 템플릿 상대 경로는 실행 위치가 아닌 JSON 파일 위치 기준임.

```powershell
.\dist\LoaRaidHelper\LoaRaidHelper.exe --config .\local\profile.calibrated.json
```

배포 spec은 개인 게임 템플릿을 자동 포함하지 않음. 실제 게임 이미지·레이드 규칙·학습 모델을 나중에 포함하려면 이용 조건, 모델 라이선스, 출처·해시와 경로를 별도로 검증해야 함. 기본 기믹은 가상 데모 보스용이며 실제 공략으로 배포하면 안 됨.

## 실기 확인표

| 확인 대상 | 통과 조건 |
| --- | --- |
| 캡처 | 실제 모니터의 게임 화면이 검은 화면·이전 화면 없이 읽힘 |
| DPI | Windows 배율 100/125/150%에서 HP ROI와 오버레이 위치가 올바름 |
| 다중 모니터 | 선택 모니터와 음수 좌표를 포함한 오버레이 위치가 올바름 |
| 입력 통과 | 오버레이 위 클릭이 게임 입력을 방해하지 않고 게임 포커스를 유지함 |
| 보스 판별 | 마을·일반 몬스터·로딩 화면에서 HP·기믹 오안내가 발생하지 않음 |
| 실제 HP | 보스별 정상 화면·효과가 겹친 화면에서 숫자 완전 일치와 지연을 측정함 |
| 버프·클래스 | 같은 모양·다른 색·강조 효과·쿨다운 상태를 구분하는지 평가함 |
| 재전투 | 전멸·대기실·같은 보스 재입장에서 중복 이력이 올바르게 초기화됨 |
| 음성 | 한국어 음성 설치 PC에서 짧은 안내가 적절한 장치로 재생됨 |
| 배포 | 개발 환경이 없는 PC에서 폴더 전체와 외부 설정만으로 실행됨 |

이 항목은 Windows에서 수행해야 할 검증 목록임. 클라우드에서 실행한 합성 검사 결과와 구분하여 기록함. 캡처가 검게 나오면 창 모드와 모니터 선택을 확인하고, ROI가 어긋나면 모니터 해상도·Windows DPI·게임 UI 배율을 기록한 뒤 해당 프로필을 다시 보정함.
