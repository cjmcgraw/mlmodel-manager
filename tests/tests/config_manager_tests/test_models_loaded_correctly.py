from uuid import uuid4 as uuid
import random
import pytest
import time

import tests
from tests import config_manager_tests


@pytest.mark.usefixtures("clear_tfserving_config", "clear_local")
def test_single_model_single_version_is_served():
    multiplication_factor = random.random()

    test_record = tests.generate_random_test_record(framework="tensorflow")

    tests.build_local_model(test_record, multiplication_factor, is_tar=False)
    config_manager_tests.config_manager_update_tfserving_config_from_local_filesystem()

    config_manager_tests.assert_prediction_matches_expected(
        test_record, multiplication_factor
    )


@pytest.mark.usefixtures("clear_tfserving_config", "clear_local")
def test_single_model_two_versions_one_priority_are_served():
    multiplication_factor1 = random.random()
    multiplication_factor2 = random.random()
    test_records = tests.generate_random_test_records(
        2,
        framework="tensorflow",
        name=uuid().hex,
        versions=sorted({random.randint(1, 10_000) for _ in range(2)}),
        priorities=[True, False],
    )

    tests.build_local_model(test_records[0], multiplication_factor1, is_tar=False)
    tests.build_local_model(test_records[1], multiplication_factor2, is_tar=False)
    config_manager_tests.config_manager_update_tfserving_config_from_local_filesystem()

    config_manager_tests.assert_prediction_matches_expected(
        test_records[0], multiplication_factor1
    )


@pytest.mark.usefixtures("clear_tfserving_config", "clear_local")
def test_single_model_multiple_versions_is_served():
    test_records = tests.generate_random_test_records(
        framework="tensorflow",
        name=uuid().hex,
        versions=sorted({random.randint(1, 10_000) for _ in range(10)}),
    )

    for test_record in test_records:
        multiplication_factor = random.random()

        tests.build_local_model(test_record, multiplication_factor, is_tar=False)
        config_manager_tests.config_manager_update_tfserving_config_from_local_filesystem()

        config_manager_tests.assert_prediction_matches_expected(
            test_record, multiplication_factor
        )


@pytest.mark.usefixtures("clear_local", "clear_tfserving_config")
def test_multiple_models_single_version_is_served():
    test_records = tests.generate_random_test_records(
        framework="tensorflow", approx_n=10
    )
    multiplication_factors = dict()

    for test_record in test_records:
        multiplication_factors[test_record.name] = random.random()
        tests.build_local_model(
            test_record, multiplication_factors[test_record.name], is_tar=False
        )

    config_manager_tests.config_manager_update_tfserving_config_from_local_filesystem()

    for test_record in test_records:
        multiplication_factor = multiplication_factors[test_record.name]

        config_manager_tests.assert_prediction_matches_expected(
            test_record, multiplication_factor
        )
