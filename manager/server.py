from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
from uuid import uuid4 as uuid
from typing import List, Dict
import collections
import subprocess
import logging as log
import jinja2
import datetime
import pymongo
import docker as docker_lib
import itertools as i
import string as s
import shlex
import json
import time
import sys
import os
import re

log.basicConfig(level=log.DEBUG, stream=sys.stdout)


ENVIRONMENT_NAME = os.environ["ENVIRONMENT"]
TEAM_NAME = os.environ["TEAM_NAME"]

MONGO_USER = os.environ["MONGO_USER"]
MONGO_PASSWORD = os.environ["MONGO_PASSWORD"]

MANAGER_BUILD_ID = os.environ["MANAGER_BUILD_ID"]
MLMODEL_ENDPOINT_DOMAIN_FORMAT = os.environ["MLMODEL_ENDPOINT_DOMAIN_FORMAT"]

process_id = uuid().hex
start_time = time.time()
log.info(f"beginning process with pid={process_id} at time={start_time}")

log.info(f"connecting to mongo")
mongo = pymongo.MongoClient(
    "mongo", 27017, username=MONGO_USER, password=MONGO_PASSWORD, connectTimeoutMS=1000
)
log.info(f"collecting information regarding pymongo database")
db = mongo.ml_models
log.info(f"connection successful")

log.info(f"connecting to docker environment")
docker = docker_lib.from_env()

global_counters = {"deployments": collections.Counter(), "calls": collections.Counter()}

app = FastAPI()
thread_id = uuid().hex


@app.get("/health/ping")
@app.get("/ping")
def ping():
    return ["pong"]


@app.get("/version")
@app.get("/health")
@app.get("/health/check")
@app.get("/health/test")
def health_check():
    def get_models_names(models):
        return [model["name"] for model in models]

    all_models = get_all_models()
    active_models = filter(lambda x: x["active"], all_models)
    valid_models = filter(lambda x: x["valid"], all_models)
    weird_models = filter(lambda x: x["active"] and not x["valid"], all_models)

    health_summary = {
        "manager_build_id": MANAGER_BUILD_ID,
        "mongo": bool(mongo.server_info()),
        "docker": bool(docker.info()),
        "all_models": get_models_names(all_models),
        "active_models": get_models_names(active_models),
        "valid_models": get_models_names(valid_models),
        "weird_models": get_models_names(weird_models),
    }
    log.info(f"health check summary: {health_summary}")
    return health_summary


@app.get("/metrics")
def metrics():
    def model_to_prometheus_key(model):
        data = [f'name="{model["name"]}"']
        if "deployment" in model:
            deployment = model["deployment"][0]
            data += [
                f'domain="http://{deployment.domain}:{deployment.port}"',
                f'build_id="{deployment.build_id}"',
                f'run_id="{deployment.run_id}"',
                f'image="{deployment.image}"',
                f'model_type="{deployment.model_type}"',
                f'deployment_time="{deployment.deployment_time}"',
            ]
        return ",".join(data)

    all_models = get_all_models(verbose=True)
    all_names = [model["name"] for model in all_models]
    all_model_keys = {
        model["name"]: model_to_prometheus_key(model) for model in all_models
    }
    active_models = {model["name"] for model in all_models if model["active"]}
    valid_models = {model["name"] for model in all_models if model["valid"]}
    weird_models = active_models - valid_models

    data = []
    data += [f"mlmodel_manager_active{{{all_model_keys[m]}}} 1" for m in active_models]
    data += [f"mlmodel_manager_valid{{{all_model_keys[m]}}} 1" for m in valid_models]
    data += [f"mlmodel_manager_weird{{{all_model_keys[m]}}} 1" for m in weird_models]

    for model in all_models:
        k = all_model_keys[model["name"]]
        if "deployment" in model:
            deployment = model["deployment"][0]
            for service in deployment.swarm_services:
                if "replicas" in service:
                    running, requested = [
                        int(x) for x in service["replicas"].split("/", 1)
                    ]
                    data += [
                        f"mlmodel_manager_model_running_replicas{{{k}}} {running}",
                        f"mlmodel_manager_model_request_replicas{{{k}}} {requested}",
                    ]
                if deployment.containers:
                    container_states = collections.Counter(
                        [
                            str(container["desired_state"]).lower()
                            for container in deployment.containers
                        ]
                    )
                    data += [
                        f"mlmodel_manager_model_{i}{{{k}}} {n}"
                        for (i, n) in container_states.items()
                    ]

    return Response(content="\n".join(data), media_type="text/plain")


class DeploymentRecord(BaseModel):
    template_file: str = None
    model_type: str
    name: str = None
    domain: str = None
    port: int = 80
    deploy_delay: str = "5s"
    deploy_monitor_period: str = "30s"
    cpu_limit: str = "1"
    mem_limit: str = "2G"
    cpu_reservation: str = "0.1"
    mem_reservation: str = "1G"
    scale: int = 2
    deployment_id: str = None
    deployment_time: str = None
    deployment_time_isoformat: str = None
    name: str = None
    build_id: str
    run_id: str
    image: str
    extra_template_attributes: Dict = {}
    rendered_template: str = None
    swarm_services: List = None
    containers: List = None

    @staticmethod
    def get_last_n(name, n):
        log.info(f"loading model from database name: {name}")
        collection = db[f"deployments_{name}"]
        all_deployments_by_time = (
            collection.find().sort([("_id", pymongo.DESCENDING)]).limit(n)
        )
        deployments = []

        for data in all_deployments_by_time:
            data.setdefault("model_type", "")
            if data:
                deployment = DeploymentRecord(**data)
                deployment.containers = get_container_status(
                    name, deployment_id=deployment.deployment_id
                )

                deployment.swarm_services = get_active_models(
                    deployment_id=deployment.deployment_id
                )
                deployments.append(deployment)
        return deployments

    @staticmethod
    def clear_all_records_by_name(name):
        db[f"deployments_{name}"].drop()

    @staticmethod
    def get_all_valid_deployment_names():
        return [
            re.sub("^deployments_", "", collection)
            for collection in db.list_collection_names()
            if collection.startswith("deployments_")
        ]

    def save(self):
        data = dict(self, swarm_status={}, container_status=[])
        del data["swarm_status"]
        del data["container_status"]
        collection = db[f"deployments_{self.name}"]
        collection.insert_one(data)

        return self


@app.get("/")
def get_all_models(live_only: bool = False, verbose: bool = False):
    all_live_models = set(service["name"] for service in get_active_models())
    all_valid_deployments = set(DeploymentRecord.get_all_valid_deployment_names())
    all_names = all_valid_deployments | all_live_models

    if live_only:
        all_names = all_live_models

    log.info(f"all_models: {all_names}")
    log.info(f"all_live: {all_live_models}")

    def process_model(name):
        record = {
            "name": name,
            "valid": name in all_valid_deployments,
            "active": name in all_live_models,
        }

        if verbose:
            record["deployment"] = DeploymentRecord.get_last_n(name, 1)
        return record

    return [process_model(name) for name in all_names]


@app.get("/{model}")
def get_model(model: str, n: int = 1):
    deployments = list(DeploymentRecord.get_last_n(model, n))
    if len(deployments) < 1:
        raise HTTPException(404, detail=f"unknown deployment {model}")
    log.info(f"retrieving ML mlodel deployments: {deployments}")
    return deployments


@app.delete("/{model}")
def delete_model(model: str, clear_all_records: bool = False):
    log.warning(f"deleting ML model deployment: {model}")
    deployments = list(DeploymentRecord.get_last_n(model, 1))

    try:
        stop_model(model)
    except HTTPException as err:
        log.exception(err)
        ...

    if clear_all_records:
        log.warning(f"clearing all production records for {model}")
        DeploymentRecord.clear_all_records_by_name(model)
    return {"deployments": deployments}


@app.put("/{model}")
@app.post("/{model}")
def add_model(model: str, deployment: DeploymentRecord):
    deployment.name = model
    deployment.domain = MLMODEL_ENDPOINT_DOMAIN_FORMAT.format(model_name=model)
    deployment.template_file = f"{deployment.model_type}.template.yml"

    template_file = deployment.template_file.split("/")[-1]
    with open(f"/app/templates/{template_file}") as f:
        template = jinja2.Template(f.read())

    deployment.deployment_id = uuid().hex
    deployment.deployment_time = datetime.datetime.utcnow().isoformat()
    rendered_template = template.render(
        **dict(deployment),
        team_name=TEAM_NAME,
        current_time=time.time(),
        environment=ENVIRONMENT_NAME,
        **dict(deployment.extra_template_attributes),
    )
    log.info(f"rendered template:\n{rendered_template}")
    cmd = f"docker stack deploy --with-registry-auth --resolve-image changed -c - {deployment.name}"

    deployment.rendered_template = rendered_template
    deployment.save()
    result = _run_cmd(cmd, check=True, input=rendered_template)
    deployment.containers = []
    deployment.swarm_services = []
    return deployment


def stop_model(model: str):
    cmd = f"docker stack rm {model}"

    result = None
    try:
        result = _run_cmd(cmd, check=True)
    except:
        log.critical(f"Failed to stop model for unknown reason:\n{result}")
        raise HTTPException(status_code=400, detail="unknown mlmodel given!")


def _run_cmd(cmd, **kwargs):
    check = kwargs.get("check", False)
    kwargs["check"] = False
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("encoding", "utf-8")
    if isinstance(cmd, str):
        cmd = cmd.split(" ")
    log.info(f"running command:\n{cmd}")
    result = subprocess.run(cmd, **kwargs)
    log.info(
        f"""
        finished command:
        {cmd}
        
        stdout:
        {result.stdout}

        stderr:
        {result.stderr}
        """
    )

    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout)
    return result


def get_container_status(model_name, deployment_id=None):
    cmd = [
        "docker",
        "service",
        "ps",
        shlex.quote(f"{model_name}_mlmodel"),
        "--no-trunc",
        "--format",
        "{{.Name}}__{{.Node}}__{{.Image}}__{{.DesiredState}}__{{.CurrentState}}__{{.Error}}",
    ]

    if deployment_id:
        cmd += ["--filter", f"label=team.{TEAM_NAME}.deployment.id={deployment_id}"]

    cmd_stdout = _run_cmd(cmd).stdout
    key_names = ["name", "node", "image", "desired_state", "current_state", "error"]

    def process_into_dict(line):
        return dict(i.zip_longest(key_names, line.split("__")))

    return [process_into_dict(d) for d in cmd_stdout.strip().split("\n") if d.strip()]


def get_active_models(deployment_id=None):
    cmd = [
        "docker",
        "service",
        "ls",
        "--filter",
        f"label=team.{TEAM_NAME}.type=mlmodel",
        "--format",
        "{{.Name}},{{.Image}},{{.Replicas}}",
    ]

    if deployment_id:
        cmd += ["--filter", f"label=team.{TEAM_NAME}.deployment.id={deployment_id}"]

    key_names = ["name", "image", "replicas"]
    cmd_stdout = _run_cmd(cmd).stdout

    def process_into_dict(line):
        weird_formatted_name, *data = line.split(",")
        _, *keys = key_names
        name = re.sub("_mlmodel$", "", weird_formatted_name.split(".")[0])
        return dict(i.zip_longest(keys, data), name=name)

    return [process_into_dict(l) for l in cmd_stdout.strip().split("\n") if l.strip()]
