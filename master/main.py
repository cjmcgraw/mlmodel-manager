# @copyright
# Copyright (c) 2021 Accretive Technology Group, Inc. All rights
# reserved. For use only by Accretive Technology, its employees
# and contractors. DO NOT DISTRIBUTE.
import logging.config
import logging as log
import time
import sys
import fastapi
import datetime
from pydantic import BaseModel
import os
import requests
from typing import Literal
import socket

import model_manager_lib

from model_manager_lib import gcs, PriorityEndpoint
import uvloop
import uvicorn


HOSTNAME = socket.gethostname()
HTTP_HOST = "0.0.0.0"
HTTP_PORT = os.environ["HTTP_PORT"]
HTTP_WORKERS = os.environ["HTTP_WORKERS"]
ENVIRONMENT = os.environ["ENVIRONMENT"]
assert ENVIRONMENT in ["production", "integ", "staging", "test"]


start_time = time.time()
REMOTE_MODEL_DIRECTORY = model_manager_lib.load_remote_model_directory(
    os.environ["REMOTE_MODEL_DIRECTORY"], os.environ["ENVIRONMENT"]
)

__VERSION__ = "0.0.1"

app = fastapi.FastAPI()
logging.config.fileConfig("logging.cfg", disable_existing_loggers=False)

log.info(f"Environment: {ENVIRONMENT}")
log.info(f"Remote model directory: {REMOTE_MODEL_DIRECTORY}")


from fcache.cache import FileCache

registered_config_manager_cache = FileCache(
    ".registered_config_manager_cache", flag="cs"
)
registered_remote_model_puller_cache = FileCache(
    ".registered_remote_model_puller_cache", flag="cs"
)


class NodeEndpoint(BaseModel):
    node_type: Literal["config_manager", "remote_model_puller"]
    target: str


@app.get("/")
def root():
    return {
        "environment": ENVIRONMENT,
        "version": __VERSION__,
        "uptime": time.time() - start_time,
        "remote_model_directory": REMOTE_MODEL_DIRECTORY,
        "config_manager_nodes": registered_config_manager_cache.items(),
        "remote_model_puller_nodes": registered_remote_model_puller_cache.items(),
    }


@app.get("/health/ping")
@app.get("/ping")
def ping():
    return ["pong"]


@app.get("/health")
@app.get("/health/check")
@app.get("/health/test")
def health_check():
    return {"status": "green"}


def get_data_for_path(
    node_type, method, target, path, json_data=None, ret_format="json"
) -> str:
    """Send request to worker. It will remove a node from registration cache if
    it resulted a timeout error.
     :param node_type: str representing type of node,either "remote_model_puller" or "config_manager"
     :param method: HTTP method, "GET", "POST", "DELETE" etc
     :param target: request target ( worker hostname)
     :param path: the url path of the request
     :param json_data the JSON data to be posted
     "param ret_format the format of return string.
     :return: str
    """
    try:
        res = requests.request(
            method, f"http://{target}{path}", json=json_data, timeout=1
        )
        if res and ret_format == "json":
            ret_str = res.json()
        elif res:
            ret_str = res.text
        else:
            ret_str = ""
    except requests.exceptions.Timeout as err:
        ret_str = f"failed on request {err}"
        log.exception(f"failed on request {target}{path}", exc_info=err)
        if node_type == "config_manager":
            del registered_config_manager_cache[target]
        else:
            del registered_remote_model_puller_cache[target]
    except Exception as err:
        ret_str = f"failed on request {err}"
        log.exception(f"failed on request {target}{path}", exc_info=err)

    return ret_str


@app.get("/report_cluster_state")
def report_cluster_state():
    def get_local_filesystem(target, node_type):
        return get_data_for_path(node_type, "GET", target, "/local/all")

    def get_serving_all(target):
        return get_data_for_path(
            "config_manager", "GET", target, "/tensorflow_serving/all"
        )

    def get_serving_config(target):
        return get_data_for_path(
            "config_manager", "GET", target, "/tensorflow_serving/config", None, "text"
        )

    config_manager_data = {
        node: {
            "local_filesystem": get_local_filesystem(node, "config_manager"),
            "serving_all": get_serving_all(node),
            "serving_config": get_serving_config(node),
        }
        for node in list(registered_config_manager_cache.keys())
    }

    remote_model_puller_data = {
        node: {"local_filesystem": get_local_filesystem(node, "remote_model_puller")}
        for node in list(registered_remote_model_puller_cache.keys())
    }

    return {
        "config_manager": config_manager_data,
        "remote_model_puller": remote_model_puller_data,
    }


@app.delete("/models/{framework}/{model_name}")
def delete_model(framework: str, model_name):
    gcs.remove_model_gcs_bucket(REMOTE_MODEL_DIRECTORY, framework, model_name)
    registered_remote_model_pullers = registered_remote_model_puller_cache.items()
    remote_model_puller_data = {
        node: get_data_for_path(
            "remote_model_puller",
            "DELETE",
            node,
            f"/models/{framework}/{model_name}",
            None,
            "text",
        )
        for node in list(registered_remote_model_puller_cache.keys())
    }
    config_manager_data = {
        node: get_data_for_path(
            "config_manager",
            "DELETE",
            node,
            f"/models/{framework}/{model_name}",
            None,
            "text",
        )
        for node in list(registered_config_manager_cache.keys())
    }
    return {
        "config_manager": config_manager_data,
        "remote_model_puller": remote_model_puller_data,
    }


@app.post("/register")
def register_node(endpoint: NodeEndpoint):
    if not endpoint.target:
        raise fastapi.HTTPException(
            status_code=400,
            detail="target cannot be empty",
        )
    node_key = endpoint.target
    node_value = datetime.datetime.now()
    ret = None
    if endpoint.node_type == "remote_model_puller":
        registered_remote_model_puller_cache[node_key] = node_value
        ret = registered_remote_model_puller_cache.items()
    else:
        registered_config_manager_cache[node_key] = node_value
        ret = registered_config_manager_cache.items()
    return ret


@app.delete("/register")
def unregister_node(endpoint: NodeEndpoint):
    if not endpoint.target:
        raise fastapi.HTTPException(
            status_code=400,
            detail="target cannot be empty",
        )
    node_key = endpoint.target
    ret = None
    if endpoint.node_type == "remote_model_puller":
        if node_key in registered_remote_model_puller_cache:
            del registered_remote_model_puller_cache[node_key]
        ret = registered_remote_model_puller_cache.items()
    else:
        if node_key in registered_config_manager_cache:
            del registered_config_manager_cache[node_key]
        ret = registered_config_manager_cache.items()

    return ret


@app.post("/priority")
def set_priority(endpoint: PriorityEndpoint):
    if not (endpoint.framework and endpoint.name and endpoint.version):
        raise fastapi.HTTPException(
            status_code=400,
            detail="framework/name/version should all be set to set priority",
        )

    gcs.copy_remote_record_to_priority_bucket(
        REMOTE_MODEL_DIRECTORY, endpoint.framework, endpoint.name, endpoint.version
    )
    # todo, send pull &  config_update to all nodes
    for node in list(registered_remote_model_puller_cache.keys()):
        get_data_for_path("remote_model_puller", "POST", node, "/pull")
    for node in list(registered_config_manager_cache.keys()):
        get_data_for_path(
            "config_manager",
            "POST",
            node,
            "/update_tfserving_config_from_local_filesystem",
            None,
            "text",
        )


@app.delete("/priority")
def remove_priority(endpoint: PriorityEndpoint):
    if (not endpoint.framework) or (not endpoint.name):
        raise fastapi.HTTPException(
            status_code=400,
            detail="framework/name should all be set to remove priority",
        )
    gcs.remove_priority_bucket(
        REMOTE_MODEL_DIRECTORY, endpoint.framework, endpoint.name
    )
    # Note when a node failed to receive delete priority call, it would result
    # discrepency between remote and local. Two jira tickets have been
    # added to address this problem  https://jira.atg-corp.com/browse/DEV-75599?and
    # https://jira.atg-corp.com/browse/DEV-75602
    #
    config_manager_data = {
        node: get_data_for_path(
            "config_manager",
            "DELETE",
            node,
            f"/priority",
            {"framework": endpoint.framework, "name": endpoint.name},
            "text",
        )
        for node in list(registered_config_manager_cache.keys())
    }

    return config_manager_data


if __name__ == "__main__":
    processes = []
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
