@echo off
REM Build cross_device_hid.exe as a single-file Windows executable
REM Requirements: pip install pyinstaller pynput pystray Pillow

echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

echo Building executable...
python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name cross_device_hid ^
    --add-data "README.md;." ^
    main.py

echo.
if exist dist\cross_device_hid.exe (
    echo Build successful!
    echo Executable: dist\cross_device_hid.exe
) else (
    echo Build FAILED — check output above.
)
pause
