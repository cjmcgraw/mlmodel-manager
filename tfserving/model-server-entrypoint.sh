#!/usr/bin/env bash
set -eu

if [[ ! -f "${TENSORFLOW_SERVING_CONFIG_FILE}" ]]; then
    echo "Missing tensorflow serving config file! Generating one!"
    mkdir -p $(dirname "${TENSORFLOW_SERVING_CONFIG_FILE}")
    echo -en "model_config_list {\n\n}\n" > "${TENSORFLOW_SERVING_CONFIG_FILE}"
fi

tensorflow_model_server \
    --port=${TENSORFLOW_SERVING_GRPC_PORT}  \
    --rest_api_port=${TENSORFLOW_SERVING_HTTP_PORT} \
    --model_config_file=${TENSORFLOW_SERVING_CONFIG_FILE} \
    --model_config_file_poll_wait_seconds=${MODEL_CONFIG_FILE_POLL_WAIT} \
    --file_system_poll_wait_seconds=${FILE_SYSTEM_POLL_WAIT} \
    --monitoring_config_file=monitoring.config \
    --enable_model_warmup \
    --num_load_threads=${NUM_LOAD_THREADS} \
    --num_unload_threads=${NUM_UNLOAD_THREADS} \
    --remove_unused_fields_from_bundle_metagraph \
    --xla_cpu_compilation_enabled \
    --tensorflow_session_parallelism=${TENSORFLOW_SESSION_PARALLELISM} \
    --grpc_channel_arguments=grpc.enable_deadline_checking=1
