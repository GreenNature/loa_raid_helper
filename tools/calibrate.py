"""스크린샷의 ROI와 외부 아이콘 템플릿을 보정하는 도구임."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from loa_raid_helper.config import default_config_data, load_config
from loa_raid_helper.domain import ROI


ROI_KEYS = ("hp_roi", "boss_roi", "buffs_roi", "lobby_roi")
TEMPLATE_KINDS = ("buff", "class", "raid_anchor", "boss_anchor", "lobby_anchor")


def read_image(path: Path):
    """한글 경로를 지원하여 BGR 이미지를 읽음."""
    image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"이미지를 읽을 수 없음: {path}")
    return image


def write_bytes(path: Path, content: bytes, *, overwrite: bool = False):
    """명시적 덮어쓰기 시 원본을 백업한 뒤 파일을 교체함."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.exists():
        if not overwrite:
            raise FileExistsError(f"기존 파일을 보존함. 다른 경로나 --overwrite를 사용해야 함: {path}")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = path.with_name(f"{path.name}.bak.{stamp}")
        shutil.copy2(path, backup)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return backup


def write_json(path: Path, data, *, overwrite: bool = False):
    """한글 JSON을 안전하게 저장함."""
    return write_bytes(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8"), overwrite=overwrite)


def config_data(path: Path | None):
    """설정을 검증하고 템플릿 경로를 절대 경로로 보존함."""
    if path is None:
        return default_config_data()
    path = path.resolve()
    load_config(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("raid_anchor", "boss_anchor", "lobby_anchor"):
        if data.get(key):
            data[key]["path"] = str((path.parent / data[key]["path"]).resolve())
    for key in ("buffs", "classes"):
        for template in data.get(key, []):
            template["path"] = str((path.parent / template["path"]).resolve())
    return data


def save_config(path: Path, data, *, overwrite: bool = False):
    """저장 위치를 기준으로 리소스 경로를 다시 계산함."""
    output = json.loads(json.dumps(data))
    templates = [output[key] for key in ("raid_anchor", "boss_anchor", "lobby_anchor") if output.get(key)]
    templates += output.get("buffs", []) + output.get("classes", [])
    for template in templates:
        template["path"] = os.path.relpath(Path(template["path"]).resolve(), path.resolve().parent)
    return write_json(path, output, overwrite=overwrite)


def register_template(data, entry, image_path: Path):
    """템플릿을 앵커 또는 아이콘 설정에 등록함."""
    template = {key: entry[key] for key in ("id", "label", "threshold", "synergy")}
    template["path"] = str(image_path.resolve())
    if entry["kind"] in ("buff", "class"):
        key = "buffs" if entry["kind"] == "buff" else "classes"
        items = [item for item in data.get(key, []) if item["id"] != entry["id"]]
        data[key] = items + [template]
    else:
        data[entry["kind"]] = template


def save_template(image, image_source: Path, roi: ROI, output: Path, manifest: Path,
                  *, identifier: str, label: str, kind: str, source: str,
                  threshold: float = 0.88, synergy: str = "", overwrite: bool = False):
    """선택 영역과 출처·해시를 저장함."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", identifier):
        raise ValueError("ID는 영문·숫자로 시작하고 영문·숫자·점·밑줄·하이픈만 사용할 수 있음")
    if not 0 < threshold <= 1:
        raise ValueError("임계값은 0 초과 1 이하여야 함")
    if output.suffix.lower() != ".png":
        raise ValueError("템플릿 저장 경로는 .png여야 함")
    if len({image_source.resolve(), output.resolve(), manifest.resolve()}) != 3:
        raise ValueError("원본 화면·출력 PNG·manifest 경로는 서로 달라야 함")
    if not source.strip():
        raise ValueError("템플릿 출처를 입력해야 함")
    data = {"schema_version": 1, "templates": []}
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1 or not isinstance(data.get("templates"), list):
            raise ValueError("지원하지 않는 manifest 형식임")
        if any(entry["id"] == identifier for entry in data["templates"]) and not overwrite:
            raise FileExistsError("manifest에 같은 ID가 있음. 새 ID나 --overwrite를 사용해야 함")
    cropped = roi.crop(image)
    if min(cropped.shape[:2]) < 4 or float(cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY).std()) < 5.0:
        raise ValueError("템플릿은 가로·세로 4픽셀 이상이며 구분 가능한 무늬가 있어야 함")
    success, encoded = cv2.imencode(".png", cropped)
    if not success:
        raise ValueError("선택 영역을 PNG로 변환할 수 없음")
    payload = encoded.tobytes()
    entry = {
        "id": identifier, "label": label or identifier, "kind": kind,
        "path": os.path.relpath(output.resolve(), manifest.resolve().parent),
        "sha256": hashlib.sha256(payload).hexdigest(), "source": source,
        "source_image_sha256": hashlib.sha256(image_source.read_bytes()).hexdigest(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "roi": {"x": roi.x, "y": roi.y, "width": roi.width, "height": roi.height},
        "threshold": threshold, "synergy": synergy,
    }
    write_bytes(output, payload, overwrite=overwrite)
    data["templates"] = [item for item in data["templates"] if item["id"] != identifier] + [entry]
    write_json(manifest, data, overwrite=manifest.exists())
    return entry


def crop_command(args):
    """정규화 좌표로 템플릿을 만들고 선택적으로 설정에 추가함."""
    if args.config and not args.config_output:
        raise ValueError("--config 입력을 사용할 때 --config-output 저장 경로가 필요함")
    data = config_data(args.config)
    if args.config_output and args.config_output.exists() and not args.overwrite:
        raise FileExistsError(f"설정 출력 파일이 이미 있음: {args.config_output}")
    manifest = args.manifest or args.output.parent / "manifest.json"
    if args.config_output and args.config_output.resolve() in {args.output.resolve(), manifest.resolve(), args.image.resolve()}:
        raise ValueError("설정 출력 경로는 원본 화면·PNG·manifest와 달라야 함")
    entry = save_template(read_image(args.image), args.image, ROI(*args.roi), args.output, manifest,
                          identifier=args.id, label=args.label or args.id, kind=args.kind,
                          source=args.source, threshold=args.threshold, synergy=args.synergy,
                          overwrite=args.overwrite)
    if args.config_output:
        register_template(data, entry, args.output)
        save_config(args.config_output, data, overwrite=args.overwrite)
    print(json.dumps({"template": str(args.output), "manifest": str(manifest),
                      "config": str(args.config_output) if args.config_output else None,
                      "entry": entry}, ensure_ascii=False, indent=2))


def gui_command(args):
    """드래그로 ROI와 아이콘을 선택하는 Qt 보정 창을 실행함."""
    from PySide6.QtCore import QRectF, Qt, Signal
    from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
    from PySide6.QtWidgets import (QApplication, QComboBox, QDoubleSpinBox, QFileDialog,
                                  QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                                  QMessageBox, QPushButton, QVBoxLayout, QWidget)

    class SelectionCanvas(QWidget):
        selected = Signal(object)

        def __init__(self):
            super().__init__()
            self.setMinimumSize(640, 360)
            self.pixmap = None
            self.selection = None
            self.origin = None
            self.image_rect = QRectF()

        def set_image(self, frame):
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.pixmap = QPixmap.fromImage(QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format.Format_RGB888).copy())
            self.selection = None
            self.update()

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor("#151925"))
            if self.pixmap is None:
                return
            size = self.pixmap.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            self.image_rect = QRectF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2, size.width(), size.height())
            painter.drawPixmap(self.image_rect.toRect(), self.pixmap)
            if self.selection:
                roi = self.selection
                rect = QRectF(self.image_rect.x() + roi.x * size.width(), self.image_rect.y() + roi.y * size.height(), roi.width * size.width(), roi.height * size.height())
                painter.fillRect(rect, QColor(94, 234, 212, 45))
                painter.setPen(QPen(QColor("#5eead4"), 2))
                painter.drawRect(rect)

        def normalized(self, position):
            return (max(0., min(1., (position.x() - self.image_rect.x()) / self.image_rect.width())),
                    max(0., min(1., (position.y() - self.image_rect.y()) / self.image_rect.height())))

        def mousePressEvent(self, event):
            if event.button() == Qt.MouseButton.LeftButton and self.image_rect.contains(event.position()):
                self.origin = self.normalized(event.position())

        def mouseMoveEvent(self, event):
            if self.origin is None:
                return
            x, y = self.normalized(event.position())
            x0, y0 = self.origin
            if abs(x - x0) > .001 and abs(y - y0) > .001:
                self.selection = ROI(min(x, x0), min(y, y0), abs(x - x0), abs(y - y0))
                self.update()
                self.selected.emit(self.selection)

        def mouseReleaseEvent(self, event):
            self.mouseMoveEvent(event)
            self.origin = None

    class CalibrationWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("레이드 헬퍼 · 화면 보정")
            self.resize(1200, 840)
            self.data = config_data(args.config)
            self.image_path = None
            self.frame = None
            self.output = args.output
            self.canvas = SelectionCanvas()
            self.status = QLabel("스크린샷을 열고 필요한 영역을 드래그하세요.")
            self.roi_key = QComboBox()
            self.roi_key.addItems(ROI_KEYS)
            self.identifier = QLineEdit()
            self.identifier.setPlaceholderText("예: boss_demo 또는 buff_attack")
            self.label = QLineEdit()
            self.kind = QComboBox()
            self.kind.addItems(TEMPLATE_KINDS)
            self.source = QLineEdit(args.source)
            self.synergy = QLineEdit()
            self.threshold = QDoubleSpinBox()
            self.threshold.setRange(.01, 1.)
            self.threshold.setSingleStep(.01)
            self.threshold.setValue(.88)
            form = QFormLayout()
            form.addRow("ROI 항목", self.roi_key)
            form.addRow("템플릿 ID", self.identifier)
            form.addRow("표시 이름", self.label)
            form.addRow("용도", self.kind)
            form.addRow("출처", self.source)
            form.addRow("시너지 문구", self.synergy)
            form.addRow("일치 임계값", self.threshold)
            buttons = QHBoxLayout()
            for title, handler in (("스크린샷 열기", self.open_image), ("ROI 적용", self.apply_roi),
                                   ("템플릿 저장", self.save_icon), ("설정 저장", self.save_settings)):
                button = QPushButton(title)
                button.clicked.connect(handler)
                buttons.addWidget(button)
            layout = QVBoxLayout()
            layout.addWidget(self.canvas, 1)
            layout.addWidget(self.status)
            layout.addLayout(form)
            layout.addLayout(buttons)
            container = QWidget()
            container.setLayout(layout)
            self.setCentralWidget(container)
            self.canvas.selected.connect(self.update_selection)
            if args.image:
                self.open_image(args.image)

        def update_selection(self, roi):
            self.status.setText(f"선택 영역: x={roi.x:.4f}, y={roi.y:.4f}, width={roi.width:.4f}, height={roi.height:.4f}")

        def error(self, exc):
            QMessageBox.warning(self, "작업을 완료할 수 없음", str(exc))

        def open_image(self, path=None):
            if not isinstance(path, Path):
                name, _ = QFileDialog.getOpenFileName(self, "스크린샷 열기", "", "이미지 (*.png *.jpg *.jpeg *.bmp *.webp)")
                if not name:
                    return
                path = Path(name)
            try:
                self.frame = read_image(path)
                self.image_path = path
                self.canvas.set_image(self.frame)
                self.status.setText(f"{path.name} · 영역을 드래그하세요.")
            except Exception as exc:
                self.error(exc)

        def apply_roi(self):
            roi = self.canvas.selection
            if roi is None:
                self.error("먼저 영역을 드래그해야 함")
                return
            self.data[self.roi_key.currentText()] = {"x": roi.x, "y": roi.y, "width": roi.width, "height": roi.height}
            self.status.setText(f"{self.roi_key.currentText()} 적용됨 · 설정 저장을 눌러야 파일에 반영됨")

        def confirm_replace(self, path):
            if not path.exists():
                return True
            return QMessageBox.question(self, "기존 파일 백업", f"기존 파일을 백업한 뒤 저장할까요?\n{path}", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

        def save_icon(self):
            if self.canvas.selection is None or self.image_path is None:
                self.error("먼저 스크린샷 영역을 선택해야 함")
                return
            identifier = self.identifier.text().strip()
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", identifier):
                self.error("템플릿 ID에 영문·숫자·점·밑줄·하이픈만 사용할 수 있음")
                return
            output = args.assets / f"{identifier}.png"
            if not self.confirm_replace(output):
                return
            try:
                entry = save_template(self.frame, self.image_path, self.canvas.selection, output,
                                      args.manifest or args.assets / "manifest.json",
                                      identifier=identifier, label=self.label.text().strip() or identifier,
                                      kind=self.kind.currentText(), source=self.source.text().strip(),
                                      threshold=self.threshold.value(), synergy=self.synergy.text().strip(),
                                      overwrite=output.exists())
                register_template(self.data, entry, output)
                self.status.setText(f"{output} 저장됨 · 설정 저장을 눌러 등록을 완료하세요.")
            except Exception as exc:
                self.error(exc)

        def save_settings(self):
            name, _ = QFileDialog.getSaveFileName(self, "설정 저장", str(self.output), "JSON 설정 (*.json)", options=QFileDialog.Option.DontConfirmOverwrite)
            if not name:
                return
            path = Path(name)
            if not self.confirm_replace(path):
                return
            try:
                backup = save_config(path, self.data, overwrite=path.exists())
                self.output = path
                self.status.setText(f"설정 저장됨: {path}" + (f" · 백업: {backup.name}" if backup else ""))
            except Exception as exc:
                self.error(exc)

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyleSheet("QWidget { background: #171b29; color: #e6edf3; font-size: 13px; } QPushButton { background: #2c344a; padding: 9px; border-radius: 5px; } QLineEdit, QComboBox, QDoubleSpinBox { background: #232b3e; padding: 5px; }")
    window = CalibrationWindow()
    window.show()
    return app.exec()


def main():
    """보정 도구의 명령행 진입점임."""
    parser = argparse.ArgumentParser(description="스크린샷 ROI 및 아이콘 템플릿 보정 도구임")
    commands = parser.add_subparsers(dest="command", required=True)
    gui = commands.add_parser("gui", help="드래그로 ROI와 템플릿을 지정함")
    gui.add_argument("--image", type=Path, help="보정할 스크린샷 경로임")
    gui.add_argument("--config", type=Path, help="읽을 기존 설정이며 원본은 보존함")
    gui.add_argument("--output", type=Path, default=Path("local/profile.calibrated.json"), help="새 설정의 기본 저장 경로임")
    gui.add_argument("--assets", type=Path, default=Path("local/templates"), help="잘라낸 템플릿 저장 폴더임")
    gui.add_argument("--manifest", type=Path, help="출처·해시 목록의 저장 경로임")
    gui.add_argument("--source", default="사용자가 직접 캡처한 스크린샷", help="리소스 출처와 이용 조건을 기록함")
    crop = commands.add_parser("crop", help="GUI 없이 정규화 ROI로 템플릿을 자름")
    crop.add_argument("image", type=Path)
    crop.add_argument("--roi", type=float, nargs=4, required=True, metavar=("X", "Y", "WIDTH", "HEIGHT"))
    crop.add_argument("--output", type=Path, required=True, help="새 PNG 저장 경로임")
    crop.add_argument("--id", required=True)
    crop.add_argument("--label")
    crop.add_argument("--kind", choices=TEMPLATE_KINDS, default="buff")
    crop.add_argument("--source", default="사용자가 직접 캡처한 스크린샷")
    crop.add_argument("--manifest", type=Path)
    crop.add_argument("--threshold", type=float, default=.88)
    crop.add_argument("--synergy", default="")
    crop.add_argument("--config", type=Path, help="기존 설정의 입력 경로임")
    crop.add_argument("--config-output", type=Path, help="템플릿을 등록한 새 설정 저장 경로임")
    crop.add_argument("--overwrite", action="store_true", help="기존 파일을 백업한 뒤 교체함")
    args = parser.parse_args()
    try:
        return gui_command(args) if args.command == "gui" else crop_command(args) or 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"오류: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
