from uuid import uuid4 as uuid
import logging as log
import requests
import time
import sys

import helpful_test_functions as helpers

log.basicConfig(level=log.DEBUG, stream=sys.stdout)

test_urls = [url for url in helpers.generate_test_urls(10)]
images = [img for img in helpers.generate_test_images(10)]
run_ids = [uuid().hex for _ in range(10)]
build_ids = [uuid().hex for _ in range(10)]
data = list(zip(test_urls, images, run_ids, build_ids))
log.info(data)
r = helpers.requests_log_wrapper(requests)

try:
    for test_url, *_ in data:
        log.info(f"running with test_url={test_url}")
        response = r.get(test_url)
        log.info(
            f"""recevied response from server:

        {response.text}
        """
        )
        assert (
            500 >= response.status_code >= 400
        ), f"""
        Failed to check that running against an unknown test id would
        result in a 4xx response.

        url={test_url}

        {response.text}
        """

    for test_url, image, run_id, build_id in data:
        body = {
            "domain": uuid().hex,
            "build_id": build_id,
            "run_id": run_id,
            "image": image,
            "model_type": "default",
        }
        response = r.post(test_url, json=body)
        assert (
            200 == response.status_code
        ), f"""
        Failed to create a request 

        url={test_url}
        body={body}

        {response.text}
        """

    time.sleep(10)
    for test_url, _, run_id, build_id in data:
        response = r.get(test_url + "?n=10")
        assert (
            200 == response.status_code
        ), f"""
        Failed to retrieve previously created configuration 

        url={test_url}

        {response.text}
        """
        actual = response.json()
        assert (
            len(actual) == 1
        ), f"""
        Expected length of deployments in request to be exactly 1
        got more than one:

        expected: 1
        actual: {len(actual)}

        {actual}
        """
        assert all(
            [actual[0]["build_id"] == build_id, actual[0]["run_id"] == run_id]
        ), f"""
        Expected exact match for run_id and build id from request.

        url={test_url}
        build_id={build_id}
        run_id={run_id}

        {actual}
        """
finally:
    for test_url, *_ in data:
        print(test_url)
        response = r.delete(test_url + "?clear_all_records=true")
        assert (
            200 == response.status_code
        ), f"""
        Failed to delete test record. Watch out we still have lingering shit!

        url={test_url}

        {response.text}
        """
