# OCR 모델과 Qt 플러그인을 함께 배포하는 설정임
from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH)
ocr_data = collect_data_files("rapidocr_onnxruntime")
a = Analysis(
    [str(root / "tools" / "launcher.py")],
    pathex=[str(root / "src")],
    binaries=[], datas=ocr_data, hiddenimports=[],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "torch", "tensorflow", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="LoaRaidHelper",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=sys.platform != "win32",
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="LoaRaidHelper")
