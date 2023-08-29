#!/bin/bash
set -euxo pipefail

# Clean leftovers from previous builds
rm -R dist/*/ dist/*-record dist/*-distinfo dist/*.tar.gz 2> /dev/null || true

if [ -f /etc/redhat-release ]; then
    sudo dnf install -y libcurl-devel krb5-devel python3-jsonschema python3-devel rpm-build
    # Only Fedora has packit as rpm available, on others we install it using pip
    if grep Fedora /etc/redhat-release; then
        sudo dnf install -y packit python3-setuptools_scm+toml python3-subprocess-tee
    else
        type packit 2>/dev/null || sudo pip3 install packitos
    fi
else
    echo 'FATAL: This can be run only on rpm based operating systems at this moment.' >&2
    exit 1
fi

packit build locally
