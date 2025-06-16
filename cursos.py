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


def obter_nomes_por_ids(ids: List[int]) -> List[str]:
    """Retorna os nomes de cursos correspondentes aos IDs fornecidos."""
    if not ids:
        return []

    ids_set = set(ids)

    # Verifica se existe algum curso com conjunto de IDs exatamente igual
    nomes_exatos = [n for n, lista in CURSOS_OM.items() if set(lista) == ids_set]
    if nomes_exatos:
        return nomes_exatos

    # Caso contrário, inclui nomes de cursos que contenham qualquer um dos IDs
    nomes: List[str] = []
    for cid in ids:
        for nome, lista in CURSOS_OM.items():
            if cid in lista and nome not in nomes:
                nomes.append(nome)

    return nomes

# Aceita /cursos e /cursos/
@router.get("", summary="Lista de cursos disponíveis")
@router.get("/", summary="Lista de cursos disponíveis")
async def listar_cursos():
    """Retorna o mapeamento de cursos do CED para as disciplinas da OM."""
    return {"cursos": CURSOS_OM}
