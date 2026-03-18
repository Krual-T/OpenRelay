#!/usr/bin/env bash
set -euo pipefail

UNIT_NAME="${1:-${OPENRELAY_SYSTEMD_UNIT:-openrelay.service}}"

echo "Restarting ${UNIT_NAME}..."
systemctl --user restart "${UNIT_NAME}"

echo
systemctl --user is-active "${UNIT_NAME}" >/dev/null
systemctl --user show "${UNIT_NAME}" \
  --property=ActiveState \
  --property=ActiveEnterTimestamp \
  --property=ExecMainPID \
  --no-pager

echo
systemctl --user status "${UNIT_NAME}" --no-pager | sed -n '1,20p'
