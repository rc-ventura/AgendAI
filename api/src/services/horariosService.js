const cache = require('../cache');

function createHorariosService({ horariosRepo }) {
  function listarDisponiveis(data) {
    const cacheKey = data ? `horarios:${data}` : 'horarios';

    const cached = cache.get(cacheKey);
    if (cached) return cached;

    const rows = data
      ? horariosRepo.findAvailableByDate(data)
      : horariosRepo.findAvailable();

    const result = rows.map(r => ({
      id: r.id,
      data_hora: r.data_hora,
      disponivel: r.disponivel,
      medico: {
        id: r.medico_id,
        nome: r.medico_nome,
        especialidade: r.especialidade,
      },
    }));

    cache.set(cacheKey, result);
    return result;
  }

  return { listarDisponiveis };
}

module.exports = { createHorariosService };
