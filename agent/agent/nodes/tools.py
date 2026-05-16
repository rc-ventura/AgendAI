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
    return json.dumps({
        "sucesso": True,
        "mensagem": "Consulta agendada com sucesso!",
        "agendamento_id": result["id"],
        "paciente_nome": result["paciente"]["nome"],
        "paciente_email": result["paciente"]["email"],
        "medico_nome": result["medico"]["nome"],
        "data_hora": dt,
    }, ensure_ascii=False)


@tool
async def cancelar_agendamento(agendamento_id: int) -> str:
    """Cancela um agendamento existente.
    Use quando o paciente solicitar cancelamento. Requer o ID numérico do agendamento.
    """
    client = get_client()
    detalhes = await client.buscar_agendamento(agendamento_id)
    await client.cancelar_agendamento(agendamento_id)
    dt = detalhes["horario"]["data_hora"].replace("T", " ")
    return json.dumps({
        "sucesso": True,
        "mensagem": "Agendamento cancelado com sucesso.",
        "agendamento_id": agendamento_id,
        "paciente_nome": detalhes["paciente"]["nome"],
        "paciente_email": detalhes["paciente"]["email"],
        "medico_nome": detalhes["medico"]["nome"],
        "data_hora": dt,
    }, ensure_ascii=False)


@tool
async def buscar_pagamentos() -> str:
    """Retorna valores de consulta e formas de pagamento aceitas.
    Use quando o paciente perguntar sobre preços ou como pagar.
    """
    client = get_client()
    pagamentos = await client.buscar_pagamentos()
    if not pagamentos:
        return json.dumps({"disponivel": False, "mensagem": "Informações de pagamento não disponíveis."})
    p = pagamentos[0]
    formas = json.loads(p["formas"]) if isinstance(p["formas"], str) else p["formas"]
    return json.dumps({
        "disponivel": True,
        "descricao": p["descricao"],
        "valor": p["valor"],
        "formas_pagamento": formas,
    }, ensure_ascii=False)


@tool
async def buscar_agendamentos_paciente(email: str, status: str | None = None) -> str:
    """Busca os agendamentos de um paciente pelo e-mail.
    Use quando o paciente perguntar sobre suas consultas agendadas ou quiser cancelar mas não souber o ID.
    Parâmetro status opcional: 'ativo' para filtrar apenas consultas ativas.
    """
    client = get_client()
    agendamentos = await client.listar_agendamentos_paciente(email, status)
    if not agendamentos:
        msg = "Nenhum agendamento encontrado"
        msg += f" com status '{status}'" if status else ""
        msg += f" para {email}."
        return json.dumps({"disponivel": False, "mensagem": msg})
    linhas = []
    for a in agendamentos:
        dt = a["horario"]["data_hora"].replace("T", " ")
        linhas.append(
            f"• ID {a['id']} — {dt} | {a['medico']['nome']} | status: {a['status']}"
        )
    return json.dumps({
        "disponivel": True,
        "total": len(agendamentos),
        "agendamentos": linhas,
    }, ensure_ascii=False)


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
    buscar_agendamentos_paciente,
    criar_agendamento,
    cancelar_agendamento,
    buscar_pagamentos,
    buscar_paciente,
]

tool_node = ToolNode(ALL_TOOLS)
