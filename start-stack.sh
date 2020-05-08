#! /usr/bin/env bash
echo "checking for required dependencies!"
_=$(docker --help && docker-compose --help && docker stack --help)
if [[ $? != 0 ]]; then
    echo "unable to find docker, docker-compose or docker stack"
    echo "please install these dependencies for this script to work"
    echo ""
    exit 1
fi

cd "$(dirname "$0")"
set -a
source .env
set +a
export MONGO_VOLUME_MOUNT_DIR=$(pwd)/mongo/data
echo "mongo data dir = $MONGO_VOLUME_MOUNT_DIR"

echo "checking for current running streambot"
_=$(docker stack ls | grep 'mlmodelstatemanager')
if [[ $? == 0 ]]; then
    echo "noticed running mlmodelstatemanager"
    echo "stopping..."
    docker stack rm mlmodelstatemanager
    sleep 10
    echo "done"
fi

set -eu

docker-compose --file "./docker-compose.yml" build
echo "checking for existing proxy network"
_=$(docker network ls | grep 'proxy')
if [[ $? != 0 ]]; then
    echo "creating external proxy network"
    docker network create --driver overlay proxy --subnet 10.1.0.0/16
    echo "proxy network created"
fi
echo ""
echo "deploying docker stack"
docker stack deploy -c "./docker-compose-deploy.yml" mlmodelstatemanager
sleep 10

echo "finished deploy docker stack. Manager should be up and running now"
