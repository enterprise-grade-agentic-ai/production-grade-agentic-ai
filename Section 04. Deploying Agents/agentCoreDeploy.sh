#!/bin/bash

source .venv/bin/activate
uv pip freeze --exclude-editable > requirements.txt

FILE=".env"
# Check if the file exists
if [ ! -f "$FILE" ]; then
    echo "Error: File '$FILE' not found."
    exit 1
fi

command="agentcore launch --auto-update-on-conflict" 
cat ${FILE} | (while read line || [[ -n $line ]];
do
   # echo ${line}
   command+=" --env ${line}"
   # echo "${command}"
done && eval $command)