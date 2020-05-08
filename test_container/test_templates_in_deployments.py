from uuid import uuid4 as uuid
import logging as log
import requests
import time
import sys
import os

log.basicConfig(level=log.DEBUG, stream=sys.stdout)

import helpful_test_functions as helpers

urls = [url for url in helpers.generate_test_urls(10)]
imgs = [img for img in helpers.generate_test_images(10)]
model_types = [_type for _type in helpers.generate_model_types()]
r = helpers.requests_log_wrapper(requests)

for test_url, model_type, img in zip(urls, model_types, imgs):
    try:
        response = r.get(test_url)
        assert (
            500 >= response.status_code >= 400
        ), f"""
        Failed to check that running against an unknown test id would
        result in a 4xx response.

        url={test_url}

        {response.text}

        """
        body = {
            "domain": uuid().hex,
            "build_id": uuid().hex,
            "run_id": uuid().hex,
            "image": img,
            "model_type": model_type,
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
        time.sleep(5)

        response = r.get(test_url)
        assert (
            200 == response.status_code
        ), f"""
        Failed to retrieve previously created configuration 

        url={test_url}

        {response.text}
        """
        data = response.json()
        assert all(
            [
                data[0]["build_id"] == body["build_id"],
                data[0]["run_id"] == body["run_id"],
                data[0]["model_type"] == body["model_type"],
            ]
        ), f"""
        Expected build_id and run_id to match exactly

        url={test_url}
        build_id={body['build_id']}
        run_id={body['run_id']}
        model_type={body['model_type']}

        {data}
        """
    finally:
        response = r.delete(test_url + "?clear_all_records=true")
        assert (
            200 == response.status_code
        ), f"""
        Failed to delete test record. Watch out we still have lingering shit!

        url={test_url}

        {response.text}
        """
