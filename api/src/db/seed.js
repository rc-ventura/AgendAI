// Seeds baseline reference data exactly once (count-guard on medicos). Idempotent: a second
// run on a populated DB is a no-op. Inserts run inside a single transaction.
async function seed(pool) {
  const count = await pool.query('SELECT COUNT(*)::int AS n FROM medicos');
  if (count.rows[0].n > 0) return;

  const client = await pool.connect();
  try {
    await client.query('BEGIN');

    const insMedico = async (nome, esp) =>
      (await client.query('INSERT INTO medicos (nome, especialidade) VALUES ($1, $2) RETURNING id', [nome, esp])).rows[0].id;
    const insPaciente = async (nome, email, tel) =>
      (await client.query('INSERT INTO pacientes (nome, email, telefone) VALUES ($1, $2, $3) RETURNING id', [nome, email, tel])).rows[0].id;
    const insHorario = async (medicoId, dataHora, disp) =>
      (await client.query('INSERT INTO horarios (medico_id, data_hora, disponivel) VALUES ($1, $2, $3) RETURNING id', [medicoId, dataHora, disp])).rows[0].id;

    // Médicos
    const m1 = await insMedico('Dr. Carlos Lima', 'Clínico Geral');
    const m2 = await insMedico('Dra. Ana Souza', 'Cardiologista');
    const m3 = await insMedico('Dr. Pedro Costa', 'Dermatologista');

    // Pacientes
    const p1 = await insPaciente('João Silva', 'joao@email.com', '11999990001');
    const p2 = await insPaciente('Maria Santos', 'maria@email.com', '11999990002');
    await insPaciente('Pedro Oliveira', 'pedro@email.com', '11999990003');
    await insPaciente('Ana Ferreira', 'ana@email.com', '11999990004');
    await insPaciente('Lucas Pereira', 'lucas@email.com', '11999990005');
    await insPaciente('Rafael Ventura', 'rcventura1080@gmail.com', '11999990006');


    // Horários — próximos dias úteis.
    // Use local-time formatting (not toISOString, which is UTC) so the calendar day matches
    // d.getDay() and the API's date filter behaves predictably in any server timezone.
    const formatLocalDate = (d) => {
      const yyyy = d.getFullYear();
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const dd = String(d.getDate()).padStart(2, '0');
      return `${yyyy}-${mm}-${dd}`;
    };
    const hoje = new Date();
    const horarios = [];
    let diaOffset = 1;
    while (horarios.length < 10) {
      const d = new Date(hoje);
      d.setDate(hoje.getDate() + diaOffset);
      const diaSemana = d.getDay();
      if (diaSemana !== 0 && diaSemana !== 6) {
        const dateStr = formatLocalDate(d);
        const medicos = [m1, m2, m3];
        const horas = ['09:00:00', '11:00:00', '14:00:00', '16:00:00'];
        const medicoId = medicos[horarios.length % 3];
        const hora = horas[Math.floor(horarios.length / 3) % 4];
        const id = await insHorario(medicoId, `${dateStr}T${hora}`, 1);
        horarios.push(id);
      }
      diaOffset++;
    }

    // 2 agendamentos pré-confirmados (horarios 0 e 1 ficam indisponíveis)
    await client.query('INSERT INTO agendamentos (paciente_id, horario_id, status) VALUES ($1, $2, $3)', [p1, horarios[0], 'ativo']);
    await client.query('INSERT INTO agendamentos (paciente_id, horario_id, status) VALUES ($1, $2, $3)', [p2, horarios[1], 'ativo']);
    await client.query('UPDATE horarios SET disponivel = 0 WHERE id IN ($1, $2)', [horarios[0], horarios[1]]);

    // Pagamento
    await client.query('INSERT INTO pagamentos (descricao, valor, formas) VALUES ($1, $2, $3)', [
      'Consulta Geral',
      150.0,
      JSON.stringify(['PIX', 'Cartão de Débito', 'Cartão de Crédito', 'Dinheiro']),
    ]);

    await client.query('COMMIT');
  } catch (error) {
    await client.query('ROLLBACK');
    console.error('Erro ao popular banco de dados:', error);
    throw error;
  } finally {
    client.release();
  }
}

module.exports = { seed };
