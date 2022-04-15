#! /usr/bin/env python
from collections import OrderedDict
from uuid import uuid4 as uuid
import logging
import pytest
import shutil
import tests
from tests import remote_model_puller_tests as remote_tests

log = logging.getLogger(__file__)


def generate_test_case(
    test_case_name, local_versions, remote_versions, remote_priority, expected, **kwargs
):
    args = OrderedDict(
        test_case_name=test_case_name,
        framework=kwargs.get("framework", f"test={test_case_name}_{uuid().hex}"),
        name=kwargs.get("name", f"name={uuid().hex}"),
        local_versions=local_versions,
        remote_versions=remote_versions,
        remote_priority=remote_priority,
        expected=expected,
    )
    return tuple(args.values())


test_cases = {
    "both_empty": generate_test_case(
        test_case_name="both_empty",
        local_versions=[],
        remote_versions=[],
        remote_priority=[],
        expected=[],
    ),
    "local_empty_remote_with_one": generate_test_case(
        test_case_name="local_empty_remote_with_one",
        local_versions=[],
        remote_versions=[1],
        remote_priority=None,
        expected=[1],
    ),
    "local_empty_remote_with_two": generate_test_case(
        test_case_name="local_empty_remote_with_two",
        local_versions=[],
        remote_versions=[2, 1],
        remote_priority=None,
        expected=[2],
    ),
    "local_empty_remote_with_three": generate_test_case(
        test_case_name="local_empty_remote_with_three",
        local_versions=[],
        remote_versions=[3, 2, 1],
        remote_priority=None,
        expected=[3],
    ),
    "local_with_one_remote_empty": generate_test_case(
        test_case_name="local_with_one_remote_empty",
        local_versions=[1],
        remote_versions=[],
        remote_priority=None,
        expected=[1],
    ),
    "local_with_one_remote_with_one": generate_test_case(
        test_case_name="local_with_one_remote_with_one",
        local_versions=[1],
        remote_versions=[1],
        remote_priority=None,
        expected=[1],
    ),
    "local_with_one_remote_with_two": generate_test_case(
        test_case_name="local_with_one_remote_with_two",
        local_versions=[1],
        remote_versions=[2, 1],
        remote_priority=None,
        expected=[2, 1],
    ),
    "local_with_one_remote_with_three": generate_test_case(
        test_case_name="local_with_one_remote_with_three",
        local_versions=[1],
        remote_versions=[3, 2, 1],
        remote_priority=None,
        expected=[3, 1],
    ),
    "local_with_two_remote_empty": generate_test_case(
        test_case_name="local_with_two_remote_empty",
        local_versions=[2, 1],
        remote_versions=[],
        remote_priority=None,
        expected=[2, 1],
    ),
    "local_with_two_remote_with_one": generate_test_case(
        test_case_name="local_with_one_remote_with_one",
        local_versions=[2, 1],
        remote_versions=[1],
        remote_priority=None,
        expected=[2, 1],
    ),
    "local_with_two_remote_with_two": generate_test_case(
        test_case_name="local_with_one_remote_with_two",
        local_versions=[2, 1],
        remote_versions=[2, 1],
        remote_priority=None,
        expected=[2, 1],
    ),
    "local_with_two_remote_with_three": generate_test_case(
        test_case_name="local_with_one_remote_with_three",
        local_versions=[2, 1],
        remote_versions=[3, 2, 1],
        remote_priority=None,
        expected=[3, 2, 1],
    ),
    "local_with_two_remote_with_one_priority": generate_test_case(
        test_case_name="local_with_one_remote_with_three",
        local_versions=[3, 2],
        remote_versions=[1],
        remote_priority=[True],
        expected=[0, 3, 2],
    ),
    "local_with_one_remote_with_one_priority": generate_test_case(
        test_case_name="local_with_one_remote_with_three",
        local_versions=[1],
        remote_versions=[1],
        remote_priority=[True],
        expected=[0, 1],
    ),
}


@pytest.mark.usefixtures("clear_local", "clear_remote")
@pytest.mark.parametrize(
    argnames=[
        "test_case_name",
        "framework",
        "name",
        "local_versions",
        "remote_versions",
        "remote_priority",
        "expected",
    ],
    argvalues=[v for _, v in test_cases.items()],
    ids=[k for k, _ in test_cases.items()],
)
def test_cases(
    test_case_name,
    framework,
    name,
    local_versions,
    remote_versions,
    remote_priority,
    expected,
):
    # setup local state
    random_local_test_records = tests.generate_random_test_records(
        framework=framework, name=name, versions=local_versions
    )
    remote_tests.make_local_records(random_local_test_records)

    # setup remote state
    random_remote_test_records = tests.generate_random_test_records(
        framework=framework,
        name=name,
        versions=remote_versions,
        priorities=remote_priority,
    )
    tests.make_remote_records(random_remote_test_records)

    remote_tests.manually_trigger_remote_pull()
    all_local_state = remote_tests.get_all_local_state()

    if len(expected) > 0:
        assert framework in all_local_state
        assert name in all_local_state[framework]
        records = all_local_state[framework][name]
        assert len(records) == len(expected)
        assert expected == [record["version"] for record in records], [
            record["version"] for record in records
        ]
    else:
        assert all_local_state == {}


@pytest.mark.usefixtures("clear_local", "clear_remote")
def test_priority_check():
    framework = "tensorflow"
    name = "prioritycheck"
    # setup remote state
    random_remote_test_records = tests.generate_random_test_records(
        framework=framework, name=name, versions=[1, 2, 3]
    )
    tests.make_remote_records(random_remote_test_records)
    pull_result = remote_tests.manually_trigger_remote_pull()
    assert (
        "ERROR" not in pull_result
    ), f"""
    local should be in sync with remote therefore there was no error message being logged.
    actual:
    {pull_result}
"""
    all_local_state = remote_tests.get_all_local_state()
    assert framework in all_local_state
    assert name in all_local_state[framework]
    assert len(all_local_state[framework][name]) > 0
    record = all_local_state[framework][name][0]
    # manually create priority bucket
    testrecord = tests.TestRecord(
        record["key"]["framework"],
        record["key"]["name"],
        record["version"],
        record["is_priority"],
    )
    test_priority_record = tests.TestRecord(
        record["key"]["framework"],
        record["key"]["name"],
        tests.PRIORITY_VERSION,
        record["is_priority"],
    )

    record_path = tests.expected_local_location(testrecord)
    priority_record_path = tests.expected_local_location(test_priority_record)
    shutil.copytree(record_path, priority_record_path)
    # error message should show up
    pull_result = remote_tests.manually_trigger_remote_pull()
    assert (
        "ERROR" in pull_result
    ), f"""
        local now is different from remote from the manual copy above. Therefore we would expect error message being logged.
        actual:
        {pull_result}
    """
