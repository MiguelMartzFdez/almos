# Shared Packaging Inputs

This folder contains the packaging inputs shared by Windows, Linux, and macOS.

## Main file

```text
packaging/shared/almos.yaml
```

This is the dependency source of truth for EasyALMOS.

## Rule

If the application runtime changes:

1. edit `packaging/shared/almos.yaml`
2. rebuild the installer or package for the platform you want to ship
3. test a clean install on that platform

Platform-specific support files can still exist in each packaging folder, but they should not replace `almos.yaml` as the main editable definition.
