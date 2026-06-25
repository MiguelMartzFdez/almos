# EasyALMOS Packaging Notes

Packaging documentation is now split by platform:

- [Overview](docs/packaging.md)
- [Windows packaging](docs/packaging-windows.md)
- [Linux packaging](docs/packaging-linux.md)
- [macOS packaging](docs/packaging-macos.md)

Windows builds are generated directly with:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\windows\build.ps1
```

Linux packages are generated on Linux with:

```bash
./packaging/linux/build-deb.sh
```

macOS disk images are generated on macOS with:

```bash
./packaging/macos/build.sh
```
