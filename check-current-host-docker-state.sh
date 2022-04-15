#! /usr/bin/env bash

function usage() {
    echo "$0 args"
    echo ""
    echo "  The intention of this script is to allow for more sane formatting in each environment for"
    echo "  asking docker-swarm what was running on a host. The current implementation at ATG doesn't"
    echo "  allow us to to easily check which containers are doing what. ATG assumes that each project"
    echo "  will be an individual container. This script grew organically for the need to determine which"
    echo "  container in the environment was doing what"
    echo ""
    echo "  The expected use of the script is to run on each host in production, and pipe all the logs to"
    echo "  a location so that jenkins can record on deployment what the state at the time of deployment is."
    echo "  This also allows us to probe at any given time the current state of the containers in a more"
    echo "  organized way"
    echo ""
}

while [[ $# -gt 0 ]];do case $1 in
    *) usage; exit 0 ;;
esac; shift; done

set -eu
declare -A container_data_lookup

format_datetime() {
    echo $(date --utc --date="${@}" +"%FT%T" 2> /dev/null || echo "")
}

format_unix_timestamp() {
    echo $(date --utc --date="${@}" +"%s" 2> /dev/null || echo 0)
}

all_known_container_ids=$(sudo docker ps -aq)
all_json_data_base64=$(sudo docker inspect '--format={{json .}}' ${all_known_container_ids} | jq -r "@base64")
for container_hashed_json in $(echo -E ${all_json_data_base64}); do
    container_json=$(echo $container_hashed_json | base64 --decode)
    full_name=$(echo -E "${container_json}" | jq -r ".Name")
    trimmed_name=$(echo "$full_name" | cut -d '.' -f 1)
    name_ids=$(echo "${full_name}" | cut -d '.' -f 2-)
    
    if [[ "${trimmed_name}" == "${name_ids}" ]]; then
        name_ids="-"
    fi

    created=$(echo -E "${container_json}" | jq -r ".Created")
    started=$(echo -E "${container_json}" | jq -r ".State.StartedAt")
    finished=$(echo -E "${container_json}" | jq -r ".State.FinishedAt")
    base64_error_message=$(echo -E "${container_json}" | jq -r '.State.Error | @base64')
    
    container_status=$(echo -E ${container_json} | jq -r ".State.Status")
    health_status=$(echo -E "${container_json}" | jq -r '.State.Health.Status')

    if [[ "${health_status}" != "null" ]]; then
        failures=0
        available=0
        exit_codes=$(echo -E "${container_json}" | jq -r '.State.Health.Log[].ExitCode' || echo "")
        for exit_code in ${exit_codes}; do
            if [[ "${exit_code}" -gt 0 ]]; then
                let failures+=1
            fi
            let available+=1
        done
        health_status+=" (${failures}/${available})"
    else
        health_status="-"
    fi

    oomed=$(echo -E "${container_json}" | jq -r ".State.OOMKilled")
    created_secs=$(format_unix_timestamp "${created}")
    started_secs=$(format_unix_timestamp "${started}")
    finished_secs=$(format_unix_timestamp "${finished}")

    t1=0
    t2=0
    uptime_prefix=""
    if [[ "${finished_secs}" -gt 0 ]]; then
        t2=${finished_secs}
        uptime_prefix="ran"
        if [[ "${started_secs}" -gt 0 ]]; then
            t1=${started_secs}
        elif [[ "${created_secs}" -gt 0 ]]; then
            t1=${created_secs}
        fi
    elif [[ "${started_secs}" -gt 0 ]]; then
        t2=$(date +%s)
        uptime_prefix="up" 
        t1=${started_secs}
    elif [[ "${created_secs}" -gt 0 ]]; then
        t2=$(date +%s)
        uptime_prefix="paused"
        t1=${created_secs}
    fi


    uptime_fmt="-"
    if [[ "${t1}" -gt 0 && "${t2}" -gt 0 ]]; then
        uptime=$(echo "${t2} - ${t1}" | bc)
        if [[ "${uptime}" ]] && [[ "${uptime}" -gt 0 ]]; then
            uptime_str="${uptime} secs"
            if [[ "${uptime}" -gt 86400 ]]; then
                uptime_str="$(echo "scale=1; ${uptime} / 86400.0" | bc) days"
            elif [[ "${uptime}" -gt 3600 ]]; then
                uptime_str="$(echo "scale=1; ${uptime} / 3600.0" | bc) hrs"
            elif [[ "${uptime}" -gt 60 ]]; then
                uptime_str="$(echo "scale=1; ${uptime} / 60.0" | bc) mins"
            fi
            uptime_fmt="${uptime_prefix} ${uptime_str}"
        fi
    fi


    created_ts="-"
    if [[ "${created_secs}" -gt 0 ]]; then
        created_ts=$(format_datetime "${created}")
    fi
    started_ts="-"
    if [[ "${started_secs}" -gt 0 ]]; then
        started_ts=$(format_datetime "${started}")
    fi
    finished_ts="-"
    if [[ "${finished_secs}" -gt 0 ]]; then
        finished_ts=$(format_datetime "${finished}")
    fi


    exit_code=$(echo -E ${container_json} | jq -r ".State.ExitCode")
    fields="${name_ids},${container_status},${exit_code},${uptime_fmt}"
    fields+=",${health_status},${oomed},${created_ts},${started_ts},${finished_ts}"
    container_data_lookup[${trimmed_name}]+="${fields}|"
done

records_str=""
error_messages=""
for key in "${!container_data_lookup[@]}"; do
    value=${container_data_lookup[$key]}
    IFS=$'\n'
    for line in $(echo $value | tr '|' '\n' | sort -bir --field-separator=',' --key=7); do
        if [[ ! -z "${line}" ]]; then
            records_str+="$key,$line\n"
        fi
    done
done
records_str="name,ids,status,exit_code,uptime,healthcheck (fails),OOM,created,start,last\n$records_str"
echo -e "${records_str}" | column -t -s ,

