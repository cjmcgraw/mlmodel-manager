from dataclasses import dataclass
from uuid import uuid4 as uuid
import subprocess as sp
from typing import List
import tempfile
import pathlib
import logging
import tarfile
import random
import shutil
import time
import io
import os

import requests
import pytest
import pathy

import tests

log = logging.getLogger(__file__)


def get_current_remote_puller_state(host="remote_model_puller", port=8001):
    response = requests.get(f"http://{host}:{str(port)}")
    response.raise_for_status()
    return response.json()


def get_current_remote_state(host="remote_model_puller", port=8001):
    response = requests.get(f"http://{host}:{str(port)}/remote/current")
    response.raise_for_status()
    return response.json()


def get_current_local_state(host="remote_model_puller", port=8001):
    response = requests.get(f"http://{host}:{str(port)}/local/current")
    response.raise_for_status()
    return response.json()


def get_all_local_state(host="remote_model_puller", port=8001):
    response = requests.get(f"http://{host}:{str(port)}/local/all")
    response.raise_for_status()
    return response.json()


def manually_trigger_remote_pull(host="remote_model_puller", port=8001):
    response = requests.post(f"http://{host}:{str(port)}/pull")
    response.raise_for_status()
    return response.text


def send_remove_model_request(
    frame_work: str, model_name: str, host="remote_model_puller", port=8001
):
    response = requests.delete(
        f"http://{host}:{str(port)}/models/{frame_work}/{model_name}", timeout=10
    )
    response.raise_for_status()
    return response.text


def make_local_records(test_records: List[tests.TestRecord]):
    for test_record in test_records:
        location = tests.expected_local_location(test_record)
        location.mkdir(parents=True, exist_ok=True)
        with open(location.joinpath("test_model"), "w") as f:
            f.write(uuid().hex)
