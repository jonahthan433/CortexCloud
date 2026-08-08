#!/usr/bin/env bash
# Free estimate: scheduling problem (4 jobs, pairwise conflicts).
set -euo pipefail
curl -s https://api.cortexcloud.org/v1/estimate \
  -H 'content-type: application/json' \
  -d '{"problem_type":"qubo","n":4,"data":{"linear":[1,-2,3,-4],"quadratic":{"0,1":-1.5,"1,2":2.0,"2,3":-0.5}}}' | python3 -m json.tool
