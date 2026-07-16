# EasyALMOS Linux Packaging

This document explains how to generate and maintain the Linux package.

## Output

```text
dist/linux/easyalmos-<VERSION>.deb
```

## Target platform

The current Linux package targets 64-bit Ubuntu and other amd64 Debian-based distributions.

## Build command

From the repository root on Linux:

```bash
chmod +x packaging/linux/build-deb.sh
./packaging/linux/build-deb.sh
```

## Build requirements

- Linux
- `dpkg-deb`
- `install`
- `grep`
- `sed`
- `packaging/linux/assets/micromamba-linux-64`

## Source of truth

Linux packaging is driven by:

```text
packaging/shared/almos.yaml
```

If dependencies change, edit that file first.

## Relevant files

- `packaging/linux/build-deb.sh`
- `packaging/linux/assets/micromamba-linux-64`
- `packaging/linux/scripts/easyalmos_bootstrap.sh`
- `packaging/linux/scripts/install_easyalmos_system.sh`
- `packaging/linux/scripts/install_desktop_shortcut_system.sh`
- `packaging/linux/scripts/launch_easyalmos.sh`
- `packaging/linux/scripts/uninstall_easyalmos.sh`

## What the package does

1. Installs the EasyALMOS launcher under `/usr/bin/easyalmos`
2. Installs the shared environment definition under `/usr/lib/easyalmos/shared/almos.yaml`
3. Uses bundled micromamba to create the runtime under `/opt/easyalmos`
4. Creates an applications menu entry
5. Attempts to create a desktop shortcut for the installing user

If runtime creation fails during package installation, the launcher can retry it later with administrator permissions.

## User installation

### Graphical install

1. Download `easyalmos-<VERSION>.deb`
2. Double-click the package
3. Install it with the system package installer
4. Open **EasyALMOS** from the applications menu or desktop shortcut

### Terminal install

```bash
sudo apt install ./easyalmos-<VERSION>.deb
```

## Log location

During package installation, logs are written under:

```text
/opt/easyalmos/logs
```

If Ubuntu shows a crash report saying that the package post-installation script failed, check:

```bash
sudo cat /opt/easyalmos/logs/install-error.log
sudo cat /opt/easyalmos/logs/install.log
```

The package post-installation step attempts to create the private runtime, but the package remains installed if that setup fails. Launching `easyalmos` retries the runtime setup with administrator permissions.

## User removal

Remove the package:

```bash
sudo dpkg -r easyalmos
```

Remove the package and the runtime under `/opt/easyalmos`:

```bash
sudo dpkg --purge easyalmos
```

## When to update Linux packaging

### Package-only changes

Change Linux packaging files only when you are updating:

- `.deb` metadata
- shortcut behavior
- launcher behavior
- install and uninstall scripts
- startup message behavior

Then rebuild the package:

```bash
./packaging/linux/build-deb.sh
```

### Dependency changes

1. Edit `packaging/shared/almos.yaml`
2. Rebuild the package
3. Test the package on Ubuntu or another Debian-based system

The current Linux package resolves from `packaging/shared/almos.yaml`.
