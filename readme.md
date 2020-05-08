# MLModel Manager
This project is a webservice that manages machine learning models being served to
production.

The purpose of this project is relatively simple. I needed the ability to dynamically 
serve production read machine learning docker containers to an environment where they 
could be communicated with, at scale, with the external world. The implementation of 
doing this is actually quite complicated though. It relies heavily on the underlying 
technology that you are using. Because of this, this project exists as an abstraction 
to hide the logic behind what the implementation is doing.

We can always run a get command to the main host. For this example I will be heavily
using [httpie](https://httpie.org/) to run requests. When hitting endpoints using chrome
it is highly recommended you consider using [this specific json
formatter](https://chrome.google.com/webstore/detail/json-viewer-awesome/iemadiahhbebdklepanmkjenfdebfpfe?hl=en)

```
$ http -v localhost/

GET / HTTP/1.1
Accept: */*
Accept-Encoding: gzip, deflate
Connection: keep-alive
Host: localhost
User-Agent: HTTPie/2.0.0



HTTP/1.1 200 OK
content-length: 2
content-type: application/json
date: Wed, 15 Apr 2020 06:30:44 GMT
server: uvicorn

[]

```

We can create a deployment by taking a known existing model and posting it into the
endpoint, providing the required data by the endpoint.

```
$ http -v post 'localhost/carls_model' <<< '{"domain": "carls_model.com", "build_id": "some_build_id", "run_id": "some_run_id", "image": "qarlm/static-http-response-server", "port": 80}'
POST /carls_model HTTP/1.1
Accept: application/json, */*
Accept-Encoding: gzip, deflate
Connection: keep-alive
Content-Length: 142
Content-Type: application/json
Host: localhost
User-Agent: HTTPie/2.0.0

{
    "build_id": "some_build_id",
    "domain": "carls_model.com",
    "image": "qarlm/static-http-response-server",
    "port": 80,
    "run_id": "some_run_id"
}

HTTP/1.1 200 OK
content-length: 1543
content-type: application/json
date: Wed, 15 Apr 2020 06:33:13 GMT
server: uvicorn

{
    "build_id": "some_build_id",
    "containers": [],
    "cpu_limit": "1",
    "cpu_reservation": "0.1",
    "deploy_delay": "5s",
    "deploy_monitor_period": "30s",
    "deployment_id": "839e2353728e476d9a6da2f5f781e908",
    "deployment_time": 1586932393.268678,
    "domain": "carls_model.com",
    "extra_template_attributes": {},
    "image": "qarlm/static-http-response-server",
    "mem_limit": "2G",
    "mem_reservation": "1G",
    "name": "carls_model",
    "port": 80,
    "rendered_template": <truncated>,
    "run_id": "some_run_id",
    "scale": 2,
    "swarm_services": [],
    "template_file": "default.template.yml"
}
```

Now. If your template is setup correctly you should see a machine learning model being
served on port `80`, on `carls_model.com`. What is being served is
`qarlm/static-http-response-server` which is a server I wrote for testing purposes that
returns a static http response.

Calling to out main endpoint again we see that we retrieve a list of running services
and the service called `carls_model` is now both valid (meaning it has a known record)
and it is active, meaning that it is being served to production.

```
$ http -v localhost/
GET / HTTP/1.1
Accept: */*
Accept-Encoding: gzip, deflate
Connection: keep-alive
Host: localhost
User-Agent: HTTPie/2.0.0



HTTP/1.1 200 OK
content-length: 51
content-type: application/json
date: Wed, 15 Apr 2020 06:37:49 GMT
server: uvicorn

[
    {
        "active": true,
        "name": "carls_model",
        "valid": true
    }
]

```

We can retrieve more fine grained details regarding the deployment and its history
by passing the `n=` parameter that will let us look through the history of deployments.
Curling to the endpoint looking at `carls_model` now shows us:

```
$ http -v localhost/carls_model
GET /carls_model HTTP/1.1
Accept: */*
Accept-Encoding: gzip, deflate
Connection: keep-alive
Host: localhost
User-Agent: HTTPie/2.0.0



HTTP/1.1 200 OK
content-length: 2022
content-type: application/json
date: Wed, 15 Apr 2020 06:39:30 GMT
server: uvicorn

[
    {
        "build_id": "some_build_id",
        "containers": [
            {
                "current_state": "Running 6 minutes ago",
                "desired_state": "Running",
                "error": "",
                "image": "qarlm/static-http-response-server:latest",
                "name": "mlmodel_carls_model_mlmodel.1",
                "node": "docker-desktop"
            },
            {
                "current_state": "Running 6 minutes ago",
                "desired_state": "Running",
                "error": "",
                "image": "qarlm/static-http-response-server:latest",
                "name": "mlmodel_carls_model_mlmodel.2",
                "node": "docker-desktop"
            }
        ],
        "cpu_limit": "1",
        "cpu_reservation": "0.1",
        "deploy_delay": "5s",
        "deploy_monitor_period": "30s",
        "deployment_id": "839e2353728e476d9a6da2f5f781e908",
        "deployment_time": "1586932393.268678",
        "domain": "carls_model.com",
        "extra_template_attributes": {},
        "image": "qarlm/static-http-response-server",
        "mem_limit": "2G",
        "mem_reservation": "1G",
        "name": "carls_model",
        "port": 80,
        "rendered_template": <truncated>,
        "run_id": "some_run_id",
        "scale": 2,
        "swarm_services": [
            {
                "image": "qarlm/static-http-response-server:latest",
                "name": "carls_model",
                "replicas": "2/2"
            }
        ],
        "template_file": "default.template.yml"
    }
]
```

we can now see more fine grained detail regarding the deployment. Specifically we can
see the current swarm services, and their replicas. We can also see the current
container state of the last known containers associated with this build.

finally now that I have deployed the service, I can stop it by deleteing the resource
associated with the deployment. I can always pass the `clear_all_records=true` parameter
if I'd like all of the associated records to be wiped forever.

```
http -v delete localhost/carls_model
DELETE /carls_model HTTP/1.1
Accept: */*
Accept-Encoding: gzip, deflate
Connection: keep-alive
Content-Length: 0
Host: localhost
User-Agent: HTTPie/2.0.0



HTTP/1.1 200 OK
content-length: 2040
content-type: application/json
date: Wed, 15 Apr 2020 06:43:44 GMT
server: uvicorn

{
    "deployments": [
        {
            "build_id": "some_build_id",
            "containers": [
                {
                    "current_state": "Running 10 minutes ago",
                    "desired_state": "Running",
                    "error": "",
                    "image": "qarlm/static-http-response-server:latest",
                    "name": "mlmodel_carls_model_mlmodel.1",
                    "node": "docker-desktop"
                },
                {
                    "current_state": "Running 10 minutes ago",
                    "desired_state": "Running",
                    "error": "",
                    "image": "qarlm/static-http-response-server:latest",
                    "name": "mlmodel_carls_model_mlmodel.2",
                    "node": "docker-desktop"
                }
            ],
            "cpu_limit": "1",
            "cpu_reservation": "0.1",
            "deploy_delay": "5s",
            "deploy_monitor_period": "30s",
            "deployment_id": "839e2353728e476d9a6da2f5f781e908",
            "deployment_time": "1586932393.268678",
            "domain": "carls_model.com",
            "extra_template_attributes": {},
            "image": "qarlm/static-http-response-server",
            "mem_limit": "2G",
            "mem_reservation": "1G",
            "name": "carls_model",
            "port": 80,
            "rendered_template": <truncated>,
            "run_id": "some_run_id",
            "scale": 2,
            "swarm_services": [
                {
                    "image": "qarlm/static-http-response-server:latest",
                    "name": "carls_model",
                    "replicas": "2/2"
                }
            ],
            "template_file": "default.template.yml"
        }
    ]
}

```

Now running the previous get command to get fine grained detail shows us the service is
no longer active in swarm, and its containers have since stopped.

```
http -v localhost/carls_model                                                       <<<
GET /carls_model HTTP/1.1
Accept: */*
Accept-Encoding: gzip, deflate
Connection: keep-alive
Host: localhost
User-Agent: HTTPie/2.0.0



HTTP/1.1 200 OK
content-length: 1547
content-type: application/json
date: Wed, 15 Apr 2020 06:44:45 GMT
server: uvicorn

[
    {
        "build_id": "some_build_id",
        "containers": [],
        "cpu_limit": "1",
        "cpu_reservation": "0.1",
        "deploy_delay": "5s",
        "deploy_monitor_period": "30s",
        "deployment_id": "839e2353728e476d9a6da2f5f781e908",
        "deployment_time": "1586932393.268678",
        "domain": "carls_model.com",
        "extra_template_attributes": {},
        "image": "qarlm/static-http-response-server",
        "mem_limit": "2G",
        "mem_reservation": "1G",
        "name": "carls_model",
        "port": 80,
        "rendered_template": <truncated>,
        "run_id": "some_run_id",
        "scale": 2,
        "swarm_services": [],
        "template_file": "default.template.yml"
    }
]
```
