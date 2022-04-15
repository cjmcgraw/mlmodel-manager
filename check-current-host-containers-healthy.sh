#! /usr/bin/env bash
set -eu

running_containers=$(sudo docker ps --format '{{.Names}}')

has_config_manager_active=$(echo -e "${running_containers}" | grep 'mlmodelmanager_config_manager' | head -n 1 || echo "")
has_remote_model_puller_active=$(echo -e "${running_containers}" | grep 'mlmodelmanager_remote_model_puller' | head -n 1 || echo "")
has_tfserving_active=$(echo -e "${running_containers}" | grep "mlmodelmanager_tfserving" | head -n 1  || echo "")
has_master_active=$(echo -e "${running_containers}" | grep "mlmodelmanager_master" | head -n 1 || echo "")

if [[ "${has_config_manager_active}" ]]; then
    echo "found active config manager container"
    echo "attempting healthcheck"
    results=$(curl --silent --fail --connect-timeout 10 --max-time 10 localhost:8001/health)
    echo $results | jq .
    echo "passed"
fi

if [[ "${has_remote_model_puller_active}" ]]; then
    echo "found active remote model puller container"
    echo "attempting healthcheck"
    results=$(curl --silent --fail --connect-timeout 10 --max-time 10 localhost:8002/health)
    echo $results | jq .
    echo "passed"
fi

if [[ "${has_master_active}" ]]; then
    echo "found active master container"
    echo "attempting healthcheck"
    results=$(sudo docker exec "${has_master_active}" curl --silent --fail --connect-timeout 10 --max-time 10 localhost:8000/health)
    echo $results | jq .
    echo "passed"
fi

if [[ "${has_tfserving_active}" ]]; then
    echo "found active tfserving container"
    echo "attempting healthcheck"
    sudo docker exec "${has_tfserving_active}" python3.8 /app/healthcheck.py
    echo "passed"
fi

