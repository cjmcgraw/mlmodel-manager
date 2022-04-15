from dataclasses import dataclass
from typing import List, Dict
from uuid import uuid4 as uuid
import subprocess as sp
import tempfile
import pathlib
import logging
import random
import shutil
import pytest
import os
import requests
import pathy
import subprocess as sp

from tensorflow_serving.apis import get_model_status_pb2

PRIORITY_VERSION = 0
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

import tensorflow as tf

MODEL_STATE = get_model_status_pb2.ModelVersionStatus.State

log = logging.getLogger(__file__)

LOCAL_MODEL_PATH = pathlib.Path(os.environ["LOCAL_MODEL_DIRECTORY"])
LOCAL_CACHE = pathlib.Path(tempfile.mkdtemp())


@pytest.fixture
def clear_local():
    def clear_local_state():
        for path in LOCAL_MODEL_PATH.glob("*"):
            shutil.rmtree(str(path), ignore_errors=True)

    clear_local_state()
    yield
    clear_local_state()


@pytest.fixture
def clear_remote():
    def clear_remote_state():
        sp.run(
            [
                "gsutil",
                "-m",
                "rm",
                "-rf",
                str(REMOTE_MODEL_PATH.joinpath("**/model.tar.gz")),
            ]
        )

    clear_remote_state()
    yield
    clear_remote_state()


@dataclass()
class TestRecord:
    framework: str
    name: str
    version: int
    is_priority: bool


def expected_local_location(
    test_record: TestRecord, base_path=LOCAL_MODEL_PATH
) -> pathlib.Path:
    if test_record.is_priority:

        local_path = (
            base_path.joinpath(test_record.framework)
            .joinpath(test_record.name)
            .joinpath(str(PRIORITY_VERSION))
        )
    else:
        local_path = (
            base_path.joinpath(test_record.framework)
            .joinpath(test_record.name)
            .joinpath(str(test_record.version))
        )
    return local_path


def generate_random_test_record(
    framework=None, name=None, version=None, is_priority=False
):
    return TestRecord(
        framework=framework or f"framework={uuid().hex}",
        name=name or f"name={uuid().hex}",
        is_priority=is_priority,
        version=version or random.randint(1, 1e6),
    )


def generate_random_test_records(
    approx_n=10, framework=None, name=None, versions=None, priorities=None
):
    # needs to be set for each one if set

    versions = list(
        versions
        if versions is not None
        else sorted({random.randint(1, 1e6) for _ in range(approx_n)}, reverse=True)
    )
    if priorities is not None:
        assert len(priorities) == len(versions)
    else:
        priorities = [False] * len(versions)
    return [
        generate_random_test_record(framework, name, version, is_priority)
        for is_priority, version in zip(priorities, versions)
    ]


def build_local_model(
    test_record: TestRecord,
    multiplication_factor: float,
    output_dir: str = LOCAL_MODEL_PATH,
    is_tar: bool = False,
) -> TestRecord:
    assert test_record.framework == "tensorflow"
    multiplication_factor = tf.constant(multiplication_factor, dtype=tf.float64)
    x = tf.keras.Input(shape=(1,), dtype=tf.float64, name="x")
    y = x * multiplication_factor
    model = tf.keras.Model(inputs=x, outputs=y)

    input_signature = {"x": tf.TensorSpec(dtype=tf.float64, shape=[1], name="x")}

    @tf.function(input_signature=[input_signature])
    def serving_function(input_data: Dict[str, tf.Tensor]):
        data = input_data["x"]
        result = model(data)
        return {"y": tf.reshape(result, [-1], name="y")}

    tmp_output_dir = LOCAL_CACHE.joinpath(uuid().hex)
    tmp_model_save_path = expected_local_location(
        test_record=test_record, base_path=tmp_output_dir
    )
    final_output_path = expected_local_location(
        test_record=test_record,
        base_path=output_dir,
    )

    model.compile()
    model.save(
        filepath=str(tmp_model_save_path),
        overwrite=False,
        signatures={
            tf.saved_model.DEFAULT_SERVING_SIGNATURE_DEF_KEY: serving_function,
            tf.saved_model.PREDICT_METHOD_NAME: serving_function,
        },
    )

    if is_tar:
        shutil.make_archive(
            base_name=str(final_output_path.joinpath("model")),
            format="gztar",
            root_dir=str(tmp_model_save_path),
        )
    else:
        sp.check_output(
            [
                "cp",
                "-r",
                str(tmp_output_dir) + "/" + test_record.framework,
                str(output_dir),
            ]
        )

    shutil.rmtree(tmp_output_dir, ignore_errors=True)
    return test_record


def check_response(r: requests.Response):
    if r.status_code != 200:
        raise ValueError(
            f"""
        Failed to post .

        status_code:
        {r.status_code}

        response:
        {r.text}
        """
        )
    return r


REMOTE_MODEL_PATH = pathy.Pathy(
    str(
        pathlib.Path(os.environ["REMOTE_MODEL_DIRECTORY"]).joinpath(
            os.environ["ENVIRONMENT"]
        )
    ).replace("gs:/", "gs://")
)


@dataclass()
class RemoteTarData:
    test_record: TestRecord
    remote_path: pathy.Pathy
    expected_test_file_contents: str

    def assert_unpacked_tar_matches(self, path: pathlib.Path):
        local_file_path = path.joinpath("test_directory").joinpath("test_file")
        assert local_file_path.exists()
        with open(str(local_file_path), "r") as f:
            actual_test_file_contents = f.read()

        assert self.expected_test_file_contents == actual_test_file_contents


def make_remote_records(test_records: List[TestRecord]) -> List[RemoteTarData]:
    if len(test_records) == 0:
        return []
    upload_dir = LOCAL_CACHE.joinpath(uuid().hex)
    upload_dir.mkdir(parents=True, exist_ok=True)

    testing_tar_files = []
    for test_record in test_records:
        if test_record.is_priority:
            test_record.version = 0

        final_tar_location = (
            upload_dir.joinpath(test_record.framework)
            .joinpath(test_record.name)
            .joinpath(str(test_record.version))
        )

        root_dir = LOCAL_CACHE.joinpath(uuid().hex)
        test_dir = root_dir.joinpath("test_directory")
        test_dir.mkdir(parents=True, exist_ok=True)

        expected_test_file_contents = uuid().hex
        with open(test_dir.joinpath("test_file"), "w") as f:
            f.write(expected_test_file_contents)

        final_tar_location.mkdir(parents=True, exist_ok=True)
        shutil.make_archive(
            base_name=str(final_tar_location.joinpath("model")),
            format="gztar",
            root_dir=str(root_dir),
        )

        testing_tar_file = RemoteTarData(
            test_record=test_record,
            remote_path=expected_remote_location(test_record),
            expected_test_file_contents=expected_test_file_contents,
        )
        testing_tar_files.append(testing_tar_file)

    push_local_model_directory_to_remote(upload_dir)
    return testing_tar_files


def push_local_model_directory_to_remote(
    local_model_dir: pathlib.Path, remote_model_path: pathlib.Path = REMOTE_MODEL_PATH
):
    assert local_model_dir.exists()
    cmd = ["gsutil", "-m", "cp", "-r", str(local_model_dir), str(remote_model_path)]
    log.info(f"running command: {cmd}")
    sp.check_output(cmd)


def expected_remote_location(
    test_record: TestRecord, base_path=REMOTE_MODEL_PATH
) -> pathy.Pathy:
    if test_record.is_priority:
        remote_path = (
            base_path.joinpath(test_record.framework)
            .joinpath(test_record.name)
            .joinpath(str(PRIORITY_VERSION))
        )
    else:
        remote_path = (
            base_path.joinpath(test_record.framework)
            .joinpath(test_record.name)
            .joinpath(str(test_record.version))
        )
    return remote_path
