# ROI·템플릿 보정과 평가

보정에는 자신의 해상도, UI 배율, 창 모드로 직접 캡처한 스크린샷을 사용함. 실제 게임 리소스와 검증된 기믹 데이터는 저장소에 포함되지 않음. 개인 화면에는 채팅·닉네임이 포함될 수 있으므로 원본과 잘라낸 자료를 `local/` 또는 저장소 밖에 보관함.

## GUI 보정

저장소 루트에서 실행함. `local/raid.png`는 사용자가 준비한 화면임.

```bash
python -m loa_raid_helper --init-config local/profile.json
python tools/calibrate.py gui --image local/raid.png --config local/profile.json --output local/profile.calibrated.json
```

1. `ROI 항목`에서 `hp_roi`, `boss_roi`, `buffs_roi`, `lobby_roi` 중 하나를 선택함.
2. 스크린샷에서 해당 영역을 드래그한 뒤 `ROI 적용`을 누름. 네 항목을 필요한 화면에 맞춰 반복함.
3. 아이콘이나 앵커를 드래그하고 템플릿 ID, 표시 이름, 용도, 출처, 시너지 문구를 입력함.
4. `템플릿 저장`을 누르면 PNG와 manifest가 저장되고 현재 설정에 등록됨.
5. `설정 저장`을 눌러 새 JSON을 저장함. ROI 적용과 템플릿 저장만으로 설정 파일이 자동 저장되지는 않음.

기본 출력 설정은 `local/profile.calibrated.json`, 기본 템플릿 폴더는 `local/templates`임. `--assets`, `--manifest`, `--source`로 저장 위치와 출처를 지정할 수 있음. 기존 파일은 GUI 확인 후에만 교체하며 이름에 `.bak.<UTC시각>`을 붙인 백업을 먼저 생성함. 기존 프로필을 입력으로 읽고 다른 파일에 저장하면 원본을 보존함.

| 항목 | 선택 기준 |
| --- | --- |
| `hp_roi` | 보스 HP 줄 수 한 줄만 포함함. 숫자 앞 `x`나 뒤 `줄`은 허용하지만 HP 바·보스명·다른 숫자는 제외함 |
| `boss_roi` | 보스 고유 표시 템플릿이 들어 있는 상단 영역임 |
| `buffs_roi` | 하단의 스킬·버프 아이콘이 나타나는 영역임 |
| `lobby_roi` | 대기실의 클래스 아이콘과 대기실 앵커를 포함하는 영역임 |
| `raid_anchor` | 레이드에서만 나타나는 구분 가능한 화면 무늬임. 전체 프레임에서 비교함 |
| `boss_anchor` | 특정 보스를 구별하는 무늬이며 `boss_roi` 안에서 비교함 |
| `lobby_anchor` | 대기실에서만 나타나는 무늬이며 `lobby_roi` 안에서 비교함 |
| `buff` | `buffs_roi`에서 찾을 버프 또는 스킬 아이콘임 |
| `class` | `lobby_roi`에서 찾을 클래스 아이콘이며 `synergy`에 표시할 문구를 등록함 |

템플릿은 아이콘 경계에 가깝게 자르고 애니메이션·강조 효과·겹친 숫자가 적은 프레임을 선택함. 가로·세로 4픽셀 이상이며 구분 가능한 명암 변화가 있어야 함. 단색 사각형은 잘못된 무조건 일치를 유발하므로 거부함. 해상도와 UI 배율이 크게 달라지면 별도 프로필과 템플릿을 준비함.

템플릿 ID는 영문·숫자로 시작하고 영문·숫자·점·밑줄·하이픈을 사용할 수 있음. 표시 이름과 시너지 문구는 한글을 사용할 수 있음. 동일 ID를 다시 저장하면 명시적 교체가 필요함. `boss_anchor.id`는 기믹 규칙의 `boss_id`와 같아야 함.

## 명령행 자르기

GUI가 없는 클라우드에서도 정규화 좌표로 템플릿을 만들 수 있음. 좌표 순서는 `x y width height`이며 화면의 좌상단이 `(0, 0)`임. 픽셀 사각형이 `(left, top, width, height)`이고 화면이 `(W, H)`이면 `(left/W, top/H, width/W, height/H)`로 입력함.

```bash
python tools/calibrate.py crop local/raid.png --roi 0.45 0.80 0.03 0.05 --output local/templates/attack.png --id attack --label "공격력 버프" --kind buff --source "직접 캡처, 해상도 1920x1080, UI 배율 100%" --config local/profile.json --config-output local/profile.with-buff.json
```

`--config-output` 없이 실행하면 PNG와 manifest만 생성함. 기존 설정을 입력할 때는 `--config-output`을 함께 지정해야 함. 기본 manifest는 출력 PNG 폴더의 `manifest.json`임. 기존 PNG·설정·같은 ID는 자동으로 덮어쓰지 않으며, 필요한 경우 `--overwrite`를 명시하면 백업 후 교체함. 여러 새 템플릿을 manifest에 추가할 때도 이전 manifest를 백업함.

manifest는 ID, 표시 이름, 용도, PNG의 상대 경로와 SHA-256, 원본 화면의 SHA-256, 출처, 생성 시각, ROI, 임계값, 시너지 문구를 기록함. 출처에는 캡처 방법과 이용 조건을 작성함. 이 목록은 추적 자료이며 현재 런타임이 manifest 해시를 자동 검증하는 것은 아님. 원본 화면 자체는 도구가 복제하지 않음.

## 기믹 규칙

아래는 형식 설명용 예시이며 실제 보스 공략 정보가 아님. 등록한 보스 ID, HP 임계값, 검증한 문구로 바꿔야 함.

```json
{
  "rules": [
    {"boss_id": "my_boss", "hp_lines": 175, "message": "등록한 보스 175줄 기믹 확인하세요"}
  ],
  "stable_frames": 2,
  "max_hp_lines": 999,
  "min_ocr_confidence": 0.85
}
```

기존 JSON의 해당 항목을 편집함. 예시 조각만 저장하면 ROI·앵커·버프 설정을 포함한 완전한 프로필이 되지 않음. `max_hp_lines`는 대상 레이드의 실제 범위에 맞게 정하며 인식값 상한과 급락 재확인 기준에 사용됨. 최초 인식이 이미 임계값을 지난 상태이면 지난 기믹을 소급 안내하지 않음. 자세한 상태 정책은 [구조 문서](architecture.md)에 정의함.

## 이미지 평가

```bash
python tools/evaluate.py local/screenshots --config local/profile.calibrated.json --output local/evaluation.json
python tools/evaluate.py local/screenshots --config local/profile.calibrated.json --truth local/truth.json --output local/evaluation.with-truth.json
```

파일 한 장 또는 폴더를 입력할 수 있음. 하위 폴더는 `--recursive`로 포함함. `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`를 지원하며 처리 순서는 파일명 정렬임. `--no-ocr`는 아이콘 검증 전용이며 HP OCR을 수행하지 않음. 기존 결과 파일은 덮어쓰지 않으므로 새 출력 경로를 사용함.

정답 JSON의 `frames` 키는 입력 폴더 기준 상대 경로임. 단일 파일은 파일명만 사용함. 각 항목은 필요한 지표만 기록할 수 있으며 버프·클래스 정답에는 표시 이름 대신 템플릿 ID를 사용함.

```json
{
  "frames": {
    "raid_001.png": {
      "phase": "raid",
      "boss_id": "my_boss",
      "hp_lines": 175,
      "buffs": ["attack"],
      "classes": []
    },
    "lobby_001.png": {
      "phase": "lobby",
      "boss_id": "",
      "hp_lines": null,
      "buffs": [],
      "classes": ["my_class"]
    }
  }
}
```

결과에는 프레임별 처리 시간, `FrameState`, 검출 표시 이름이 포함됨. 정답이 있는 프레임과 필드에서만 지표를 계산함. 아이콘 precision은 `TP/(TP+FP)`, recall은 `TP/(TP+FN)`임. 현재는 종류별 검출을 평가하므로 박스 위치·동일 클래스 인원 수는 평가하지 않음. HP exact match는 숫자 정답에 대한 완전 일치 비율이며 `null` 정답의 읽음 억제는 `hp_absence_accuracy`로 별도 집계함. 단계와 보스 ID 정확도도 제공함. 분모가 없으면 지표는 `null`임.

OCR의 최초 호출에는 모델 초기화 시간이 포함됨. 일반 프레임의 지연과 최초 지연을 구분하여 확인함. 이 도구는 프레임별 인식을 평가하므로 영상의 시간 순서와 기믹 안내 타이밍 검증을 대체하지 않음. 양성 화면뿐 아니라 마을·일반 몬스터·로딩·겹친 UI·비슷한 아이콘의 음성 화면도 넣어 오인식을 확인해야 함.
