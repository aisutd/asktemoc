from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

@router.get("/", response_model=dict)
async def health_check():
    """
    Health check endpoint to verify backend is running.
    Returns a simple success response with HTTP 200 status.
    """
    return JSONResponse(
        status_code=200,
        content={"status": "healthy"}
    )