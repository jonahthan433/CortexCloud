"""
x402 payment-gated Exa AI search endpoints.
"""
import json
import logging
import httpx
from fastapi import APIRouter, Request, Header, HTTPException, status
from fastapi.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger("cortexcloud.x402.search")

router = APIRouter()

# Per-route JSON input/output schemas for the x402 v2 Bazaar discovery
# extension. Required by x402scan's validator (SCHEMA_INPUT_MISSING is a hard
# error if the 402 body lacks an input schema).
BAZAAR_SCHEMAS = {
    "/x402/v1/search": {
        "input": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "numResults": {"type": "integer", "description": "Number of results to return", "default": 10},
                "useAutoprompt": {"type": "boolean", "description": "Use autoprompt for better results"},
                "type": {"type": "string", "enum": ["neural", "keyword"], "description": "Search type"},
                "includeDomains": {"type": "array", "items": {"type": "string"}, "description": "Domains to include"},
                "excludeDomains": {"type": "array", "items": {"type": "string"}, "description": "Domains to exclude"},
                "startPublishedDate": {"type": "string", "description": "Start date for published content (ISO format)"},
                "endPublishedDate": {"type": "string", "description": "End date for published content (ISO format)"},
            },
            "required": ["query"]
        },
        "output": {
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "url": {"type": "string"},
                            "id": {"type": "string"},
                            "publishedDate": {"type": "string"},
                            "author": {"type": "string"},
                            "text": {"type": "string"},
                            "score": {"type": "number"}
                        }
                    }
                },
                "query": {"type": "string"},
                "requestId": {"type": "string"}
            }
        }
    },
    "/x402/v1/search/contents": {
        "input": {
            "type": "object",
            "properties": {
                "ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Result IDs to fetch content for"
                },
                "text": {"type": "boolean", "description": "Include text content", "default": True},
                "summary": {"type": "boolean", "description": "Include summary", "default": True},
                "highlights": {"type": "boolean", "description": "Include highlights", "default": False}
            },
            "required": ["ids"]
        },
        "output": {
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                            "url": {"type": "string"},
                            "publishedDate": {"type": "string"},
                            "author": {"type": "string"},
                            "text": {"type": "string"},
                            "summary": {"type": "string"},
                            "highlights": {"type": "object"}
                        }
                    }
                }
            }
        }
    }
}

@router.post("/search")
async def exa_search(
    request: Request,
    x_correlation_id: str = Header(None, alias="x-correlation-id"),
):
    """
    Exa web search endpoint (x402 payment-gated).
    Fixed price: $0.015 per search.
    """
    # Read and parse request body
    body = await request.body()
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    # Validate required fields
    query = data.get("query")
    if not query:
        raise HTTPException(status_code=400, detail="Missing required field: query")
    
    # Prepare Exa API request
    exa_payload = {
        "query": query,
        "numResults": data.get("numResults", 10),
        "useAutoprompt": data.get("useAutoprompt", False),
        "type": data.get("type", "neural"),
    }
    
    # Add optional filters if provided
    if data.get("includeDomains"):
        exa_payload["includeDomains"] = data["includeDomains"]
    if data.get("excludeDomains"):
        exa_payload["excludeDomains"] = data["excludeDomains"]
    if data.get("startPublishedDate"):
        exa_payload["startPublishedDate"] = data["startPublishedDate"]
    if data.get("endPublishedDate"):
        exa_payload["endPublishedDate"] = data["endPublishedDate"]
    
    # Call Exa API
    exa_api_key = settings.EXA_API_KEY
    if not exa_api_key:
        logger.error("EXA_API_KEY not configured")
        raise HTTPException(status_code=500, detail="Search service not configured")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.exa.ai/search",
                json=exa_payload,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": exa_api_key
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Exa API error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Search provider error: {response.status_code}"
                )
            
            exa_result = response.json()
            
            # Format response to match expected schema
            formatted_result = {
                "results": [
                    {
                        "title": result.get("title", ""),
                        "url": result.get("url", ""),
                        "id": result.get("id", ""),
                        "publishedDate": result.get("publishedDate"),
                        "author": result.get("author"),
                        "text": result.get("text"),
                        "score": result.get("score")
                    }
                    for result in exa_result.get("results", [])
                ],
                "query": query,
                "requestId": exa_result.get("requestId", "")
            }
            
            return JSONResponse(content=formatted_result)
            
    except httpx.TimeoutException:
        logger.error("Exa API timeout")
        raise HTTPException(status_code=504, detail="Search service timeout")
    except Exception as e:
        logger.error(f"Exa API error: {e}")
        raise HTTPException(status_code=502, detail="Search service unavailable")

@router.post("/search/contents")
async def exa_search_contents(
    request: Request,
    x_correlation_id: str = Header(None, alias="x-correlation-id"),
):
    """
    Exa contents endpoint (x402 payment-gated).
    Fixed price: $0.005 per content fetch.
    """
    # Read and parse request body
    body = await request.body()
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    # Validate required fields
    ids = data.get("ids")
    if not ids or not isinstance(ids, list):
        raise HTTPException(status_code=400, detail="Missing or invalid field: ids (must be array)")
    
    # Prepare Exa API request
    exa_payload = {
        "ids": ids,
        "text": data.get("text", True),
        "summary": data.get("summary", True),
        "highlights": data.get("highlights", False)
    }
    
    # Call Exa API
    exa_api_key = settings.EXA_API_KEY
    if not exa_api_key:
        logger.error("EXA_API_KEY not configured")
        raise HTTPException(status_code=500, detail="Search service not configured")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.exa.ai/contents",
                json=exa_payload,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": exa_api_key
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Exa contents API error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=502,
                    detail=f"Search provider error: {response.status_code}"
                )
            
            exa_result = response.json()
            
            # Format response to match expected schema
            formatted_result = {
                "results": [
                    {
                        "id": result.get("id", ""),
                        "title": result.get("title", ""),
                        "url": result.get("url", ""),
                        "publishedDate": result.get("publishedDate"),
                        "author": result.get("author"),
                        "text": result.get("text"),
                        "summary": result.get("summary"),
                        "highlights": result.get("highlights")
                    }
                    for result in exa_result.get("results", [])
                ]
            }
            
            return JSONResponse(content=formatted_result)
            
    except httpx.TimeoutException:
        logger.error("Exa contents API timeout")
        raise HTTPException(status_code=504, detail="Search service timeout")
    except Exception as e:
        logger.error(f"Exa contents API error: {e}")
        raise HTTPException(status_code=502, detail="Search service unavailable")