# EasyALMOS macOS Packaging

This folder contains the macOS bootstrap-app packaging for EasyALMOS.

## Current outputs

```text
dist/macos/easyalmos-<VERSION>.dmg
```

The `.dmg` is the distribution artifact. `EasyALMOS.app` exists inside the mounted disk image for the user to drag into `Applications`.

## Build

Run on a real Mac:

```bash
chmod +x packaging/macos/build.sh
./packaging/macos/build.sh
```

Requirements:

- macOS 11 Big Sur or newer
- `rsync`
- `hdiutil`
- `grep`
- `sed`

## Dependency source

macOS packaging should use:

```text
packaging/shared/almos.yaml
```

## Current status

The macOS package now follows the same lightweight model as Windows and Linux:

- `EasyALMOS.app` is a bootstrap launcher
- first launch installs Micromamba and creates the environment
- the runtime is stored under `~/Library/ApplicationSupport/EasyALMOS`
- later launches reuse that installed runtime

Compatibility target:

- macOS 11 Big Sur or newer
- Intel Macs using `osx-64`
- Apple Silicon Macs using `osx-arm64`

Optional assets:

- `assets/micromamba-osx-64`
- `assets/micromamba-osx-arm64`
- `assets/easyalmos.icns`

For the full workflow, see:

- [macOS packaging](../../docs/packaging-macos.md)
