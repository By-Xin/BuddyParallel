# BuddyParallel Board Support

## M5StickC Plus

- PlatformIO env: `m5stickc-plus`
- Chip: ESP32
- Bootloader address: `0x1000`
- Firmware bundle path in packaged app: `_internal/firmware/m5stickc-plus`
- Status: primary beta target, full pet UI firmware

## M5Stack CoreS3

- PlatformIO env: `m5stack-cores3`
- Chip: ESP32-S3
- Flash: 16 MB
- PSRAM: 8 MB
- Display: 2.0 inch 320x240 ILI9342C touch IPS
- USB identity used for auto-detect: `303A:8119`
- Bootloader address: `0x0`
- Firmware bundle path in packaged app: `_internal/firmware/m5stack-cores3`
- Status: USB CDC beta target, CoreS3-specific dashboard firmware

Build the CoreS3 firmware before cutting a CoreS3-enabled release:

```powershell
cd firmware
pio run -e m5stack-cores3
```

Then rebuild and package the Windows app:

```powershell
powershell -ExecutionPolicy Bypass -File ..\companion\scripts\build_windows.ps1
powershell -ExecutionPolicy Bypass -File ..\companion\scripts\package_release_zip.ps1 -Version 0.1.0-alpha.1
```

User setup flow:

1. Connect the board over USB-C.
2. Open `BuddyParallel.exe`.
3. Open `Setup Board`.
4. Leave board type on `Auto Detect`, or choose `M5Stack CoreS3` manually if auto-detect is uncertain.
5. Select the serial port.
6. Click `Flash Firmware`.
7. After reboot, Setup saves the port and board profile into `%APPDATA%\BuddyParallel\config.json`.

CoreS3 notes:

- Long-press the CoreS3 reset button for about 3 seconds to enter download mode if esptool cannot auto-reset it.
- CoreS3 support uses USB CDC first. BLE parity can be added later, but USB is the supported beta path.
- The CoreS3 firmware intentionally uses a larger 320x240 control dashboard instead of the M5StickC Plus pet animation UI.
