from collections import defaultdict
import pytest
import random

import tests
from tests import remote_model_puller_tests as remote_tests


@pytest.mark.usefixtures("clear_local", "clear_remote")
def test_multiple_frameworks_and_names_do_not_collide():
    test_record, *_ = tests.generate_random_test_records(1)

    records_same_framework = [
        tests.generate_random_test_record(framework=test_record.framework)
        for _ in range(10)
    ]

    records_same_name = [
        tests.generate_random_test_record(name=test_record.name)
        for _ in range(10)
    ]

    records = [test_record] + records_same_name + records_same_framework
    random.shuffle(records)

    expected_by_framework = defaultdict(dict)
    for record in records:
        expected_by_framework[record.framework][record.name] = record

    expected_records_lookup = dict(expected_by_framework)

    tests.make_remote_records(records)
    remote_tests.manually_trigger_remote_pull()
    local_state = remote_tests.get_all_local_state()

    for framework, names in local_state.items():
        assert framework in expected_by_framework
        for name, actual_records in names.items():
            assert name in expected_by_framework[framework]
            for actual_record in actual_records:
                expected_record = expected_records_lookup[framework][name]
                assert actual_record['version'] == expected_record.version
