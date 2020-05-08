from fastapi import FastAPI, HTTPException, Response
import subprocess
import shlex
import itertools as i
import logging as log
import re
import os


def deploy_model(rendered_template, name):
    cmd = (
        f"docker stack deploy --with-registry-auth --resolve-image changed -c - {name}"
    )
    result = _run_cmd(cmd, check=True, input=rendered_template)


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

    quoted_cmd = [shlex.quote(command) for command in cmd]
    log.info(f"running command:\n{quoted_cmd}")
    result = subprocess.run(quoted_cmd, **kwargs)
    log.info(
        f"""
        finished command:
        {quoted_cmd}
        
        stdout:
        {result.stdout}

        stderr:
        {result.stderr}
        """
    )

    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout)
    return result


def get_container_status(team_name, model_name, deployment_id=None):
    cmd = [
        "docker",
        "service",
        "ps",
        f"{model_name}_mlmodel",
        "--no-trunc",
        "--format",
        "{{.Name}}__{{.Node}}__{{.Image}}__{{.DesiredState}}__{{.CurrentState}}__{{.Error}}",
    ]

    if deployment_id:

        cmd += ["--filter", f"label=team.{team_name}.deployment.id={deployment_id}"]

    cmd_stdout = _run_cmd(cmd).stdout
    key_names = ["name", "node", "image", "desired_state", "current_state", "error"]

    def process_into_dict(line):
        return dict(i.zip_longest(key_names, line.split("__")))

    return [process_into_dict(d) for d in cmd_stdout.strip().split("\n") if d.strip()]


def get_active_models(team_name, deployment_id=None):
    cmd = [
        "docker",
        "service",
        "ls",
        "--filter",
        f"label=team.{team_name}.type=mlmodel",
        "--format",
        "{{.Name}},{{.Image}},{{.Replicas}}",
    ]

    if deployment_id:
        cmd += ["--filter", f"label=team.{team_name}.deployment.id={deployment_id}"]

    key_names = ["name", "image", "replicas"]
    cmd_stdout = _run_cmd(cmd).stdout

    def process_into_dict(line):
        weird_formatted_name, *data = line.split(",")
        _, *keys = key_names
        name = re.sub("_mlmodel$", "", weird_formatted_name.split(".")[0])
        return dict(i.zip_longest(keys, data), name=name)

    return [process_into_dict(l) for l in cmd_stdout.strip().split("\n") if l.strip()]
