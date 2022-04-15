#! /usr/bin/env python
import logging
import pathlib
import time
import sys
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
from model_manager_lib import tfserving, local_filesystem

logging.basicConfig(
    level=logging.DEBUG,
    stream=sys.stdout,
)


log = logging.getLogger(__file__)

LOCAL_MODEL_DIRECTORY: pathlib.Path = pathlib.Path(os.environ['LOCAL_MODEL_DIRECTORY'])
TENSORFLOW_SERVING_CONFIG_FILE: pathlib.Path = pathlib.Path(os.environ['TENSORFLOW_SERVING_CONFIG_FILE'])
TENSORFLOW_SERVING_GRPC_TARGET: str = f"localhost:{os.environ['TENSORFLOW_SERVING_GRPC_PORT']}"
MODEL_CONFIG_FILE_POLL_WAIT: int = int(os.environ['MODEL_CONFIG_FILE_POLL_WAIT'])
FILE_SYSTEM_POLL_WAIT: int = int(os.environ['FILE_SYSTEM_POLL_WAIT'])
LAST_HEALTH_CHECK_STATE_FILE: str = "last_health_check_state.json"

MAXIMUM_WAIT_TIME_FOR_UPDATE: int = int(
    3 * MODEL_CONFIG_FILE_POLL_WAIT +
    3 * FILE_SYSTEM_POLL_WAIT +
    # add 10 minutes on top of three times both the poll waits
    15 * 60
)

if __name__ == "__main__":
    start_time = time.time()

    def get_seconds_since_creation(m: local_filesystem.LocalRecord) -> int:
        return int(start_time - m.local_model_path.stat().st_ctime)

    log.info("Starting healthcheck script")

    current_known_local_models = local_filesystem.get_current_local_models(
        model_directory=LOCAL_MODEL_DIRECTORY,
        framework="tensorflow",
    )
    log.info(f"found current known local models: {current_known_local_models}")

    config = tfserving.load_config(
        tensorflow_serving_config_file=TENSORFLOW_SERVING_CONFIG_FILE
    )

    current_known_tfserving_models = tfserving.get_known_tensorflow_serving_models(
        grpc_target=TENSORFLOW_SERVING_GRPC_TARGET,
        tensorflow_serving_config=config
    )

    local_record_available_since = {
        record_key: get_seconds_since_creation(local_model)
        for record_key, local_model in current_known_local_models.items()
    }

    log.info(f"getting time since all local record versions were created")

    models_that_have_failed_to_load_for_unknown_reason = []

    for record_key, tfserving_models in current_known_tfserving_models.items():
        log.info(f"checking record_key={record_key} models={tfserving_models}")
        if len(tfserving_models) > 0:
            highest_known_version = max({m.version for m in tfserving_models})
            if record_key in current_known_local_models:
                current_local = current_known_local_models[record_key]
                log.info(f"found associated local record: {current_local}")

                if current_local.version > highest_known_version:
                    log.info("local record is a lower version than expected!")

                    active_time = local_record_available_since.get(record_key, 0)
                    log.info(f"local record has been active for {active_time}s")
                    if local_record_available_since[record_key] > MAXIMUM_WAIT_TIME_FOR_UPDATE:
                        log.error(
                            "record has been active long enough to be deployed. "
                            f"Maximum wait time {MAXIMUM_WAIT_TIME_FOR_UPDATE}s"
                        )
                        models_that_have_failed_to_load_for_unknown_reason.append(current_local)
                    else:
                        log.info("record has not been active enough to have been deployed. Will check later")
                else:
                    log.info("record is up to date!")

    log.info(
        "number of models that have failed to "
        f"load = {models_that_have_failed_to_load_for_unknown_reason}"
    )

    if len(models_that_have_failed_to_load_for_unknown_reason) == 0:
        log.info("healthcheck passed!")
    else:
        log.info("healthcheck failed!")
    sys.exit(len(models_that_have_failed_to_load_for_unknown_reason))
