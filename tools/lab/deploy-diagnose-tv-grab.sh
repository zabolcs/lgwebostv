set -eu
ROOT=/var/lib/webosbrew/remote-broker
printf 'files\n'; ls -la "$ROOT" 2>/dev/null || true
printf 'config\n'; cat "$ROOT/bindings.conf" 2>/dev/null || true
printf 'disabled-reason\n'; cat "$ROOT/disabled-reason" 2>/dev/null || true
printf 'runtime-log\n'; tail -n 120 /tmp/hu.szabi.remote-broker.log 2>/dev/null || true
printf 'pids\n'; pidof remote-broker 2>/dev/null || true
printf 'supervisor='; cat /tmp/hu.szabi.remote-broker-supervisor.pid 2>/dev/null || echo none
printf 'kernel-tail\n'; dmesg 2>/dev/null | tail -n 25 || true
