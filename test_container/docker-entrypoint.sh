#! /usr/bin/env bash
# Lets run all the tests in this directory as main functions!
cd /app/
echo "installing pip dependencies"
pip3 install -r requirements.txt
echo "finished installing pip dependencies"
echo ""
set -eu
set -o pipefail
files_to_run="$@"

if [[ -z $files_to_run ]]; then
    files_to_run=$(ls | grep '^test.*\.py$')
fi
echo "running over the following files: $files_to_run"

uuid="$(date +%s)"
run_directory="./runs/$uuid"
mkdir -p $run_directory
echo "setup run directory at $run_directory"

echo "checking for test scripts, and executing them"
sleep 5 
for test_script in $files_to_run; do
    echo "found test_script: $test_script"
    if [[ -f $test_script ]]; then
        echo "running python $test_script"
        python3 $test_script | tee $run_directory/$(echo "$test_script" | sed 's/.py$/.log/')
        echo "finished running $test_script"
        echo ""
    fi
done
