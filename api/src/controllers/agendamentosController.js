const { isValidEmail, isPositiveInteger } = require('../middlewares/validation');

function createAgendamentosController({ agendamentosService }) {
  async function criar(req, res, next) {
    try {
      const { paciente_email, horario_id } = req.body;

      if (!isValidEmail(paciente_email)) {
        return res.status(400).json({ error: 'E-mail inválido' });
      }
      if (!isPositiveInteger(horario_id)) {
        return res.status(400).json({ error: 'horario_id deve ser um número inteiro positivo' });
      }

      const result = agendamentosService.criarAgendamento(paciente_email, Number(horario_id));
      res.status(201).json(result);
    } catch (err) {
      next(err);
    }
  }

  async function buscar(req, res, next) {
    try {
      if (!isPositiveInteger(req.params.id)) {
        return res.status(400).json({ error: 'ID inválido' });
      }
      const result = agendamentosService.buscarAgendamento(Number(req.params.id));
      res.json(result);
    } catch (err) {
      next(err);
    }
  }

  async function cancelar(req, res, next) {
    try {
      if (!isPositiveInteger(req.params.id)) {
        return res.status(400).json({ error: 'ID inválido' });
      }
      const result = agendamentosService.cancelarAgendamento(Number(req.params.id));
      res.json(result);
    } catch (err) {
      next(err);
    }
  }

  async function listar(req, res, next) {
    try {
      const { email, status } = req.query;
      if (!email || !isValidEmail(email)) {
        return res.status(400).json({ error: 'Parâmetro email inválido ou ausente' });
      }
      const result = agendamentosService.listarAgendamentosPaciente(email, status || null);
      res.json(result);
    } catch (err) {
      next(err);
    }
  }

  return { criar, buscar, cancelar, listar };
}

module.exports = { createAgendamentosController };
