#!/usr/bin/env bash
set -eu
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

for PROJECT in ansible-lint molecule; do
  echo "Running tests for $PROJECT"
  if [[ -d "${TOX_ENV_DIR}/${PROJECT}/.git" ]]; then
    git -C "${TOX_ENV_DIR}/${PROJECT}" pull
  else
    mkdir -p "${TOX_ENV_DIR}/${PROJECT}"
    git clone --recursive https://github.com/ansible/${PROJECT} "${TOX_ENV_DIR}/${PROJECT}"
  fi
  pushd "${TOX_ENV_DIR}/${PROJECT}" > /dev/null
    tox devenv
    source venv/bin/activate
    uv pip install -e "$SCRIPT_DIR/.."
    uv pip freeze | grep "file:"
    pytest
  popd
done
