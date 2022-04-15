from collections import OrderedDict
from uuid import uuid4 as uuid
from typing import List, Set
import random
import pytest
import pathy
import time

import tests
from tests import config_manager_tests


def generate_test_case(n_names, versions, expected):
    case = OrderedDict(
        names={uuid().hex for _ in range(n_names)},
        versions=versions,
        expected=expected
    )
    return tuple(case.values())


test_cases = {
    "one model with one version": generate_test_case(
        n_names=1,
        versions=[1],
        expected=[1]
    ),
    "one model with two version": generate_test_case(
        n_names=1,
        versions=[1, 2],
        expected=[2]
    ),
    "one model with 10 versions": generate_test_case(
        n_names=1,
        versions=[x for x in range(10, 0, -1)],
        expected=[10],
    ),
    "one model with 10 versions reversed order": generate_test_case(
        n_names=1,
        versions=[x for x in range(1, 10)],
        expected=[9],
    ),
    "two models with one version": generate_test_case(
        n_names=2,
        versions=[1],
        expected=[1]
    ),
    "two models with 5 versions": generate_test_case(
        n_names=2,
        versions=[x for x in range(5, 0, -1)],
        expected=[5]
    ),
    "10 models with 5 versions": generate_test_case(
        n_names=10,
        versions=[x for x in range(5, 0, -1)],
        expected=[5]
    )
}


@pytest.mark.usefixtures('clear_tfserving_config', 'clear_local')
@pytest.mark.parametrize(
    argnames=['names', 'versions', 'expected'],
    argvalues=[x for x in test_cases.values()],
    ids=[x for x in test_cases.keys()]
)
def test_delete_cases(names: List[str], versions: List[int], expected: List[int]):
    assert len(versions) > 0

    version_to_expected = {}
    for version in versions:
        test_records = [
            tests.generate_random_test_record(
                framework='tensorflow',
                name=name,
                version=version
            ) for name in names
        ]

        multiplication_factors = [
            random.random()
            for _ in test_records
        ]

        version_to_expected[version] = zip(test_records, multiplication_factors)
        for test_record, factor in version_to_expected[version]:
            tests.build_local_model(test_record, factor, is_tar=False)

        # upload all the versions
        config_manager_tests.config_manager_update_tfserving_config_from_local_filesystem()
        for test_record, factor in version_to_expected[version]:
            config_manager_tests.assert_prediction_matches_expected(test_record, factor)

    # finally after all versions have been successfully loaded. Run the remove and
    # see that the local state is what we expect, and the most recent models are
    # still being served
    time.sleep(5)
    response = config_manager_tests.config_manager_remove_out_of_date_local_models()

    for expected_version in expected:
        for test_record, multi_factor in version_to_expected[expected_version]:
            config_manager_tests.assert_prediction_matches_expected(test_record, multi_factor)

        all_local_state = config_manager_tests.get_config_manager_all_local_models()
        assert 'tensorflow' in all_local_state
        tensorflow_local_state = all_local_state['tensorflow']
        for name in names:
            assert name in tensorflow_local_state
            all_versions = {model['version'] for model in tensorflow_local_state[name]}
            assert set(all_versions) == set(expected), f"""
            Failed to assert that the local state matched what we expected.
            
            We expect only the most recent model versions to remain after we've pruned
            the models that do exist. We found that more versions existed on the local
            file system then we expected!
            
            expected:
            {set(expected)}
            
            actual:
            {set(all_versions)}
            
            Please review the following log for more information:
            
            {response}
            """




@pytest.mark.usefixtures('clear_tfserving_config', 'clear_local')
def test_remove_model_name_request():
    # load one version of a model
    framework = "tensorflow"
    model_name = "model_to_remove"
    factor = random.random()
    test_record = tests.generate_random_test_records(1, framework=framework, name=model_name)[0]

    tests.build_local_model(test_record, factor, is_tar=False)

    config_manager_tests.config_manager_update_tfserving_config_from_local_filesystem()
    config_manager_tests.assert_prediction_matches_expected(test_record, factor)
    all_local_state = config_manager_tests.get_config_manager_all_local_models()
    assert(all_local_state[framework][model_name])
    # delete it by sending remove request
    config_manager_tests.config_manager_send_remove_model_request(framework, model_name)
    new_all_local_state = config_manager_tests.get_config_manager_all_local_models()
    assert(framework not in new_all_local_state or model_name not in new_all_local_state[framework])
    for model in all_local_state[framework][model_name]:
        assert(not pathy.Pathy(model['full_model_path']).exists())