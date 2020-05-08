from uuid import uuid4 as uuid
import requests as r
import itertools as i
import requests as r
import logging
import json
import time
import os

log = logging.getLogger(__file__)

environment_name = os.environ.get("ENVIRONMENT", None)
# we need the manager for docker runs, localhost for local runs
manager_domain = "manager" if environment_name else "localhost"
images = [f"qarlm/static-http-response-server:{n}" for n in range(1, 10)]
model_types = ["default"]


def generate_test_images(n=3):
    yield from i.islice(i.cycle(images), n)


def generate_model_types(n=len(model_types)):
    yield from i.islice(i.cycle(model_types), n)


def generate_test_urls(n=3):
    yield from (
        f"http://{manager_domain}/test_{time.time()}_{uuid().hex[:11]}".replace(
            ".", "_"
        )
        for _ in range(n)
    )


def requests_log_wrapper(r):
    class req_wrap:
        def __getattr__(self, name):
            attr = r.__getattribute__(name)
            if callable(attr):

                def func(*args, **kwargs):
                    log.debug(args)
                    log.debug(kwargs)
                    if "json" in kwargs:
                        log.debug("\n" + json.dumps(kwargs["json"], indent=4))
                    response = attr(*args, **kwargs)
                    if isinstance(response, r.Response):
                        log.debug(response)
                        if response.headers.get("content-type") == "application/json":
                            log.debug("\n" + json.dumps(response.json(), indent=4))
                        else:
                            log.debug(response.text)
                    return response

                return func
            return attr

    return req_wrap()
