#!/usr/bin/env bash
# Give the 4 GiB Gala hosts room for short migration/container-restart peaks.
# This is part of first boot and every reviewed release, never an EC2 hotfix.
set -euo pipefail

swap_file=/var/lib/tibillet-gala/swapfile
swap_bytes=2147483648
fstab_entry="$swap_file none swap sw 0 0"

[[ -d /var/lib/tibillet-gala ]] || { echo 'Gala runtime directory is missing' >&2; exit 1; }
if [[ -e "$swap_file" || -L "$swap_file" ]]; then
  [[ -f "$swap_file" && ! -L "$swap_file" ]] || { echo 'Gala swap path is not a regular file' >&2; exit 1; }
  [[ "$(stat -c %s "$swap_file")" == "$swap_bytes" ]] || {
    echo 'Existing Gala swap file has an unexpected size' >&2; exit 1;
  }
else
  fallocate -l "$swap_bytes" "$swap_file"
  chmod 0600 "$swap_file"
  mkswap -q "$swap_file"
fi
chmod 0600 "$swap_file"

if ! swapon --noheadings --show=NAME | grep -Fxq "$swap_file"; then
  swapon "$swap_file"
fi
if ! grep -Fxq "$fstab_entry" /etc/fstab; then
  if grep -Eq '^/var/lib/tibillet-gala/swapfile[[:space:]]' /etc/fstab; then
    echo 'Conflicting Gala swap entry in fstab' >&2; exit 1
  fi
  printf '%s\n' "$fstab_entry" >> /etc/fstab
fi

# Prefer RAM during normal traffic; the file is a safety net for brief peaks.
printf 'vm.swappiness = 10\n' > /etc/sysctl.d/90-tibillet-gala-swap.conf
sysctl -w vm.swappiness=10 >/dev/null
printf 'Gala host swap ready: 2 GiB\n'
