import json
import sys
sys.path.insert(0, '/opt/CortexCloudAPI')
from app.x402.pricing import ROUTE_PRICING  # single source of truth for prices

with open('/opt/CortexCloudAPI/openapi.json', 'r') as f:
    spec = json.load(f)

# Ensure paths exist
if 'paths' not in spec:
    spec['paths'] = {}

# Add /x402/v1/search
spec['paths']['/x402/v1/search'] = {
    'post': {
        'operationId': 'exa_search',
        'summary': 'Web search via Exa AI (x402 payment-gated)',
        'description': 'Returns HTTP 402 with an x402 PaymentRequirements challenge (USDC on Base) unless a valid X-PAYMENT header is supplied.',
        'x-payment-info': {
            'price': {'mode': 'fixed', 'currency': 'USD', 'amount': ROUTE_PRICING['POST /x402/v1/search'].lstrip('$')},
            'protocols': [{'x402': {}}]
        },
        'requestBody': {
            'required': True,
            'content': {
                'application/json': {
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'query': {'type': 'string', 'description': 'Search query'},
                            'numResults': {'type': 'integer', 'description': 'Number of results to return', 'default': 10},
                            'useAutoprompt': {'type': 'boolean', 'description': 'Use autoprompt for better results'},
                            'type': {'type': 'string', 'enum': ['neural', 'keyword'], 'description': 'Search type'},
                            'includeDomains': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Domains to include'},
                            'excludeDomains': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Domains to exclude'},
                            'startPublishedDate': {'type': 'string', 'description': 'Start date for published content (ISO format)'},
                            'endPublishedDate': {'type': 'string', 'description': 'End date for published content (ISO format)'}
                        },
                        'required': ['query']
                    }
                }
            }
        },
        'responses': {
            '200': {'description': 'Result (after valid x402 payment)'},
            '402': {'description': 'Payment Required — x402 PaymentRequirements challenge'}
        }
    }
}

# Add /x402/v1/search/contents
spec['paths']['/x402/v1/search/contents'] = {
    'post': {
        'operationId': 'exa_search_contents',
        'summary': 'Fetch content for search result IDs via Exa AI (x402 payment-gated)',
        'description': 'Returns HTTP 402 with an x402 PaymentRequirements challenge (USDC on Base) unless a valid X-PAYMENT header is supplied.',
        'x-payment-info': {
            'price': {'mode': 'fixed', 'currency': 'USD', 'amount': ROUTE_PRICING['POST /x402/v1/search/contents'].lstrip('$')},
            'protocols': [{'x402': {}}]
        },
        'requestBody': {
            'required': True,
            'content': {
                'application/json': {
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'ids': {
                                'type': 'array',
                                'items': {'type': 'string'},
                                'description': 'Result IDs to fetch content for'
                            },
                            'text': {'type': 'boolean', 'description': 'Include text content', 'default': True},
                            'summary': {'type': 'boolean', 'description': 'Include summary', 'default': True},
                            'highlights': {'type': 'boolean', 'description': 'Include highlights', 'default': False}
                        },
                        'required': ['ids']
                    }
                }
            }
        },
        'responses': {
            '200': {'description': 'Result (after valid x402 payment)'},
            '402': {'description': 'Payment Required — x402 PaymentRequirements challenge'}
        }
    }
}

# Sync x-payment-info.amount for every paid operation from ROUTE_PRICING so
# static metadata can never drift from runtime 402 amounts again.
synced = 0
for path, methods in spec.get('paths', {}).items():
    for method, op in methods.items():
        key = f"{method.upper()} {path}"
        price = ROUTE_PRICING.get(key)
        if price and op.get('x-payment-info', {}).get('price', {}).get('amount'):
            op['x-payment-info']['price']['amount'] = price.lstrip('$')
            synced += 1
print(f'Synced {synced} x-payment-info amounts from ROUTE_PRICING')

# Write back
with open('/opt/CortexCloudAPI/openapi.json', 'w') as f:
    json.dump(spec, f, indent=2)
print('Updated OpenAPI spec with search endpoints')