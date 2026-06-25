# EasyALMOS Packaging Overview

This repository keeps packaging separated by operating system so the workspace stays easy to understand.

## Main rule

Dependencies are shared across platforms from one place:

```text
packaging/shared/almos.yaml
```

If the runtime changes, edit that file first.

## Folder layout

```text
EasyALMOS/
|-- packaging/
|   |-- shared/
|   |   |-- almos.yaml
|   |   `-- README.md
|   |-- windows/
|   |   |-- build.ps1
|   |   |-- EasyALMOS.iss
|   |   |-- assets/
|   |   `-- scripts/
|   |-- linux/
|   |   |-- assets/
|   |   |-- scripts/
|   |   |-- README.md
|   |   `-- build-deb.sh
|   `-- macos/
|       |-- assets/
|       |-- app/
|       |-- scripts/
|       |-- README.md
|       `-- build.sh
|-- docs/
|   |-- packaging.md
|   |-- packaging-windows.md
|   |-- packaging-linux.md
|   `-- packaging-macos.md
`-- dist/
    |-- windows/
    |-- linux/
    `-- macos/
```

## Platform outputs

- Windows: `dist/windows/easyalmos-<VERSION>.exe`
- Linux: `dist/linux/easyalmos-<VERSION>.deb`
- macOS: `dist/macos/easyalmos-<VERSION>.dmg`

## Build hosts

Each final artifact is built on its own operating system:

- Windows `.exe`: build on Windows
- Linux `.deb`: build on Linux
- macOS `.dmg`: build on macOS

The repository, dependency source, and packaging structure are shared, but the final installers are not all produced from one host.

## Platform model

### Windows

- installer format: `.exe`
- runtime source: `packaging/shared/almos.yaml`
- build entry point: `.\packaging\windows\build.ps1`
- build host: Windows with Inno Setup 6 or 7
- end-user result: EasyALMOS appears in Start Menu, Windows Search, and optionally on the Desktop

### Linux

- installer format: `.deb`
- runtime source: `packaging/shared/almos.yaml`
- build entry point: `./packaging/linux/build-deb.sh`
- build host: Linux with `dpkg-deb`
- end-user result: EasyALMOS appears in the applications menu and can also create a desktop shortcut

### macOS

- current distribution format: `.dmg` containing `EasyALMOS.app`
- runtime source: `packaging/shared/almos.yaml`
- build entry point: `./packaging/macos/build.sh`
- build host: a real Mac with `rsync` and `hdiutil`
- current status: bootstrap-app flow implemented, build and testing must happen on a real Mac

## What to change

### If only installer behavior changed

Examples:

- setup text
- shortcut behavior
- launch messages
- package metadata
- icon or launcher adjustments

Then update only the relevant platform folder and docs.

### If dependencies changed

1. Edit `packaging/shared/almos.yaml`
2. Rebuild the platform installer
3. Verify a clean installation on that platform
