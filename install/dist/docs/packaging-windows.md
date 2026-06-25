# EasyALMOS Windows Packaging

This document explains how to generate and maintain the Windows installer.

## Output

```text
dist/windows/easyalmos-<VERSION>.exe
```

## Build command

From the repository root:

```powershell
.\packaging\windows\build.ps1
```

## Build requirements

- Windows
- Inno Setup 6 or 7
- `packaging/windows/assets/Miniforge3-Windows-x86_64.exe`
- `packaging/shared/almos.yaml`

## Source of truth

Windows packaging is driven by:

```text
packaging/shared/almos.yaml
```

If dependencies change, edit that file first.

## Relevant files

- `packaging/windows/build.ps1`
- `packaging/windows/EasyALMOS.iss`
- `packaging/windows/assets/`
- `packaging/windows/scripts/install_easyalmos.ps1`
- `packaging/windows/scripts/launch_easyalmos.pyw`
- `packaging/windows/scripts/uninstall_easyalmos.ps1`

## What the installer does

1. Installs the bundled Miniforge runtime
2. Creates the ALMOS environment from `packaging/shared/almos.yaml`
3. Validates the runtime
4. Creates Start Menu entries
5. Optionally creates a Desktop shortcut

## User experience

After installation, EasyALMOS should be available from:

- Start Menu
- Windows Search
- Desktop shortcut, if enabled

When startup takes a moment, the launcher shows an opening message so the user does not click repeatedly.

## Runtime location

The private runtime is created here:

```text
%LOCALAPPDATA%\Programs\EasyALMOS\miniforge\envs\almos
```

## Log location

Installer logs are written under:

```text
%LOCALAPPDATA%\Programs\EasyALMOS\logs
```

## When to update Windows packaging

### Installer-only changes

Change Windows packaging files only when you are updating:

- setup text
- shortcut behavior
- launch message behavior
- uninstall behavior
- installer branding or assets

Then rebuild the installer:

```powershell
.\packaging\windows\build.ps1
```

### Dependency changes

1. Edit `packaging/shared/almos.yaml`
2. Rebuild the installer
3. Test a clean install on Windows
