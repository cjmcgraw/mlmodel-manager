#! /usr/bin/env bash
local_config_path=".container_shared_data/serving_config/models.config"
assert_owner_username=""
assert_owner_userid=""
allow_missing=''

function usage() {
    echo "$0 args"
    echo ""
    echo "  The main purpose of this script is to ensure that the host being"
    echo "  deployed to has the correct configuration for the local_config_path"
    echo "  provided."
    echo ""
    echo "  I anticipate this script will be used during deployment to check that the"
    echo "  associated files have the correct configuration, username, userid and are"
    echo "  accessible. With the added benefit of also printing out the configuration"
    echo "  so that way we have a log at deployment time of what the deployment originally"
    echo "  was. Making it easier for us to revert and report in each environment"
    echo ""
    echo "optional arguments:"
    echo "  --local-config-path         the path to the local configuration file"
    echo "  --assert-owner-username     Owner username to use for permission check (default='', disabled)"
    echo "  --assert-owner-userid       Owner to userid to use for permission check (default='', disabled)"
    echo "  --allow-missing             If the config file is allowed to be missing in the environment (default disabled)"
    echo ""
}

while [[ $# -gt 0 ]];do case $1 in
    --local-config-path) local_config_path="$(echo "${2}" | sed 's,/$,,')"; shift;;
    --assert-owner-username) assert_owner_username="${2,,}"; shift;;
    --assert-owner-userid) assert_owner_userid="${2,,}"; shift;;
    --allow-missing) allow_missing="true"; shift;;
    --help) usage; exit 0 ;;
esac; shift; done

set -eu
if [[ -z "${local_config_path}" ]]; then
    echo "missing required argument: --local-config-path" >&2
    echo "" >&2
    usage
    exit 1
fi

if [[ ! -f "${local_config_path}" ]]; then
    echo "cannot find configuration file!" >&2
    echo "" >&2
    echo "no file found at:" >&2
    echo "${local_config_path}" >&2
    echo "" >&2
    echo "please confirm that the config path is correct!" >&2
    echo "" >&2
    echo "if this is local development, ensure you've run" >&2
    echo "" >&2
    echo "  docker-compose up -d" >&2
    echo "" >&2

    if [[ "${allow_missing}" ]]; then
        echo "allow missing enabled!"
        exit 0
    else
        echo "failed with missing models.config"
        exit 1
    fi
fi

if [[ "${assert_owner_username}" ]]; then
    echo "assert: username=${assert_owner_username} is the owner of ${local_config_path}"
    config_owner_username=$(stat -c "%U" "${local_config_path}")
    if [[ "${assert_owner_username}" != "${config_owner_username,,}" ]]; then
        echo "failed on ownership check!" >&2
        echo "" >&2
        echo "path: ${local_config_path}" >&2
        echo "" >&2
        echo "expected owner username: ${assert_owner_username}" >&2
        echo "actual owner username: ${config_owner_username}" >&2
        echo "" >&2
        echo "ownership for serving config was not setup correctly" >&2
        echo "on this host. Please setup the owner of the path to be" >&2
        echo "${assert_owner_username}" >&2
        exit 5
    fi
    echo "assert: username check passed"
    echo ""
fi

if [[ "${assert_owner_userid}" ]]; then
    echo "assert: userid=${assert_owner_userid} is the owner of ${local_config_path}"
    config_owner_userid=$(stat -c "%u" "${local_config_path}")
    if [[ "${assert_owner_userid}" != "${config_owner_userid,,}" ]]; then
        echo "failed on ownership check!" >&2
        echo "" >&2
        echo "path: ${local_config_path}" >&2
        echo "" >&2
        echo "expected owner userid: ${assert_owner_userid}" >&2
        echo "actual owner userid: ${config_owner_userid}" >&2
        echo "" >&2
        echo "ownership for serving config was not setup correctly" >&2
        echo "on this host. Please setup the owner of the path to be" >&2
        echo "${assert_owner_userid}" >&2
        exit 5
    fi
    echo "assert: userid check passed"
    echo ""
fi

cat "${local_config_path}"
