function seed(db) {
  const count = db.prepare('SELECT COUNT(*) as n FROM medicos').get();
  if (count.n > 0) return;

  const insertMedico = db.prepare('INSERT INTO medicos (nome, especialidade) VALUES (?, ?)');
  const insertPaciente = db.prepare('INSERT INTO pacientes (nome, email, telefone) VALUES (?, ?, ?)');
  const insertHorario = db.prepare('INSERT INTO horarios (medico_id, data_hora, disponivel) VALUES (?, ?, ?)');
  const insertAgendamento = db.prepare('INSERT INTO agendamentos (paciente_id, horario_id, status) VALUES (?, ?, ?)');
  const insertPagamento = db.prepare('INSERT INTO pagamentos (descricao, valor, formas) VALUES (?, ?, ?)');

  const seedAll = db.transaction(() => {
    // Médicos
    const m1 = insertMedico.run('Dr. Carlos Lima', 'Clínico Geral');
    const m2 = insertMedico.run('Dra. Ana Souza', 'Cardiologista');
    const m3 = insertMedico.run('Dr. Pedro Costa', 'Dermatologista');

    // Pacientes
    const p1 = insertPaciente.run('João Silva', 'joao@email.com', '11999990001');
    const p2 = insertPaciente.run('Maria Santos', 'maria@email.com', '11999990002');
    const p3 = insertPaciente.run('Pedro Oliveira', 'pedro@email.com', '11999990003');
    const p4 = insertPaciente.run('Ana Ferreira', 'ana@email.com', '11999990004');
    insertPaciente.run('Lucas Pereira', 'lucas@email.com', '11999990005');

    // Horários — próximos 7 dias úteis
    const hoje = new Date();
    const horarios = [];
    let diaOffset = 1;
    while (horarios.length < 10) {
      const d = new Date(hoje);
      d.setDate(hoje.getDate() + diaOffset);
      const diaSemana = d.getDay();
      if (diaSemana !== 0 && diaSemana !== 6) {
        const dateStr = d.toISOString().slice(0, 10);
        const medicos = [m1.lastInsertRowid, m2.lastInsertRowid, m3.lastInsertRowid];
        const horas = ['09:00:00', '11:00:00', '14:00:00', '16:00:00'];
        const medicoId = medicos[horarios.length % 3];
        const hora = horas[Math.floor(horarios.length / 3) % 4];
        const h = insertHorario.run(medicoId, `${dateStr}T${hora}`, 1);
        horarios.push(h.lastInsertRowid);
      }
      diaOffset++;
    }

    // 2 agendamentos pré-confirmados (horarios 0 e 1 ficam indisponíveis)
    insertAgendamento.run(p1.lastInsertRowid, horarios[0], 'ativo');
    insertAgendamento.run(p2.lastInsertRowid, horarios[1], 'ativo');
    db.prepare('UPDATE horarios SET disponivel=0 WHERE id IN (?, ?)').run(horarios[0], horarios[1]);

    // Pagamento
    insertPagamento.run('Consulta Geral', 150.00, JSON.stringify(['PIX', 'Cartão de Débito', 'Cartão de Crédito', 'Dinheiro']));
  });

  seedAll();
}

module.exports = { seed };
