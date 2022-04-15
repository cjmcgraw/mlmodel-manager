from dataclasses import is_dataclass, asdict
from typing import Dict, Tuple
from uuid import uuid4 as uuid
from datetime import datetime
import multiprocessing as mp
import traceback

import statsd
import uvloop
import uvicorn
import logging.config
import logging as log
import pathlib
import time
import sys
import os
import io

import requests
import socket

from fcache.cache import FileCache

import fastapi

import model_manager_lib
from model_manager_lib import RecordKey, gcs, local_filesystem, PriorityEndpoint
from model_manager_lib.gcs import GcsDownloadException

logging.config.fileConfig("logging.cfg", disable_existing_loggers=False)


def log_exception(*exc_info):
    s = " ".join(traceback.format_exception(*exc_info))
    log.exception(f"unhandled exception occurred: {s}")
    return


sys.excepthook = log_exception

HOSTNAME = socket.gethostname()
HTTP_HOST = "0.0.0.0"
HTTP_PORT = os.environ["HTTP_PORT"]
HTTP_WORKERS = os.environ["HTTP_WORKERS"]
MASTER_URL = os.environ["MASTER_URL"]

ENVIRONMENT = os.environ["ENVIRONMENT"].lower()
assert ENVIRONMENT in ["production", "integ", "staging", "test"]
LOCAL_MODEL_DIRECTORY = pathlib.Path(
    os.environ["LOCAL_MODEL_DIRECTORY"]
).absolute()
TEMPORARY_MODEL_DIRECTORY = pathlib.Path(
    os.environ["TEMPORARY_MODEL_DOWNLOAD_DIRECTORY"]
).absolute()
REMOTE_MODEL_PULL_FREQUENCY = int(os.environ["REMOTE_MODEL_PULL_FREQUENCY"])
LAST_PULL_INFO_FILE = LOCAL_MODEL_DIRECTORY.joinpath("last_pull_info_file.json")
MAXIMUM_WAIT_TIME = REMOTE_MODEL_PULL_FREQUENCY * 10

last_pull_data = FileCache("last_pull_info")

REMOTE_MODEL_DIRECTORY = model_manager_lib.load_remote_model_directory(
    os.environ["REMOTE_MODEL_DIRECTORY"], os.environ["ENVIRONMENT"]
)

__VERSION__ = "0.0.1"

app = fastapi.FastAPI()
start_time = time.time()

statsd_client = statsd.StatsClient(host="localhost", port=8125, prefix=f'modelmanager.puller.{HOSTNAME}')


@app.get("/")
def root():
    return {
        "version": __VERSION__,
        "environment": ENVIRONMENT,
        "msg": "hello, world!",
        "local_model_directory": LOCAL_MODEL_DIRECTORY,
        "remote_model_directory": REMOTE_MODEL_DIRECTORY,
        "remote_model_pull_frequency": REMOTE_MODEL_PULL_FREQUENCY,
        "uptime": f"{round(time.time() - start_time, 2)} seconds",
    }


def register():
    target = f"{HOSTNAME}:{HTTP_PORT}"
    response = requests.post(
        f"{MASTER_URL}/register",
        timeout=1,
        json={
            "node_type": "remote_model_puller",
            "target": target,
        },
    )
    response.raise_for_status()
    data = response.json()
    assert (
        target in data
    ), f"failed to register with {target} for unknown reason"
    return {"registration_time": data[target]}


@app.get("/health")
@app.get("/health/test")
@app.get("/health/check")
def health_test():
    root_data = root()

    pull_data = "no pull configured"
    if MAXIMUM_WAIT_TIME > 0:
        current_time = time.time()
        run_time = last_pull_data.get("run_time", 0)
        took = last_pull_data.get("took", 0)
        remotes_downloaded = last_pull_data.get("remotes_downloaded", [])
        time_since_last_run = current_time - run_time
        if current_time - run_time > MAXIMUM_WAIT_TIME:
            raise fastapi.HTTPException(
                status_code=500,
                detail="failed with excessive maximum time since last pull!",
            )

        pull_data = {
            "time_since_last": time_since_last_run,
            "maximum_pull_wait_time": MAXIMUM_WAIT_TIME,
            "last_run_time": run_time,
            "last_run_timestamp": datetime.fromtimestamp(run_time).isoformat(),
            "took": took,
            "models_downloaded": remotes_downloaded,
        }

    registration_response = register()

    return {
        "status": "green",
        "data": root_data,
        "registration": registration_response,
        "pull_remotes": pull_data,
    }


@app.post("/pull", response_class=fastapi.responses.PlainTextResponse)
def manual_pull():
    status_code = 200
    base_logger = logging.getLogger()
    current_level = base_logger.getEffectiveLevel()
    log_stream = io.StringIO()
    log_handler = logging.StreamHandler(log_stream)
    try:
        log_handler.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))
        base_logger.addHandler(log_handler)
        base_logger.setLevel(logging.DEBUG)
        pull_missing_local_models_from_remote()
        check_priority_bucket_state()
    except Exception as err:
        log.exception(err)
        status_code = 500
    finally:
        base_logger.removeHandler(log_handler)
        base_logger.setLevel(current_level)
        return fastapi.responses.PlainTextResponse(
            log_stream.getvalue(), status_code=status_code
        )


@app.get("/local/all")
def all_local_records():
    local_records_dict = local_filesystem.get_known_local_models(
        model_directory=LOCAL_MODEL_DIRECTORY
    )

    return model_manager_lib.records_dict_to_jsonable(local_records_dict)


@app.get("/local/current")
def current_local_records():
    current_local_records_dict = local_filesystem.get_current_local_models(
        model_directory=LOCAL_MODEL_DIRECTORY
    )
    return model_manager_lib.records_dict_to_jsonable(
        current_local_records_dict
    )


@app.get("/remote/current")
def current_remote_records():
    current_remote_records_dict = gcs.get_current_remote_records(
        gcs_model_directory=REMOTE_MODEL_DIRECTORY
    )
    return model_manager_lib.records_dict_to_jsonable(
        current_remote_records_dict
    )


@app.delete("/models/{framework}/{name}")
def remove_model_by_name(framework: str, name: str):
    log.info(f"Delete model of framework={framework} name={name}")
    local_filesystem.delete_local_records_bykey(
        local_model_directory=LOCAL_MODEL_DIRECTORY,
        key=RecordKey(framework=framework, name=name),
    )
    local_records_dict = local_filesystem.get_known_local_models(
        model_directory=LOCAL_MODEL_DIRECTORY
    )
    return model_manager_lib.records_dict_to_jsonable(local_records_dict)


def pull_missing_local_models_from_remote() -> Tuple[gcs.RemoteRecord]:
    local_model_directory = LOCAL_MODEL_DIRECTORY
    remote_model_directory = REMOTE_MODEL_DIRECTORY
    automated_pull_start_time = time.time()
    log.debug(
        f"preparing to pull local={local_model_directory} remote={remote_model_directory}"
    )

    exceptions = []
    remotes_missing = get_remotes_missing_from_local(
        local_model_directory, remote_model_directory
    )
    statsd_client.gauge("remotes_missing", len(remotes_missing))

    if len(remotes_missing) == 0:
        log.info("No missing remotes to pull!")

    for remote in remotes_missing:
        log.debug(f"processing remote={remote}")
        expected_path = local_filesystem.get_expected_local_path(
            model_directory=local_model_directory, record=remote
        )
        try:
            log.debug(f"downloading remote={remote} to path={expected_path}")
            with statsd_client.timer('gcs.download_remote'):
                gcs.download_remote_record_locally(
                    remote_record=remote,
                    local_directory=expected_path,
                    temp_directory=TEMPORARY_MODEL_DIRECTORY,
                )
        except GcsDownloadException as err:
            statsd_client.incr(f'download_errors.{err.remote}')
            log.exception(f'Failed to download remote={err.remote}',
                          exc_info=err)

        except Exception as err:
            log.warning(
                f"exception thrown during processing remote={remote} delaying exception"
            )
            log.exception(
                "unhandled exception thrown during updating remote state",
                exc_info=err,
            )
            exceptions.append(err)

    for exception in exceptions:
        log.warning("throwing delayed exceptions!")
        raise exception

    log.info("finished pull. All models handled successfully")

    last_pull_data["run_time"] = automated_pull_start_time
    last_pull_data["took"] = time.time() - automated_pull_start_time
    last_pull_data["remotes_downloaded"] = [asdict(r) for r in remotes_missing]
    last_pull_data.sync()


def get_remotes_missing_from_local(
    local_model_directory: str, remote_model_directory: str
) -> Tuple[gcs.RemoteRecord]:
    locals = local_filesystem.get_current_local_models(local_model_directory)
    log.debug(f"found locals={locals}")
    remotes = gcs.get_current_remote_records(remote_model_directory)
    log.debug(f"found remotes={remotes}")

    missing_remotes = [
        remotes[record_key]
        for record_key in set(remotes.keys()) - set(locals.keys())
    ]
    log.debug(f"found missing_remotes={missing_remotes}")

    def need_pull_remote(record_key, remote_record, locals):
        return record_key in locals and (
            locals.get(record_key).version < remote_record.version
            or remote_record.is_priority > locals.get(record_key).is_priority
        )

    newer_remotes = [
        remote_record
        for record_key, remote_record in remotes.items()
        if need_pull_remote(record_key, remote_record, locals)
    ]
    log.debug(f"found new_remotes={newer_remotes}")
    return tuple(missing_remotes + newer_remotes)


def check_priority_bucket_state() -> Dict[RecordKey, local_filesystem.LocalRecord]:
    log.debug(
        f"preparing to check priority_bucket local={LOCAL_MODEL_DIRECTORY} remote={REMOTE_MODEL_DIRECTORY}"
    )
    current_local = local_filesystem.get_current_local_models(
        model_directory=LOCAL_MODEL_DIRECTORY
    )
    log.debug(f"found locals={current_local}")
    current_remote = gcs.get_current_remote_records(
        gcs_model_directory=REMOTE_MODEL_DIRECTORY
    )
    log.debug(f"found remotes={current_remote}")
    records_to_report = {
        record_key: local_record
        for record_key, local_record in current_local.items()
        if local_record.is_priority
        and record_key in current_remote
        and not current_remote[record_key].is_priority
    }
    for record_key, record in records_to_report.items():
        log.error(f"NEED TO FIX - {HOSTNAME} has local_record key={record_key} record= {record} set as priority while it is not on GCS remote.")
        statsd_client.incr('priority_errors')
    return records_to_report


def time_fn(fn, *args, **kwargs):
    start = time.time_ns()
    ret = fn(*args, **kwargs)
    total = round((time.time_ns() - start) * 1e-6, 2)
    log.info(f"ran {fn} took {total}ms")
    return ret


def pull_remote_state_loop():
    log.info(f"starting main background loop")
    while True:
        with statsd_client.timer("loop_time"):
            try:
                log.info("starting pull remote state")
                time_fn(pull_missing_local_models_from_remote)
                time_fn(check_priority_bucket_state)
                log.info("finished pull of remote statea")
            except Exception as err:
                log.exception(
                    "unhandled exception occurred during pull of missing data",
                    exc_info=err,
                )
                statsd_client.incr('exceptions')
        time.sleep(REMOTE_MODEL_PULL_FREQUENCY)


if __name__ == "__main__":
    statsd_client.incr("startup")
    processes = []
    if REMOTE_MODEL_PULL_FREQUENCY > 0:
        processes.append(
            mp.Process(
                target=pull_remote_state_loop,
                name="pull_remote_state_loop",
                args=(),
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
