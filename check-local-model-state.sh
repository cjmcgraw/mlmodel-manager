#! /usr/bin/env bash
local_models_directory=".container_shared_data/local_saved_models"
assert_owner_username=""
assert_owner_userid=""
assert_models_are_valid=""
allow_missing=""

function usage() {
    echo "$0 args"
    echo ""
    echo "  The main purpose of this script is to ensure that the host being"
    echo "  deployed to has the correct configuration for local_saved_models directories"
    echo "  this includes ownerhsip, and expected data checks."
    echo ""
    echo "  The intention here is that during deployment this script will run, and it will allow"
    echo "  inspection and asserting of the state on the host machine. This will enable use to do"
    echo "  manual intervention to handle bad potential states"
    echo ""
    echo "optional arugments:"
    echo "  --local-models-directory    the directory to search for local saved models"
    echo "  --assert-owner-username     Owner username to use for permission check (default='', disabled)"
    echo "  --assert-owner-userid       Owner to userid to use for permission check (default='', disabled)"
    echo "  --assert-models-are-valid   flag, to check and exit if the models are invalid (default=disabled)"
    echo "  --allow-missing             flag, to allow missing local models directory"
    echo ""
}

while [[ $# -gt 0 ]];do case $1 in
    --local-models-directory) local_models_directory="$(echo "$2" | sed 's,/$,,')"; shift;;
    --assert-models-are-valid) assert_models_are_valid="on";;
    --assert-owner-username) assert_owner_username="${2,,}"; shift;;
    --assert-owner-userid) assert_owner_userid="${2,,}"; shift;;
    --allow-missing) allow_missing="true";;
    *) usage; exit 0 ;;
esac; shift; done

set -eu
if [[ -z "${local_models_directory}" ]]; then
    echo "unexpected empty argument: --local-models-directory" >&2
    usage
    exit 1
fi

if [[ ! -d "${local_models_directory}" ]]; then
    echo "Failed to find local models directory at:" >&2
    echo "${local_models_directory}" >&2
    echo "" >&2
    echo "Please ensure the local models directory exists on the host" >&2
    echo "If this is local development, ensure you've run" >&2
    echo "" >&2
    echo "  docker-compose up -d" >&2
    echo "" >&2
    if [[ "${allow_missing}" ]]; then
        echo "allowing missing local models directory"
        exit 0
    else
        echo "failing with missing local models directory"
        exit 1
    fi
fi


if [[ "${assert_owner_username}" ]]; then
    echo "assert: username=${assert_owner_username} owns directory ${local_models_directory}"
    directory_owner_username=$(stat -c "%U" "${local_models_directory}")
    if [[ "${assert_owner_username}" != "${directory_owner_username,,}" ]]; then
        echo "failed assert of ownership!" >&2
        echo "" >&2
        echo "path: ${local_models_directory}" >&2
        echo "" >&2
        echo "expected owner username: ${assert_owner_username}" >&2
        echo "actual owner username: ${directory_owner_username}" >&2
        echo "" >&2
        echo "ownership for local models directory was not setup correctly" >&2
        echo "on this host. Please setup the owner of the directories to be" >&2
        echo "${directory_owner_username}" >&2
        echo "" >&2
        exit 2
    fi
    echo "assert: username check passed"
    echo ""
fi

if [[ "${assert_owner_userid}" ]]; then
    echo "assert: userid=${assert_owner_userid} is the owner of ${local_models_directory}"
    directory_owner_userid=$(stat -c "%u" "${local_models_directory}")
    if [[ "${assert_owner_userid}" != "${directory_owner_userid,,}" ]]; then
        echo "failed on ownership check!" >&2
        echo "" >&2
        echo "path: ${local_models_path}" >&2
        echo "" >&2
        echo "expected owner userid: ${assert_owner_userid}" >&2
        echo "actual owner userid: ${directory_owner_userid}" >&2
        echo "" >&2
        echo "ownership for local models directroy was not setup correctly" >&2
        echo "on this host. Please setup the owner of the path to be" >&2
        echo "${assert_owner_userid}" >&2
        exit 5
    fi
    echo "assert: userid check passed"
    echo ""
fi

for path in $(find "${local_models_directory}" -maxdepth 3 -mindepth 3 -type d); do
    echo $path

    if [[ "${path}" ]]; then
        ls -lRh "${path}" | while read -r line; do
            echo " |    $line"
        done

        if [[ "${assert_owner_username}" ]]; then
            path_owner_username=$(stat -c "%U" "${path}")
            if [[ "${assert_owner_username}" != "${path_owner_username,,}" ]]; then
                echo "failed assert of ownership!" >&2
                echo "" >&2
                echo "path: ${path}" >&2
                echo "" >&2
                echo "expected owner username: ${assert_owner_username}" >&2
                echo "actual owner username: ${path_owner_username}" >&2
                echo "" >&2
                echo "ownership for model was not setup/created correctly" >&2
                echo "on this host. Please investigate the remote_model_puller and" >&2
                echo "consider clearing out this state to be rebuilt" >&2
                echo "" >&2
                exit 2
            fi
        fi

        if [[ "${assert_owner_userid}" ]]; then
            path_owner_userid=$(stat -c "%u" "${path}")
            if [[ "${assert_owner_userid}" != "${path_owner_userid,,}" ]]; then
                echo "failed on ownership check!" >&2
                echo "" >&2
                echo "path: ${path}" >&2
                echo "" >&2
                echo "expected owner userid: ${assert_owner_userid}" >&2
                echo "actual owner userid: ${path_owner_userid}" >&2
                echo "" >&2
                echo "ownership for model was not setup/created correctly" >&2
                echo "on this host. Please investigate the remote_model_puller and" >&2
                echo "consider clearing out this state to be rebuilt" >&2
                echo "" >&2
                exit 5
            fi
        fi

        if [[ "${assert_models_are_valid}" ]]; then
            version=$(basename "${path}")
            name=$(basename $(dirname "${path}"))
            framework=$(basename $(dirname $(dirname "${path}")))

            if [[ ! "${framework}" == "tensorflow" ]]; then
                echo "current only support tensorflow models!" >&2
                echo "unexpected framework in path" >&2
                echo "" >&2
                echo "path: ${path}" >&2
                echo "actual framework: ${framework}" >&2
                echo "" >&2
                exit 10
            fi

            if [[ ! "${version}" =~ ^[0-9]+$ ]]; then
                echo "expected the directory format of version to be a number!" >&2
                echo "" >&2
                echo "path: ${path}" >&2
                echo "actual version: ${version}" >&2
                exit 10
            fi

            if [[ ! -f "${path}/saved_model.pb" ]]; then
                echo "missing saved_model.pb file in the directory" >&2
                echo "seems like a model may be in a bad state" >&2
                echo "" >&2
                echo "path: ${path}" >&2
                echo "expected file: ${path}/saved_model.pb" >&2
                echo "" >&2
                exit 10
            fi

            if [[ ! -f "${path}/variables/variables.index" ]]; then
                echo "missing variables file in the directory" >&2
                echo "seems like a model may be in a bad state" >&2
                echo "" >&2
                echo "path: ${path}" >&2
                echo "expected file: ${path}/variables/variables.index" >&2
                echo "" >&2
                exit 10
            fi
        fi
    fi
    echo "----------------------------------------------------------------------------"
    echo ""
done
