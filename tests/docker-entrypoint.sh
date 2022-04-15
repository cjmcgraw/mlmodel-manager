#! /usr/bin/env bash

set -eu
service_account_file="$CLOUDSDK_CONFIG/service_account.json"
if [[ -f "${service_account_file}" ]]; then
    echo "noticed service account file. Activating it so that jenkins can work properly"
    gcloud auth activate-service-account --key-file "${service_account_file}"
fi

echo $(whoami)

python -Wignore -m pytest --exitfirst "$@" 
