# EasyALMOS macOS Packaging

This document explains the current macOS bootstrap-app packaging for EasyALMOS.

## Current outputs

```text
dist/macos/easyalmos-<VERSION>.dmg
```

## Current status

The bootstrap app workflow is now defined in the repository, but it still has to be built and tested on a real Mac.

The compatibility baseline is macOS 11 Big Sur. This keeps the current Big Sur 11.7 VM useful as the lowest practical test target while still supporting newer macOS releases.

## Build command

On macOS:

```bash
chmod +x packaging/macos/build.sh
./packaging/macos/build.sh
```

## Build requirements

- a real Mac
- macOS 11 Big Sur or newer
- `rsync`
- `hdiutil`
- `grep`
- `sed`

## Compatibility target

The macOS package should support:

- Intel Macs through the `osx-64` Micromamba target
- Apple Silicon Macs through the `osx-arm64` Micromamba target
- macOS 11 Big Sur or newer

The bootstrapper detects the architecture at first launch, sets `CONDA_SUBDIR` to the matching Micromamba platform, and installs the matching runtime. AMD-based macOS systems are not an official distribution target.

## Source of truth

macOS packaging should use the same dependency source as the other platforms:

```text
packaging/shared/almos.yaml
```

## Relevant files

- `packaging/macos/build.sh`
- `packaging/macos/README.md`
- `packaging/macos/assets/`
- `packaging/macos/app/EasyALMOS.app/Contents/Info.plist`
- `packaging/macos/scripts/bootstrap_easyalmos_macos.sh`
- `packaging/macos/scripts/launch_easyalmos_macos.sh`

## What the current build does

1. Reads the version from the Windows installer definition
2. Creates a staged `EasyALMOS.app`
3. Copies `packaging/shared/almos.yaml` into the app resources
4. Copies the bootstrap and launcher scripts
5. Optionally bundles predownloaded Micromamba binaries
6. Creates a `.dmg` containing `EasyALMOS.app` and an `Applications` shortcut

The build uses `packaging/macos/assets/easyalmos.icns` when present. It does not reuse the Windows `.ico` file as a macOS icon.

## User installation model

The intended user flow is:

1. Download `easyalmos-<VERSION>.dmg`
2. Open the downloaded disk image
3. Drag `EasyALMOS.app` to `Applications`
4. Open EasyALMOS from Applications, Launchpad, or Spotlight
5. On first launch, EasyALMOS installs Micromamba and creates the environment under `~/Library/ApplicationSupport/EasyALMOS`
6. Later launches reuse the installed runtime

## Runtime location

The macOS bootstrapper stores its runtime here:

```text
~/Library/ApplicationSupport/EasyALMOS
```

That location contains:

- `bin/micromamba`
- `envs/almos`
- `logs/`
- `state/`

At launch time, the app runs the Python interpreter inside `envs/almos` directly and exports the private environment paths so ALMOS subprocesses can find `python` and native libraries.

During first launch, the installer writes the detected macOS version, machine architecture, and Micromamba platform to the install log. This is important when testing Intel and Apple Silicon separately.

## User removal

To remove EasyALMOS on macOS:

1. Delete `EasyALMOS.app` from `Applications`
2. Remove `~/Library/ApplicationSupport/EasyALMOS` if you also want to remove the installed runtime and logs

## What is still missing

To finish hardening macOS packaging:

1. Build on a real Mac
2. Test on Big Sur 11.7 Intel as the minimum supported baseline
3. Test on a newer Intel macOS release if available
4. Test on Apple Silicon
5. Test the `.dmg` flow, launch, Spotlight discovery, updates, and removal

## Signing

Code signing and notarization are intentionally out of scope for now.

That means Gatekeeper warnings are expected until signing is added later.
