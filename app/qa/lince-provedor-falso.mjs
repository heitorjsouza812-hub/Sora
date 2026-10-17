// Provedor falso compatível com OpenAI, só para a validação da etapa 2 (Lince).
// Uso:  node qa/lince-provedor-falso.mjs [porta]      (padrão 8765)
// No app: tipo "Compatível com OpenAI", base_url http://localhost:8765/v1, chave sk-teste-lince-1234567890
// Qualquer outra chave → 401 no formato da OpenAI (o backend deve mostrar 422 em PT-BR).
import http from 'node:http';

const PORTA = Number(process.argv[2] ?? process.env.LINCE_PORTA ?? 8765);
const CHAVE_VALIDA = 'sk-teste-lince-1234567890';
const MODELOS = ['lince-pequeno', 'lince-medio', 'lince-grande'];

function json(res, status, corpo) {
  const texto = JSON.stringify(corpo);
  res.writeHead(status, { 'content-type': 'application/json', 'content-length': Buffer.byteLength(texto) });
  res.end(texto);
}

const servidor = http.createServer((req, res) => {
  const { pathname } = new URL(req.url, `http://localhost:${PORTA}`);
  const autorizacao = req.headers.authorization ?? '';
  console.log(`${new Date().toISOString()} ${req.method} ${pathname} auth=${autorizacao ? 'Bearer …' + autorizacao.slice(-4) : '(nenhuma)'}`);

  if (pathname === '/health') return json(res, 200, { ok: true });

  if (autorizacao !== `Bearer ${CHAVE_VALIDA}`) {
    return json(res, 401, {
      error: { message: 'Incorrect API key provided.', type: 'invalid_request_error', code: 'invalid_api_key' },
    });
  }

  if (req.method === 'GET' && pathname === '/v1/models') {
    return json(res, 200, {
      object: 'list',
      data: MODELOS.map((id) => ({ id, object: 'model', created: 1760000000, owned_by: 'lince' })),
    });
  }

  if (req.method === 'POST' && pathname === '/v1/chat/completions') {
    let corpo = '';
    req.on('data', (parte) => (corpo += parte));
    req.on('end', () => {
      let modelo = MODELOS[0];
      try {
        modelo = JSON.parse(corpo).model ?? modelo;
      } catch {
        /* corpo inválido: segue com o padrão */
      }
      json(res, 200, {
        id: 'chatcmpl-lince',
        object: 'chat.completion',
        created: 1760000000,
        model: modelo,
        choices: [{ index: 0, message: { role: 'assistant', content: 'ok' }, finish_reason: 'stop' }],
        usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
      });
    });
    return;
  }

  json(res, 404, { error: { message: 'Rota inexistente no provedor falso.', type: 'not_found' } });
});

servidor.listen(PORTA, '127.0.0.1', () => {
  console.log(`Provedor falso do Lince em http://127.0.0.1:${PORTA}/v1  (chave válida: ${CHAVE_VALIDA})`);
});
