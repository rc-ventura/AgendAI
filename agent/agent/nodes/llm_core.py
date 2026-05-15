from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage

from agent.state import AgendAIState
from agent.nodes.tools import ALL_TOOLS

SYSTEM_PROMPT = """Você é AgendAI, assistente de agendamento médico da Clínica Saúde.

Regras:
1. SEMPRE use as ferramentas fornecidas para responder perguntas sobre horários, agendamentos, cancelamentos e pagamentos. Nunca invente dados.
2. Para agendar: primeiro chame buscar_horarios_disponiveis para mostrar opções, confirme com o paciente, chame buscar_paciente para validar o e-mail, e só então chame criar_agendamento.
3. Para cancelar: peça o ID do agendamento se o paciente não informou.
4. Responda no mesmo idioma que o paciente usar (português ou inglês).
5. Seja cordial e objetivo. Saudações e despedidas não precisam de chamada de ferramenta."""

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2).bind_tools(ALL_TOOLS)


async def chat_with_llm(state: AgendAIState) -> dict:
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(state["messages"])
    response = await llm.ainvoke(messages)
    return {"messages": [response]}
