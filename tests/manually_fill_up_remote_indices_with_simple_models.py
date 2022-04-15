#!/usr/bin/env python
from uuid import uuid4 as uuid
import argparse
import tempfile
import logging
import pathlib
import sys

import tests
from tests import config_manager_tests
from tests import remote_model_puller_tests

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model-names", help="csv of model names to load, for each version")
    p.add_argument("--model-versions", help="csv of versions to load, for each name")

    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG,
        stream=sys.stdout,
    )

    if args.model_names:
        names = args.model_names.strip().split(",")
    else:
        names = [f"{uuid().hex}" for _ in range(3)]

    if args.model_versions:
        versions = [int(x) for x in args.model_versions.strip().split(",")]
    else:
        versions = [1]

    temp_dir = pathlib.Path(tempfile.mkdtemp())

    all_test_records = []
    for name in names:
        test_records = tests.generate_random_test_records(
            framework="tensorflow", name=name, versions=versions
        )

        all_test_records += test_records
        for test_record in test_records:
            tests.build_local_model(
                test_record=test_record,
                multiplication_factor=test_record.version,
                output_dir=temp_dir,
                is_tar=True,
            )

    tests.push_local_model_directory_to_remote(temp_dir)

    print("The following model names and versions have been built:")

    print("")
    for name in names:
        print(f"    name={name} version={versions}")

    print("")
    print("You can find them at the following remote directories:")
    for test_record in all_test_records:
        print(f"    {tests.expected_remote_location(test_record)}")
    print("")
    print("")
    print("To engage pull to local file system you may run the following command:")
    print("   curl -XPOST localhost:8001/pull")
    print("")
    print("To engage config updating for tfserving you may run the following command:")
    print("  curl -XPOST localhost:8002/update_tfserving_config_from_local_filesystem")
