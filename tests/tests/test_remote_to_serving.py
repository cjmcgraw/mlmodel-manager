#! /usr/bin/env python
from uuid import uuid4 as uuid
import logging
import pytest
import tests
import pathlib
import os
import pathy
import random
import tempfile
from tests import remote_model_puller_tests as remote_tests
from tests import config_manager_tests

log = logging.getLogger(__file__)

REMOTE_MODEL_PATH = pathy.Pathy(
    str(
        pathlib.Path(os.environ["REMOTE_MODEL_DIRECTORY"]).joinpath(
            os.environ["ENVIRONMENT"]
        )
    ).replace("gs:/", "gs://")
)
LOCAL_CACHE = pathlib.Path(tempfile.mkdtemp())


@pytest.mark.usefixtures("clear_tfserving_config", "clear_local", "clear_remote")
def test_single_model_single_version_package_is_served():
    multiplication_factor = random.random()

    test_record = tests.generate_random_test_record(framework="tensorflow")

    tests.build_local_model(
        test_record, multiplication_factor, is_tar=True, output_dir=LOCAL_CACHE
    )

    tests.push_local_model_directory_to_remote(LOCAL_CACHE, REMOTE_MODEL_PATH)
    remote_tests.manually_trigger_remote_pull()
    config_manager_tests.config_manager_update_tfserving_config_from_local_filesystem()

    config_manager_tests.assert_prediction_matches_expected(
        test_record, multiplication_factor
    )


@pytest.mark.usefixtures("clear_tfserving_config", "clear_local", "clear_remote")
def test_single_model_multiple_versions_package_is_served():
    test_records = tests.generate_random_test_records(
        framework="tensorflow",
        name=uuid().hex,
        versions=sorted({random.randint(1, 10_000) for _ in range(10)}),
    )

    for test_record in test_records:
        multiplication_factor = random.random()
        tests.build_local_model(
            test_record, multiplication_factor, is_tar=True, output_dir=LOCAL_CACHE
        )

        tests.push_local_model_directory_to_remote(LOCAL_CACHE, REMOTE_MODEL_PATH)
        remote_tests.manually_trigger_remote_pull()
        config_manager_tests.config_manager_update_tfserving_config_from_local_filesystem()

        config_manager_tests.assert_prediction_matches_expected(
            test_record, multiplication_factor
        )


@pytest.mark.usefixtures("clear_tfserving_config", "clear_local", "clear_remote")
def test_multiple_models_single_version_package_is_served():
    test_records = tests.generate_random_test_records(
        framework="tensorflow", approx_n=10
    )
    multiplication_factors = dict()

    for test_record in test_records:
        multiplication_factors[test_record.name] = random.random()
        tests.build_local_model(
            test_record,
            multiplication_factors[test_record.name],
            is_tar=True,
            output_dir=LOCAL_CACHE,
        )

    tests.push_local_model_directory_to_remote(LOCAL_CACHE, REMOTE_MODEL_PATH)
    remote_tests.manually_trigger_remote_pull()
    config_manager_tests.config_manager_update_tfserving_config_from_local_filesystem()

    for test_record in test_records:
        multiplication_factor = multiplication_factors[test_record.name]

        config_manager_tests.assert_prediction_matches_expected(
            test_record, multiplication_factor
        )
