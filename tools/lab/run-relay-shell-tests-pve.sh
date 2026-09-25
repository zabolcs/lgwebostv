#!/bin/sh
set -eu
pct push 125 /tmp/codex-relay-tests.tar /tmp/codex-relay-tests.tar
pct exec 125 -- sh -c '
set -eu
testdir=$(mktemp -d /tmp/codex-relay-tests.XXXXXX)
tar -xf /tmp/codex-relay-tests.tar -C "$testdir"
python3 "$testdir/remote-control/tests/test_broker_supervisor.py" -v
'
