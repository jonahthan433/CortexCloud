#!/usr/bin/env bash
# Free estimate: portfolio selection (pick 5 of 8 assets).
set -euo pipefail
curl -s https://api.cortexcloud.org/v1/estimate \
  -H 'content-type: application/json' \
  -d '{"problem_type":"qubo","n":8,"data":{"linear":[0.9,-0.7,1.2,-1.1,0.6,-0.4,1.0,-0.8],"quadratic":{"0,1":0.3,"2,3":-0.6,"4,5":0.2,"6,7":-0.4}}}' | python3 -m json.tool
