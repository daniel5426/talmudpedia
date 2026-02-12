#!/usr/bin/env bash
set -euo pipefail
exec /Library/Frameworks/Python.framework/Versions/3.12/bin/moto_server -H 127.0.0.1 -p 5001
