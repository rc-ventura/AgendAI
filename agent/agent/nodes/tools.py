import json
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode

from agent.api_client import get_client


@tool
async def buscar_horarios_disponiveis(data: str | None = None) -> str:
    """Busca horários médicos disponíveis para agendamento.
    Use quando o paciente perguntar sobre horários ou datas disponíveis.
    Parâmetro data opcional no formato YYYY-MM-DD para filtrar por data específica.
    """
    client = get_client()
    horarios = await client.buscar_horarios(data=data)
    if not horarios:
        return "Não há horários disponíveis" + (f" para {data}." if data else ".")
    linhas = []
    for h in horarios:
        dt = h["data_hora"].replace("T", " ")
        medico = h["medico"]
        linhas.append(
            f"• ID {h['id']} — {dt} | {medico['nome']} ({medico['especialidade']})"
        )
    return "Horários disponíveis:\n" + "\n".join(linhas)


@tool
async def criar_agendamento(paciente_email: str, horario_id: int) -> str:
    """Agenda uma consulta para o paciente em um horário disponível.
    Use após o paciente confirmar o horário desejado.
    Requer e-mail cadastrado do paciente e ID do horário (obtido de buscar_horarios_disponiveis).
    """
    client = get_client()
    result = await client.criar_agendamento(paciente_email, horario_id)
    dt = result["horario"]["data_hora"].replace("T", " ")
    return (
        f"Consulta agendada com sucesso! ID do agendamento: {result['id']}. "
        f"Paciente: {result['paciente']['nome']} | "
        f"Médico: {result['medico']['nome']} | "
        f"Data/hora: {dt}"
    )


@tool
async def cancelar_agendamento(agendamento_id: int) -> str:
    """Cancela um agendamento existente.
    Use quando o paciente solicitar cancelamento. Requer o ID numérico do agendamento.
    """
    client = get_client()
    result = await client.cancelar_agendamento(agendamento_id)
    return f"Agendamento {result['id']} cancelado com sucesso."


@tool
async def buscar_pagamentos() -> str:
    """Retorna valores de consulta e formas de pagamento aceitas.
    Use quando o paciente perguntar sobre preços ou como pagar.
    """
    client = get_client()
    pagamentos = await client.buscar_pagamentos()
    if not pagamentos:
        return "Informações de pagamento não disponíveis."
    p = pagamentos[0]
    formas = json.loads(p["formas"]) if isinstance(p["formas"], str) else p["formas"]
    return (
        f"{p['descricao']}: R$ {p['valor']:.2f}\n"
        f"Formas de pagamento aceitas: {', '.join(formas)}"
    )


@tool
async def buscar_paciente(email: str) -> str:
    """Busca os dados de um paciente pelo e-mail.
    Use para confirmar se o e-mail está cadastrado antes de criar um agendamento.
    """
    client = get_client()
    result = await client.buscar_paciente(email)
    if "erro" in result:
        return f"Paciente não encontrado para o e-mail: {email}. Verifique o e-mail informado."
    return f"Paciente encontrado: {result['nome']} (e-mail: {result['email']})"


ALL_TOOLS = [
    buscar_horarios_disponiveis,
    criar_agendamento,
    cancelar_agendamento,
    buscar_pagamentos,
    buscar_paciente,
]

tool_node = ToolNode(ALL_TOOLS)
