#!/usr/bin/env bash

normalize_machine_architecture() {
  case "$1" in
    arm64|aarch64)
      printf '%s\n' "arm64"
      ;;
    x86_64|amd64)
      printf '%s\n' "x86_64"
      ;;
    *)
      return 1
      ;;
  esac
}

resolve_host_architecture() {
  local reported_architecture translated

  reported_architecture="$(normalize_machine_architecture "$1")" || return 1
  translated="$2"

  if [[ "$reported_architecture" == "x86_64" && "$translated" == "1" ]]; then
    printf '%s\n' "arm64"
    return
  fi

  printf '%s\n' "$reported_architecture"
}

platform_for_architecture() {
  case "$(normalize_machine_architecture "$1")" in
    arm64)
      printf '%s\n' "osx-arm64"
      ;;
    x86_64)
      printf '%s\n' "osx-64"
      ;;
    *)
      return 1
      ;;
  esac
}

resolve_micromamba_platform() {
  local host_architecture

  host_architecture="$(resolve_host_architecture "$1" "$2")" || return 1
  platform_for_architecture "$host_architecture"
}

detect_micromamba_platform() {
  local reported_architecture translated

  reported_architecture="$(uname -m)"
  translated="$(sysctl -in sysctl.proc_translated 2>/dev/null || true)"
  if [[ -z "$translated" ]]; then
    translated="0"
  fi

  resolve_micromamba_platform "$reported_architecture" "$translated"
}

environment_architecture_matches_platform() {
  local environment_architecture expected_platform

  environment_architecture="$(normalize_machine_architecture "$1")" || return 1
  expected_platform="$(platform_for_architecture "$environment_architecture")" || return 1
  [[ "$expected_platform" == "$2" ]]
}
