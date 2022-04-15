#! /usr/bin/env python
from uuid import uuid4 as uuid
from unittest import mock
import random

import tests


from model_manager_lib import RecordKey, Record
from model_manager_lib import local_filesystem


@mock.patch("model_manager_lib.local_filesystem.glob")
def test_gives_expected_local_models(mock_glob: mock.Mock):
    model_dir = "/my/model/dir"
    frameworks = tests.generate_random_strings(n=10)
    names = tests.generate_random_strings(n=10)
    versions = tests.generate_versions(n=10, min_val=0)
    glob_paths = [
        f"{model_dir}/{framework}/{name}/{version}"
        for version in versions
        for name in names
        for framework in frameworks
    ]
    random.shuffle(glob_paths)

    expected_record_keys = {
        RecordKey(
            framework=framework,
            name=name,
        )
        for name in names
        for framework in frameworks
    }

    mock_glob.return_value = glob_paths
    actual = local_filesystem.get_known_local_models(model_dir)

    assert expected_record_keys == set(
        actual.keys()
    ), f"""
    Missing keys unexpectedly from the set of values!
    
    expected:
    {expected_record_keys}
    
    actual: 
    {set(actual.keys())}
    """

    for expected_key in expected_record_keys:
        actual_local_records = actual[expected_key]
        actual_keys = {local_record.key for local_record in actual_local_records}
        assert {
            expected_key
        } == actual_keys, f"""
        Expected all local records to match the expected key!
        
        expected:
        {set(expected_key)}
        
        actual:
        {actual_keys}
        """
        expected_versions = [int(version) for version in versions]
        expected_is_priorities = [bool(int(version) == 0) for version in versions]

        actual_versions = [
            local_record.version for local_record in actual_local_records
        ]
        actual_is_priorities = [
            local_record.is_priority for local_record in actual_local_records
        ]
        assert (
            expected_versions == actual_versions
        ), f"""
        Expected all local records to be in the expected sorted order. They were not!
        
        expected:
        {expected_versions}
        
        actual:
        {actual_versions}
        """
        assert (
            expected_is_priorities == actual_is_priorities
        ), f"""
        Expected all local records to be in the expected sorted order. They were not!

        expected:
        {expected_is_priorities}

        actual:
        {actual_is_priorities}
        """


def test_get_expected_local_path():
    local_dir = "/my/local/dir"
    framework = uuid().hex
    name = uuid().hex
    version = random.randint(1, 1000)
    is_priority = random.randint(1, 1000) % 2 == 0
    if is_priority:
        version = 0
    expected = f"{local_dir}/{framework}/{name}/{version}"
    actual = local_filesystem.get_expected_local_path(
        local_dir,
        record=Record(
            key=RecordKey(
                framework=framework,
                name=name,
            ),
            is_priority=is_priority,
            version=version,
        ),
    )

    assert expected == actual
