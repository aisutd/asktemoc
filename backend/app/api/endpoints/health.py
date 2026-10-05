from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

# Both /api/health and /api/health/ answer directly: a redirect between them
# breaks browser fetches behind HTTPS proxies (Cloud Run redirects to http://).
@router.get("", response_model=dict)
@router.get("/", response_model=dict, include_in_schema=False)
async def health_check():
    """
    Health check endpoint to verify backend is running.
    Returns a simple success response with HTTP 200 status.
    """
    return JSONResponse(
        status_code=200,
        content={"status": "healthy"}
    )