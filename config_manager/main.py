from dataclasses import asdict
from datetime import datetime
import multiprocessing as mp
import logging.config
import logging as log
import time
import sys
import os
import socket
import io
import requests
import tensorflow as tf

from model_manager_lib.tfserving import TensorflowServingConfig

tf.config.threading.set_inter_op_parallelism_threads(1)
tf.config.threading.set_intra_op_parallelism_threads(1)

from fcache.cache import FileCache
import uvicorn
import uvloop

import fastapi
import statsd

import model_manager_lib

from model_manager_lib import tfserving, local_filesystem, PriorityEndpoint, RecordKey

logging.config.fileConfig("logging.cfg", disable_existing_loggers=False)


HOSTNAME = socket.gethostname()
HTTP_HOST = "0.0.0.0"
HTTP_PORT = os.environ["HTTP_PORT"]
HTTP_WORKERS = os.environ["HTTP_WORKERS"]
MASTER_URL = os.environ["MASTER_URL"]
ENVIRONMENT = os.environ["ENVIRONMENT"]
assert ENVIRONMENT in ["production", "integ", "staging", "test"]
LOCAL_MODEL_DIRECTORY = os.environ["LOCAL_MODEL_DIRECTORY"]
TENSORFLOW_SERVING_CONFIG_FILE = os.environ["TENSORFLOW_SERVING_CONFIG_FILE"]
TENSORFLOW_SERVING_GRPC_TARGET = os.environ["TENSORFLOW_SERVING_GRPC_TARGET"]
CONFIG_UPDATE_FREQUENCY = int(os.environ["CONFIG_UPDATE_FREQUENCY"])
MAX_CONFIG_UPDATE_WAIT_TIME = CONFIG_UPDATE_FREQUENCY * 4

server_start_time = time.time()

app = fastapi.FastAPI()
statsd_client = statsd.StatsClient(host="localhost", port=8125, prefix=f'modelmanager.config.{HOSTNAME}')


config_update_data = FileCache("config_update_data")
local_model_remove_data = FileCache("local_model_remove_data")


@app.get("/")
def root():
    return {
        "server_start_time": server_start_time,
        "server_start_timestamp": datetime.fromtimestamp(server_start_time).isoformat(),
        "uptime": time.time() - server_start_time,
        "local_model_directory": LOCAL_MODEL_DIRECTORY,
        "tensorflow_serving_config_file": TENSORFLOW_SERVING_CONFIG_FILE,
        "tensorflow_serving_grpc_target": TENSORFLOW_SERVING_GRPC_TARGET,
        "config_update_frequency": CONFIG_UPDATE_FREQUENCY,
    }


def register():
    target = f"{HOSTNAME}:{HTTP_PORT}"
    response = requests.post(
        f"{MASTER_URL}/register",
        timeout=1,
        json={"node_type": "config_manager", "target": target},
    )
    response.raise_for_status()
    data = response.json()
    assert target in data, f"failed to register target={target} for unknown reason"
    return {"registration_time": data[target]}


@app.get("/health")
@app.get("/health/test")
@app.get("/health/check")
def health_check():
    return {
        "status": "green",
        "data": root(),
        "registration": register(),
        "config_update": health_check_config_update(),
        "local_model_remove": health_check_local_model_remove(),
    }


def health_check_config_update() -> dict:
    if CONFIG_UPDATE_FREQUENCY <= 0:
        return "no config update setup"
    run_time = config_update_data.get("run_time", 0)
    took = config_update_data.get("took", 0)
    records_added = config_update_data.get("records_added", [])

    last_run = time.time() - run_time
    log.info(f"time since last run: {last_run}")
    if last_run > MAX_CONFIG_UPDATE_WAIT_TIME:
        log.error(f"Last run was more then {MAX_CONFIG_UPDATE_WAIT_TIME} seconds!")
        raise fastapi.exceptions.HTTPException(
            status_code=500,
            detail=f"Failed to find valid run in last {MAX_CONFIG_UPDATE_WAIT_TIME} seconds",
        )

    return {
        "time_since_last": last_run,
        "maximum_wait_time": MAX_CONFIG_UPDATE_WAIT_TIME,
        "last_run_time": run_time,
        "last_run_timestamp": datetime.fromtimestamp(run_time).isoformat(),
        "took": took,
        "records_added": records_added,
    }


def health_check_local_model_remove() -> dict:
    if CONFIG_UPDATE_FREQUENCY <= 0:
        return "no automated model removal setup"
    run_time = config_update_data.get("run_time", 0)
    took = config_update_data.get("took", 0)
    models_removed = config_update_data.get("models_removed", [])

    last_run = time.time() - run_time
    log.info(f"time since last run: {last_run}")
    if last_run > MAX_CONFIG_UPDATE_WAIT_TIME:
        log.error(f"Last run was more then {MAX_CONFIG_UPDATE_WAIT_TIME} seconds!")
        raise fastapi.exceptions.HTTPException(
            status_code=500,
            detail=f"Failed to find valid run in last {MAX_CONFIG_UPDATE_WAIT_TIME} seconds",
        )

    return {
        "time_since_last": last_run,
        "maximum_wait_time": MAX_CONFIG_UPDATE_WAIT_TIME,
        "last_run_time": run_time,
        "last_run_timestamp": datetime.fromtimestamp(run_time).isoformat(),
        "took": took,
        "models_removed": models_removed,
    }


@app.get("/tensorflow_serving/config")
def get_tensorflow_serving_config():
    config = tfserving.load_config(TENSORFLOW_SERVING_CONFIG_FILE)
    return fastapi.responses.PlainTextResponse(str(config.proto))


@app.get("/tensorflow_serving/all")
def get_tensorflow_serving_models():
    config = tfserving.load_config(TENSORFLOW_SERVING_CONFIG_FILE)
    known_models = tfserving.get_known_tensorflow_serving_models(
        TENSORFLOW_SERVING_GRPC_TARGET, config
    )

    return model_manager_lib.records_dict_to_jsonable(known_models)


@app.get("/local/all")
def get_local_models():
    all_known_local_models = local_filesystem.get_known_local_models(
        LOCAL_MODEL_DIRECTORY
    )
    return model_manager_lib.records_dict_to_jsonable(all_known_local_models)


@app.get("/local/current")
def get_current_local_models():
    current_local_records_dict = local_filesystem.get_current_local_models(
        model_directory=LOCAL_MODEL_DIRECTORY
    )
    return model_manager_lib.records_dict_to_jsonable(current_local_records_dict)


@app.post("/update_tfserving_config_from_local_filesystem")
def manually_update_tfserving_config_from_local_filesystem():
    logging_output, status_code = run_fn_with_logging_wrapped(
        pull_local_model_changes_into_config,
    )
    return fastapi.responses.PlainTextResponse(logging_output, status_code=status_code)


@app.post("/clear_out_of_date_local_models")
def manually_remove_local_models_that_are_now_invalid():
    logging_output, status_code = run_fn_with_logging_wrapped(
        remove_local_models_that_are_out_of_date,
    )
    return fastapi.responses.PlainTextResponse(logging_output, status_code=status_code)


@app.delete("/models/{framework}/{name}")
def delete_model_bykey(framework: str, name: str):
    logging_output, status_code = run_fn_with_logging_wrapped(
        remove_local_models_by_key,
        log_level=logging.DEBUG,
        framework=framework,
        name=name,
    )

    return fastapi.responses.PlainTextResponse(logging_output, status_code=status_code)


@app.delete("/priority")
def remove_priority(endpoint: PriorityEndpoint):
    logging_output, status_code = run_fn_with_logging_wrapped(
        remove_local_priority_model,
        log_level=logging.DEBUG,
        framework=endpoint.framework,
        name=endpoint.name,
    )

    return fastapi.responses.PlainTextResponse(logging_output, status_code=status_code)


def run_fn_with_logging_wrapped(fn: callable, log_level=logging.DEBUG, **kwargs) -> str:
    base_logger = logging.getLogger()
    current_level = base_logger.getEffectiveLevel()
    log_stream = io.StringIO()
    status_code = 200
    log_handler = logging.StreamHandler(log_stream)
    log_handler.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))
    base_logger.addHandler(log_handler)
    base_logger.setLevel(log_level)
    try:
        fn(**kwargs)
    except Exception as err:
        log.exception(err)
        status_code = 500
    finally:
        base_logger.removeHandler(log_handler)
        base_logger.setLevel(current_level)
        return log_stream.getvalue(), status_code


def pull_local_model_changes_into_config():
    start_time = time.time()

    log.info("initiating pull of known models")
    local_models = local_filesystem.get_current_local_models(
        model_directory=LOCAL_MODEL_DIRECTORY,
        framework="tensorflow",
    )
    log.info(f"found known models = {local_models}")
    statsd_client.gauge("locals", len(local_models))
    config = tfserving.load_config(TENSORFLOW_SERVING_CONFIG_FILE)
    log.info(f"loading config: {config.proto}")

    known_tensorflow_serving_models = tfserving.get_known_tensorflow_serving_models(
        grpc_target=TENSORFLOW_SERVING_GRPC_TARGET, tensorflow_serving_config=config
    )

    def need_to_add(record_key, record):
        return (record_key.name not in config.known_model_names) or (
            record_key in known_tensorflow_serving_models
            and len(known_tensorflow_serving_models[record_key]) > 0
            and max(
                rec.is_priority for rec in known_tensorflow_serving_models[record_key]
            )
            != record.is_priority
        )

    records_to_add = {
        record_key: record
        for record_key, record in local_models.items()
        if need_to_add(record_key, record)
    }
    log.info(f"found records to add: {records_to_add}")
    statsd_client.gauge("records_to_add", len(records_to_add))  # can be indication of tfserving container failing

    for record_key, record in records_to_add.items():
        log.info(
            f"unknown model_name={record_key.name}. Adding to tensorflow serving config!"
        )
        config = tfserving.add_model(
            tensorflow_serving_config=config,
            record=record,
            local_path=record.local_model_path,
        )
        log.info(f"new tensorflow serving config: {config}")

    log.info(f"ending tensorflow serving config: {config}")
    log.info("finished pulling local models into the config.")

    config_update_data["run_time"] = start_time
    config_update_data["took"] = time.time() - start_time
    config_update_data["records_added"] = [asdict(r) for r in records_to_add.keys()]
    config_update_data.sync()


def remove_local_priority_model(framework: str, name: str):
    # start_time = time.time()
    log.info("initiating remove_local_priroty_model")
    key = RecordKey(framework=framework, name=name)
    config = tfserving.load_config(TENSORFLOW_SERVING_CONFIG_FILE)
    log.info(f"initial config = {config}")
    if name in config.model_config_lookup:
        all_current_tfserving_models = tfserving.get_current_tensorflow_serving_models(
            grpc_target=TENSORFLOW_SERVING_GRPC_TARGET, tensorflow_serving_config=config
        )
        if (
            name in all_current_tfserving_models
            and all_current_tfserving_models[name].is_priority
        ):
            tfserving.remove_model(config, key)

    local_filesystem.delete_local_priority_record(
        local_model_directory=LOCAL_MODEL_DIRECTORY, key=key
    )
    # add the model back
    locals = local_filesystem.get_current_local_models(
        model_directory=LOCAL_MODEL_DIRECTORY,
        framework="tensorflow",
    )
    config = tfserving.add_model(
        tensorflow_serving_config=config,
        record=locals[key],
        local_path=locals[key].local_model_path,
    )
    log.info(f"new tensorflow serving config: {config}")


def remove_local_models_that_are_out_of_date():
    start_time = time.time()

    log.info("initiating removal of out of date local records")

    config = tfserving.load_config(TENSORFLOW_SERVING_CONFIG_FILE)
    log.info(f"initial config = {config}")

    all_known_tfserving_models = tfserving.get_known_tensorflow_serving_models(
        grpc_target=TENSORFLOW_SERVING_GRPC_TARGET, tensorflow_serving_config=config
    )
    log.info(f"known tensorflow serving models = {all_known_tfserving_models}")
    # known models are counted during adding

    all_local_records = local_filesystem.get_known_local_models(
        model_directory=LOCAL_MODEL_DIRECTORY, framework="tensorflow"
    )
    log.info(f"known local records = {all_local_records}")

    def record_out_of_date(local_record: local_filesystem.LocalRecord):
        if local_record.key not in all_known_tfserving_models:
            log.info(
                f"local record not yet loaded in config! local_record={local_record} config="
            )
            return False

        known_serving_versions = {
            tfserving_record.version
            for tfserving_record in all_known_tfserving_models[local_record.key]
            if tfserving_record.status
            == tfserving.TensorflowServingModelStatus.AVAILABLE
        }
        if len(known_serving_versions) == 0:
            log.info(
                f"local record not yet served/available in tensorflow! local_record={local_record}"
            )
            return False

        log.info(
            f"found known serving record_key={local_record.key} versions={known_serving_versions}"
        )
        if local_record.version < max(known_serving_versions):
            return True

    records_to_remove = [
        local_record
        for record_key, local_records in all_local_records.items()
        for local_record in local_records
        if record_out_of_date(local_record)
    ]
    log.info(f"found records to remove: {records_to_remove}")
    statsd_client.gauge('records_to_remove', len(records_to_remove))

    exceptions = []
    for record in records_to_remove:
        log.warning(f"removing record {record}")
        try:
            local_filesystem.remove_record(record)
        except Exception as err:
            log.exception(err)
            exceptions.append(err)

    for exception in exceptions:
        raise exception

    local_model_remove_data["run_time"] = start_time
    local_model_remove_data["took"] = time.time() - start_time
    local_model_remove_data["models_removed"] = [asdict(r) for r in records_to_remove]
    local_model_remove_data.sync()


def remove_local_models_by_key(framework: str, name: str):
    log.info(f"call remove_local_models_by_key framework={framework} name={name}")

    config = tfserving.load_config(TENSORFLOW_SERVING_CONFIG_FILE)
    log.info(f"initial config = {config}")

    all_known_tfserving_models = tfserving.get_known_tensorflow_serving_models(
        grpc_target=TENSORFLOW_SERVING_GRPC_TARGET, tensorflow_serving_config=config
    )
    log.info(f"known tensorflow serving models = {all_known_tfserving_models}")
    all_local_records_bykey = local_filesystem.get_known_local_models(
        model_directory=LOCAL_MODEL_DIRECTORY, framework=framework, name=name
    )
    log.info(f"known local records = {all_local_records_bykey}")

    for record_key in all_known_tfserving_models:
        if record_key.name == name and record_key.framework == framework:
            log.info(f"remove record_key {record_key} from tfserving config")
            tfserving.remove_model(config, record_key)

    for record_key, records in all_local_records_bykey.items():
        for record in records:
            log.info(f"removing record from local file {record}")
            local_filesystem.remove_record(record)


def run_update_config_and_remove_out_of_date_loop():
    log.info("starting main background loop")
    while True:
        with statsd_client.timer("loop_time"):
            try:
                log.info("starting config update")
                pull_local_model_changes_into_config()
                log.info("finished config update")
            except Exception as err:
                log.exception(
                    msg="unhandled exception during config update",
                    exc_info=err,
                )
                statsd_client.incr('exceptions')

            try:
                log.info("starting out of date model removal")
                remove_local_models_that_are_out_of_date()
                log.info("finished out of date model removal")
            except Exception as err:
                log.exception(
                    msg="unhandled exception during local model removal",
                    exc_info=err,
                )
                statsd_client.incr('exceptions')

        time.sleep(CONFIG_UPDATE_FREQUENCY)


if __name__ == "__main__":
    statsd_client.incr("startup")
    processes = []
    if CONFIG_UPDATE_FREQUENCY > 0:
        processes.append(
            mp.Process(
                target=run_update_config_and_remove_out_of_date_loop,
                name="config_update_loop",
            )
        )
    for p in processes:
        log.warning(f"starting process: {p}")
        p.start()

    try:
        log.warning(f"starting webserver at {HOSTNAME}:{HTTP_PORT}")
        uvicorn.run(
            "main:app",
            loop="uvloop",
            access_log=ENVIRONMENT == "test",
            log_config="logging.cfg",
            debug=ENVIRONMENT == "test",
            reload=ENVIRONMENT == "test",
            port=int(HTTP_PORT),
            use_colors=False,
            host=HTTP_HOST,
            workers=int(HTTP_WORKERS),
        )
    except Exception as err:
        log.exception(
            "unhandled exception thrown during uvicorn server run", exc_info=err
        )
    finally:
        for p in processes:
            log.warning(f"terminating process: {p}")
            p.terminate()
        log.critical("webserver stopped for some reason!")
        statsd_client.incr('shutdown')
