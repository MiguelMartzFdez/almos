# EasyALMOS Linux Packaging

This folder contains the Linux-specific packaging files for EasyALMOS.

## Output

```text
dist/linux/easyalmos-<VERSION>.deb
```

## Build

Run on Ubuntu or another Debian-based Linux system:

```bash
chmod +x packaging/linux/build-deb.sh
./packaging/linux/build-deb.sh
```

## Dependency source

Linux packaging uses:

```text
packaging/shared/almos.yaml
```

## Main contents

- `build-deb.sh`: builds the `.deb`
- `assets/`: bundled Linux packaging assets
- `scripts/`: install, launch, shortcut, and uninstall logic
- `assets/`: bundled Linux bootstrap binaries

For full details, see:

- [Linux packaging](../../docs/packaging-linux.md)
