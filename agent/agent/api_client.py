import os
import httpx


class ApiClient:
    def __init__(self, base_url: str | None = None):
        self._base_url = base_url or os.environ.get("API_BASE_URL", "http://api:3000")
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=10.0)

    async def buscar_horarios(self, data: str | None = None) -> list[dict]:
        params = {"data": data} if data else {}
        r = await self._client.get("/horarios/disponiveis", params=params)
        r.raise_for_status()
        return r.json()

    async def criar_agendamento(self, paciente_email: str, horario_id: int) -> dict:
        r = await self._client.post(
            "/agendamentos",
            json={"paciente_email": paciente_email, "horario_id": horario_id},
        )
        r.raise_for_status()
        return r.json()

    async def cancelar_agendamento(self, agendamento_id: int) -> dict:
        r = await self._client.patch(f"/agendamentos/{agendamento_id}/cancelar")
        r.raise_for_status()
        return r.json()

    async def buscar_paciente(self, email: str) -> dict:
        r = await self._client.get(f"/pacientes/{email}")
        if r.status_code == 404:
            return {"erro": "Paciente não encontrado"}
        r.raise_for_status()
        return r.json()

    async def buscar_pagamentos(self) -> list[dict]:
        r = await self._client.get("/pagamentos")
        r.raise_for_status()
        return r.json()

    async def aclose(self):
        await self._client.aclose()


# Singleton para uso nos tools
_client: ApiClient | None = None


def get_client() -> ApiClient:
    global _client
    if _client is None:
        _client = ApiClient()
    return _client
