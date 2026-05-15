import pytest
import httpx
import respx
from unittest.mock import AsyncMock, MagicMock
from langchain_core.messages import HumanMessage

from agent.state import AgendAIState


@pytest.fixture
def base_state() -> AgendAIState:
    return {
        "messages": [HumanMessage(content="Olá")],
        "input_type": "text",
        "audio_data": None,
        "session_id": "test-session-001",
        "email_pending": False,
        "email_payload": None,
        "final_response": None,
    }


@pytest.fixture
def mock_api_client():
    with respx.mock(base_url="http://api:3000", assert_all_called=False) as mock:
        mock.get("/horarios/disponiveis").mock(return_value=httpx.Response(200, json=[
            {"id": 1, "data_hora": "2026-05-20T09:00:00", "disponivel": 1,
             "medico": {"id": 1, "nome": "Dr. Carlos Lima", "especialidade": "Clínico Geral"}}
        ]))
        mock.get("/horarios/disponiveis", params={"data": "2026-05-20"}).mock(
            return_value=httpx.Response(200, json=[
                {"id": 1, "data_hora": "2026-05-20T09:00:00", "disponivel": 1,
                 "medico": {"id": 1, "nome": "Dr. Carlos Lima", "especialidade": "Clínico Geral"}}
            ])
        )
        mock.post("/agendamentos").mock(return_value=httpx.Response(201, json={
            "id": 10, "status": "ativo",
            "paciente": {"id": 1, "nome": "João Silva", "email": "joao@email.com"},
            "horario": {"id": 1, "data_hora": "2026-05-20T09:00:00"},
            "medico": {"nome": "Dr. Carlos Lima"},
            "criado_em": "2026-05-14T10:00:00",
        }))
        mock.patch("/agendamentos/1/cancelar").mock(return_value=httpx.Response(200, json={
            "id": 1, "status": "cancelado"
        }))
        mock.get("/pacientes/joao@email.com").mock(return_value=httpx.Response(200, json={
            "id": 1, "nome": "João Silva", "email": "joao@email.com", "telefone": "11999999999"
        }))
        mock.get("/pacientes/naoexiste@email.com").mock(
            return_value=httpx.Response(404, json={"error": "Paciente não encontrado"})
        )
        mock.get("/pagamentos").mock(return_value=httpx.Response(200, json=[
            {"id": 1, "descricao": "Consulta", "valor": 200.0, "formas": '["PIX","Cartão","Dinheiro"]'}
        ]))
        yield mock


@pytest.fixture
def mock_openai_chat():
    mock = AsyncMock()
    mock.ainvoke = AsyncMock()
    return mock
