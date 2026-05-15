import pytest
import httpx
import respx

from agent.api_client import ApiClient


@pytest.mark.asyncio
async def test_buscar_horarios_sem_filtro(mock_api_client):
    client = ApiClient(base_url="http://api:3000")
    result = await client.buscar_horarios()
    assert isinstance(result, list)
    assert result[0]["id"] == 1
    assert "medico" in result[0]


@pytest.mark.asyncio
async def test_buscar_horarios_com_data(mock_api_client):
    client = ApiClient(base_url="http://api:3000")
    result = await client.buscar_horarios(data="2026-05-20")
    assert len(result) == 1


@pytest.mark.asyncio
async def test_criar_agendamento(mock_api_client):
    client = ApiClient(base_url="http://api:3000")
    result = await client.criar_agendamento("joao@email.com", 1)
    assert result["id"] == 10
    assert result["status"] == "ativo"


@pytest.mark.asyncio
async def test_cancelar_agendamento(mock_api_client):
    client = ApiClient(base_url="http://api:3000")
    result = await client.cancelar_agendamento(1)
    assert result["status"] == "cancelado"


@pytest.mark.asyncio
async def test_buscar_paciente_existente(mock_api_client):
    client = ApiClient(base_url="http://api:3000")
    result = await client.buscar_paciente("joao@email.com")
    assert result["nome"] == "João Silva"


@pytest.mark.asyncio
async def test_buscar_paciente_nao_encontrado(mock_api_client):
    client = ApiClient(base_url="http://api:3000")
    result = await client.buscar_paciente("naoexiste@email.com")
    assert "erro" in result or "error" in result


@pytest.mark.asyncio
async def test_buscar_pagamentos(mock_api_client):
    client = ApiClient(base_url="http://api:3000")
    result = await client.buscar_pagamentos()
    assert isinstance(result, list)
    assert result[0]["valor"] == 200.0
