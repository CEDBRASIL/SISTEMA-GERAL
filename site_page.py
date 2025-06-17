from fastapi import APIRouter
from fastapi.responses import HTMLResponse
import os

router = APIRouter()

SITE_FILE = os.path.join(os.path.dirname(__file__), "site.html")


@router.get("/site", response_class=HTMLResponse, include_in_schema=False)
async def get_site():
    """Retorna a página de teste."""
    try:
        with open(SITE_FILE, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return HTMLResponse("Site não encontrado", status_code=404)
    return HTMLResponse(content)
