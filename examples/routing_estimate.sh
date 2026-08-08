#!/usr/bin/env bash
# Free estimate: delivery routing (6 stops, pairwise travel costs).
set -euo pipefail
curl -s https://api.cortexcloud.org/v1/estimate \
  -H 'content-type: application/json' \
  -d '{"problem_type":"qubo","n":6,"data":{"linear":[0,0,0,0,0,0],"quadratic":{"0,1":4.2,"0,2":2.1,"1,3":3.8,"2,4":1.9,"3,5":2.7,"4,5":3.3}}}' | python3 -m json.tool
