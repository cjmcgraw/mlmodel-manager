#! /usr/bin/env bash
function usage() {
    echo "$0 args"
    echo ""
    echo "This script is used to up the docker-compose stack, and run"
    echo "the tests associated with this repository"
    echo ""
    echo "required arguments:"
    echo "  --skip-port-bindings"
}

skip_port_bindings=''
while [ $# > 1 ];do case $1 in
    --skip-port-bindings) skip_port_bindings="true" ;;
    --help) usage; exit 0 ;;
    *) break ;;
esac; shift; shift; done

docker_compose_file="docker-compose.yml"
if [[ $skip_port_bindings ]]; then
    echo "skip port bindings flag used"
    echo ""
    echo "modifying docker-compose to remove ports bindings"
    echo "the reason that we need to do this is because the"
    echo "build host is not okay with having ports mapped"
    echo ""
    cat docker-compose.yml | sed -E '/^[[:space:]]+ports:/d;/- [0-9]+:[0-9]+/d' > docker-compose-test.yml
    echo "running with updated docker-compose-test.yml:"
    cat docker-compose-test.yml
    docker_compose_file="docker-compose-test.yml"
    echo ""
    echo ""
fi


trap "docker-compose -f $docker_compose_file rm --stop --force" EXIT

echo "upping services"
docker-compose -f $docker_compose_file up --build -d mongo manager
echo "waiting for services to come up..."
sleep 10 
echo "done"

echo "running test container"
docker-compose -f $docker_compose_file run test_container
if [[ ! $? == 0 ]]; then
    echo "running log statements"
    docker-compose -f $docker_compose_file logs

    echo "checking container state"
    docker-compose -f $docker_compose_file ps -a
    exit 1
fi
