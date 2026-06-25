# macOS Bootstrap Assets

This folder can contain optional prebundled Micromamba binaries for macOS.

Supported filenames:

- `micromamba-osx-64`
- `micromamba-osx-arm64`
- `easyalmos.icns`

If a matching binary is present, `packaging/macos/build.sh` bundles it into `EasyALMOS.app` and first launch does not need to download Micromamba.

If these files are absent, the macOS launcher downloads Micromamba during first launch.

`easyalmos.icns` is optional. If it is absent, the generated app uses the default macOS application icon.
