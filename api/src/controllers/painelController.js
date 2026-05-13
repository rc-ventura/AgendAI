// Escapes HTML special characters to prevent XSS when rendering user-supplied data.
function escapeHtml(unsafe) {
  return String(unsafe)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function createPainelController({ painelService }) {
  async function renderizar(req, res, next) {
    try {
      const rows = painelService.listarAgendamentos();

      const rows_html = rows.map(r => {
        const statusColor = r.status === 'ativo' ? '#2d7a2d' : '#b22222';
        return `
          <tr>
            <td>${escapeHtml(r.id)}</td>
            <td>${escapeHtml(r.paciente_nome)}<br><small>${escapeHtml(r.paciente_email)}</small></td>
            <td>${escapeHtml(r.medico_nome)}<br><small>${escapeHtml(r.especialidade)}</small></td>
            <td>${escapeHtml(r.data_hora.replace('T', ' '))}</td>
            <td><span style="color:${statusColor};font-weight:bold">${escapeHtml(r.status)}</span></td>
            <td>${escapeHtml(r.criado_em)}</td>
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
  }

  return { renderizar };
}

module.exports = { createPainelController };
