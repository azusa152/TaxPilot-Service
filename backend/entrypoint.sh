#!/bin/bash
set -e

# Drop privileges to appuser when running as root (e.g., with bind-mount volumes)
if [ "$(id -u)" = "0" ]; then
    exec gosu appuser "$@"
fi

exec "$@"
