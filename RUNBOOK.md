# Contents

Here is a quick reference to sections that may be of interest to you:

* [How to manage an outage](#how-to-manage-an-outage) - Things are broken, and I need to fix them now
* [Deployment Considerations](#deployment-considerations) - What do I need to configure to deploy this?
* [Resource Usage](#resource-usage) - How much resources do I expect this to take?
* [Troubleshooting](#troubleshooting) - How can I tell what is and isn't working easily?

# How to manage an outage
---

This purpose of this first section is the "its 3am, what should I do?"

This system is the following containers:

```
tfserving
config_manager
remote_model_puller
master
```

All of which have healthchecks and resolve their own state.

## What to do in an outage

### Is it an outage?

First determine if its an outage. 

* Are the containers up and healthy? Not an outage
* Is there just a couple restarts? Not an outage
* Are we seeing containers down or cascading restarts? Maybe


The only container that can cause issues short term is the `tfserving` container.

If any of the following containers are causing issues:

```
config_manager
remote_model_puller
master
```

it is not considered a true outage. Those containers being restarted/failing/stopped is fine.
Stop them if they are causing you issues and recommendations will investigate in the morning

## What to do if its an outage?

If the `tfserving` container is restarting on a single node. Then consider removing that node from
swarm. We can have 1 of many containers down with minimal impact.

If the `tfserving` container is cascading/failing on multiple/all nodes. There is most likely an issue
with the container that will require manual intervention. Please escalate the problem.

If `tfserving` is causing system wide issues. You can aways stop the service in docker swarm. This will
cause a lot of logging from the search side and cause recommendations alerts to go off.

Stopping the service in docker-swarm will cause increased load on elasticsearch for search, and will send an
error alert to Recommendations every 15 minutes. This should be considered a last resort policy.
## Who do I contact in an outage?

Contacts in order:

* Carl McGraw
* Zhihong Duan
* Max Anger
* Kip Obenauf
* Inga Evenchik

During business hours in order:
* use the [MS Teams Channel](https://teams.microsoft.com/l/channel/19%3aa9082b0cc21d471ba8fc8875d59d5027%40thread.tacv2/General?groupId=154e18bc-4408-477a-b528-e198e2d7d45b&tenantId=a918f95e-e7f2-4d57-9955-ebc85b9929d2), "@" the appropriate people
* use the email recommendations@accretivetg.com

After hours in order:
* Send a message to the [MS Teams Channel](https://teams.microsoft.com/l/channel/19%3aa9082b0cc21d471ba8fc8875d59d5027%40thread.tacv2/General?groupId=154e18bc-4408-477a-b528-e198e2d7d45b&tenantId=a918f95e-e7f2-4d57-9955-ebc85b9929d2) If no response in 5 minutes
* Use phone contact information on [confluence page](https://confluence.atg-corp.com/display/REC)

## Impact of an outage

When an outage is occurring, meaning `tfserving` containers are not available. The following events are expected:

* Calls from search -> Elasticsearch will attempt to call `tfserving` via gRPC (15-45 per request)
* These calls will hit a 600ms initial connection timeout (thus blocking in ES for 600ms, and tying up resources)
* Once more than 25% of inbound requests fail, ES will flip a killswitch stopping all requests from trying for 60 seconds
* After 60seconds ES will attempt again. The killswitch will flip immediately if requests are still failing
* Recommendations alerts will trigger on each unique killswitch in a 15 minute interval
* Search will fallback when timeouts or killswitches occur. Serving less than optimal results to users.

During the killswitch the load on ES is relatively low (but higher than normal). When the killswitch isn't active, but
there is an outage in `tfserving` containers, ES will tie threads up and cause search to lock apache threads too.

This resource stealing of ES and search can cause wide sweeping effects. The killswitch is designed to let the system
take a break, but it will still cause substantial resource holding inbetween killswitch activations.

## Deployment Considerations
---

The purpose of this section is to give some deployment considerations regarding the system. I assume in this section that you have some familiarity with what services are running this project. They are:

```
tfserving
config_manager
remote_model_puller
master
```

For more indepth details please visit the `swarm-deploy.yml` at the root of this project.

I am enumerating a list for each service on its shared dependencies. You can consider this a deployment checklist of things that need to be configured before the service is deployable and operational.

## `tfserving`

called by Elasticsearch via gRPC connections. It represents the machine learning model

1. container serves to Elasticsearch servers on a gRPC connection. Ensure that the ES servers in the environment can access the container through DNS entry `logginrec.mlmodels.icfsys.com`
1. uses gRPC connection on port `8500` for talking to Elasticsearch. Ensure that `8500` is mounted to the host
1. uses `/local_saved_models` internally to store model state. Ensure that the host volume is mounted in the container at the correct location. Should be referenced by envvar `$LOCAL_MODEL_DIRECTORY`
1. uses `/serving_config/models.config` internally to store config state. Ensure that the host volume is mounted in the container in the correct location. Should be referenced by envvar `$TENSORFLOW_SERVING_CONFIG_FILE`
1. Should run in global mode on each node. We shouldn't have a `tfserving` instance running without a `remote_model_puller` or `config_manager` also running on the same node!
1. Should have MOST of the node resources available to it. `remote_model_puller` and `config_manager` should be taking up just a small share of resources. The large share of resources should go to this container.

## `config_manager`

tracks what `tfserving` knows about, and keeps it up to date with available models, also removes models that are no longer valid to clean up disk space.

1. should be able to write to `/app/` dir on container filesystem to save down healthcheck information between threads
1. should have the `$HOSTNAME` envvar defined and passed to it. This envvar will let it register with the `master` node. Registration is the main way for `master` to track this container. It will reference it directly by its hostname to avoid load balancing
1. should have port `8002:8002` mapped to the host container. This is for communication with `master`. The `master` container will call it to initiate admin calls.
1. should have `$LOCAL_MODEL_DIRECTORY` as a volume mount on the host machine. It will share this with `tfserving` and `remote_model_puller`. This will allow `config_manager` to track what models are available
1. should have `$TENSORFLOW_SERVING_CONFIG_FILE` as a volume mount on the host machine. It will share this with `tfserving`. This will allow `config_manager` to update `tfserving` models that are available
1. should have `$TENSORFLOW_SERVING_GRPC_TARGET` available internal to the container. This will allow the `config_manager` to communicate with `tfserving` and determine which models it currently knows about

## `remote_model_puller`

tracks what models are available on a defined gcs bucket. Then pulls the most recent/current models down to local file system. This local file system is shared with `config_manager`

1. should be able to write to `/app/` dir on container filesystem to save down healthcheck information between threads
1. should have the `$HOSTNAME` envvar defined and passed to it. This envvar will let it register with the `master` node. Registration is the main way for `master` to track this container. It will reference it directly by its hostname to avoid load balancing
1. should have port `8001:8001` mapped to the host container. This is for communication with `master`. The `master` container will call it to initiate admin calls
1. should have access to gcp credentials at `$CLOUDSDK_CONFIG/application_default_credentials.json`
1. should have `$REMOTE_MODEL_DIRECTORY` as a volume mount on the host machine. It will use a remote GCS bucket at `$REMOTE_MODEL_DIRECTORY` to know current remote state.
1. should have `$LOCAL_MODEL_DIRECTORY` as a volume mount on the host machine. It will share this with `tfserving` and `remote_model_puller`. This will allow `remote_model_puller` to pull availalbe/valid models locally and share them with other containers

## `master`

Allows administrative operations to occur on the cluster. The `master` container keeps a list of registered `config_manager` and `remote_model_puller` nodes. It allows users to perform operations across the entire cluster, and to read/change remote model state as well.

1. should be able to write to `/app/` dir on container file system to save down registration information between thread
1. should be available on a DNS `mlmodelmanager.icfsys.com`, serving port `80`
1. should be running on only one node
1. should have access to gcp credentials at `$CLOUDSDK_CONFIG/application_default_credentials.json`

## Resource Usage
---

We anticipate the following resources used per container:

|service|mem|cpu|net io|disk io|
|-------|---|---|------|-------|
|`tfserving` | ~12gb | high | medium | low |
|`config_manager` | 500mb | low | low | low |
|`remote_model_puller` | 500mb | low | medium | medium |
|`master` | 500mb | low | low | low |

We anticipate the following request loads

|service|type|reqps|connections| external to docker? |
|-------|----|-----|-----------|---------------------|
|`tfserving` | grpc | 5k> | ~20 | yes via DNS entry / docker load balancer |
|`config_manager` | http | <1 | 1 | no |
|`remote_model_puller` | http | <1 | 1 | no |
|`master` | http | <1 | 1 | yes - internal to ATG via DNS entry / docker load balancer |

## Troubleshooting

How to check if everything is or isn't working.

All containers carry healthchecks on them that check their state for internal consistency. If the container fails it healthcheck then it will eventually restart and thus shouldn't cause an issue.
