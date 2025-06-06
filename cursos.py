from fastapi import APIRouter
from typing import Dict, List

router = APIRouter()

# Mapeamento de nomes de cursos do CED para os IDs de disciplinas na OM
CURSOS_OM: Dict[str, List[int]] = {
    "Excel PRO": [161, 197, 201],
    "Design Gráfico": [254, 751, 169],
    "Analista e Desenvolvimento de Sistemas": [590, 176, 239, 203],
    "Administração": [129, 198, 156, 154],
    "Inglês Fluente": [263, 280, 281],
    "Inglês Kids": [266],
    "Informática Essencial": [130, 599, 161, 160, 162],
    "Operador de Micro": [130, 599, 160, 161, 162, 163, 222],
    "Especialista em Marketing & Vendas 360º": [123, 199, 202, 236, 264, 441, 734, 780, 828, 829],
    "Marketing Digital": [734, 236, 441, 199, 780],
    "Pacote Office": [160, 161, 162, 197, 201],
    "None": [129, 198, 156, 154],
}

@router.get("/", summary="Lista de cursos disponíveis")
async def listar_cursos():
    """Retorna o mapeamento de cursos do CED para as disciplinas da OM."""
    return {"cursos": CURSOS_OM}
