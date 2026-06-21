#!/bin/bash
if [ -f "./.venv/bin/python" ]; then
    ./.venv/bin/python -m agent.main "$@"
elif command -v python3 &>/dev/null; then
    python3 -m agent.main "$@"
else
    python -m agent.main "$@"
fi
