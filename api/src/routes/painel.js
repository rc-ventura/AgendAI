const express = require('express');
const router = express.Router();

function painelRouter(db) {
  router.get('/', (req, res, next) => {
    try {
      const rows = db.prepare(`
        SELECT a.id, a.status, a.criado_em,
               p.nome as paciente_nome, p.email as paciente_email,
               m.nome as medico_nome, m.especialidade,
               h.data_hora
        FROM agendamentos a
        JOIN pacientes p ON p.id = a.paciente_id
        JOIN horarios h ON h.id = a.horario_id
        JOIN medicos m ON m.id = h.medico_id
        ORDER BY h.data_hora
      `).all();

      const rows_html = rows.map(r => {
        const statusColor = r.status === 'ativo' ? '#2d7a2d' : '#b22222';
        return `
          <tr>
            <td>${r.id}</td>
            <td>${r.paciente_nome}<br><small>${r.paciente_email}</small></td>
            <td>${r.medico_nome}<br><small>${r.especialidade}</small></td>
            <td>${r.data_hora.replace('T', ' ')}</td>
            <td><span style="color:${statusColor};font-weight:bold">${r.status}</span></td>
            <td>${r.criado_em}</td>
          </tr>`;
      }).join('');

      const html = `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>AgendAI — Painel de Agendamentos</title>
  <style>
    body { font-family: sans-serif; padding: 24px; background: #f5f5f5; }
    h1 { color: #333; }
    table { border-collapse: collapse; width: 100%; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.1); }
    th { background: #4a90d9; color: white; padding: 10px 14px; text-align: left; }
    td { padding: 10px 14px; border-bottom: 1px solid #eee; vertical-align: top; }
    tr:last-child td { border-bottom: none; }
    small { color: #888; }
  </style>
</head>
<body>
  <h1>AgendAI — Painel de Agendamentos</h1>
  <p>Total: <strong>${rows.length}</strong> agendamentos</p>
  <table>
    <thead>
      <tr>
        <th>#</th><th>Paciente</th><th>Médico</th><th>Data/Hora</th><th>Status</th><th>Criado em</th>
      </tr>
    </thead>
    <tbody>${rows_html}</tbody>
  </table>
</body>
</html>`;

      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      res.send(html);
    } catch (err) {
      next(err);
    }
  });

  return router;
}

module.exports = painelRouter;
