#!/usr/bin/env bash

acquire_launch_lock() {
  local lock_dir="$1"
  local owner_pid=""

  if ! mkdir "$lock_dir" 2>/dev/null; then
    if [[ ! -f "$lock_dir/pid" ]]; then
      sleep 1
    fi
    if [[ -f "$lock_dir/pid" ]]; then
      read -r owner_pid <"$lock_dir/pid" || true
      if [[ "$owner_pid" =~ ^[0-9]+$ ]] && kill -0 "$owner_pid" 2>/dev/null; then
        return 1
      fi
      rm -f "$lock_dir/pid"
    fi
    rmdir "$lock_dir" 2>/dev/null || return 1
    mkdir "$lock_dir" 2>/dev/null || return 1
  fi

  printf '%s\n' "$$" >"$lock_dir/pid"
}

release_launch_lock() {
  local lock_dir="$1"
  local owner_pid=""

  if [[ -f "$lock_dir/pid" ]]; then
    read -r owner_pid <"$lock_dir/pid" || true
    if [[ "$owner_pid" == "$$" ]]; then
      rm -f "$lock_dir/pid"
      rmdir "$lock_dir" 2>/dev/null || true
    fi
  fi
}
