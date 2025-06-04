from fastapi import APIRouter
import json
from pathlib import Path

router = APIRouter()

# Caminho para o arquivo JSON com todos os cursos da Ouro Moderno
_JSON_PATH = Path(__file__).with_name("cursos_om.json")

# Cache interno para evitar releitura do arquivo a cada requisição
_cached_data = None

def _load_cursos() -> dict:
    global _cached_data
    if _cached_data is None:
        with _JSON_PATH.open("r", encoding="utf-8") as f:
            _cached_data = json.load(f)
    return _cached_data


@router.get("/", summary="Lista de todos os cursos da Ouro Moderno")
async def listar_cursos_om():
    """Retorna o conteúdo do arquivo de cursos da Ouro Moderno."""
    return _load_cursos()
