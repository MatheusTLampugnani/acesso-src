/* exported BASE, api, el, sair, toast, modalConfirm, modalPrompt, configurarAlternadorSenha */
// Chamadas à API do portal (o cabeçalho X-Portal protege contra CSRF de outros sites)
const BASE = '/acesso';

/**
 * Executa requisições à API do portal mantendo contratos e credenciais de sessão.
 */
async function api(caminho, opcoes = {}) {
  const resposta = await fetch(BASE + caminho, {
    method: opcoes.method || 'GET',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-Portal': '1' },
    body: opcoes.body ? JSON.stringify(opcoes.body) : undefined,
  });

  let dados = null;
  try {
    dados = await resposta.json();
  } catch {
    /* resposta sem corpo json */
  }

  if (!resposta.ok) {
    const detalhe = dados && dados.detail;
    const erro = new Error(typeof detalhe === 'string' ? detalhe : 'Não foi possível concluir a operação. Verifique os dados.');
    erro.status = resposta.status;
    erro.dados = dados;
    throw erro;
  }
  return dados;
}

/**
 * Cria elementos DOM de forma declarativa e limpa.
 */
function el(tag, atributos = {}, ...filhos) {
  const no = document.createElement(tag);
  for (const [chave, valor] of Object.entries(atributos)) {
    if (chave.startsWith('on')) {
      no.addEventListener(chave.slice(2).toLowerCase(), valor);
    } else if (chave === 'class') {
      no.className = valor;
    } else if (valor === true) {
      no.setAttribute(chave, '');
    } else if (valor !== false && valor != null) {
      no.setAttribute(chave, valor);
    }
  }
  for (const filho of filhos.flat()) {
    if (filho != null) no.append(filho);
  }
  return no;
}

/**
 * Encerra a sessão e redireciona para a tela de autenticação.
 */
async function sair() {
  try {
    await api('/api/sair', { method: 'POST' });
  } finally {
    location.href = BASE + '/entrar';
  }
}

/**
 * Exibe notificações toast flutuantes e elegantes no canto da tela.
 */
function toast(mensagem, tipo = 'info', duracao = 3500) {
  let container = document.getElementById('container-toasts');
  if (!container) {
    container = el('div', { id: 'container-toasts', 'aria-live': 'polite' });
    document.body.appendChild(container);
  }

  const elementoToast = el('div', {
    class: `toast ${tipo === 'sucesso' ? 'sucesso' : tipo === 'erro' ? 'erro' : ''}`,
    role: 'status',
  }, mensagem);

  container.appendChild(elementoToast);

  setTimeout(() => {
    elementoToast.style.opacity = '0';
    elementoToast.style.transform = 'translateX(20px)';
    setTimeout(() => elementoToast.remove(), 250);
  }, duracao);
}

/**
 * Diálogo modal acessível para confirmação de ações (substitui window.confirm com estilo moderno).
 */
function modalConfirm({ titulo = 'Confirmar Ação', mensagem = 'Tem certeza que deseja continuar?', detalhe = '', botaoConfirmar = 'Confirmar', botaoCancelar = 'Cancelar', perigoso = false }) {
  return new Promise((resolve) => {
    const overlay = el('div', { class: 'modal-overlay', role: 'dialog', 'aria-modal': 'true' });
    
    function fechar(resultado) {
      document.removeEventListener('keydown', teclaHandler);
      overlay.remove();
      resolve(resultado);
    }

    function teclaHandler(ev) {
      if (ev.key === 'Escape') fechar(false);
    }
    document.addEventListener('keydown', teclaHandler);

    const btnConfirmar = el('button', {
      type: 'button',
      class: perigoso ? 'perigo' : 'principal',
      onclick: () => fechar(true),
    }, botaoConfirmar);

    const btnCancelar = el('button', {
      type: 'button',
      class: 'secundario',
      onclick: () => fechar(false),
    }, botaoCancelar);

    const btnFecharX = el('button', {
      type: 'button',
      class: 'modal-fechar',
      'aria-label': 'Fechar',
      onclick: () => fechar(false),
    }, '×');

    const corpo = [el('p', {}, mensagem)];
    if (detalhe) corpo.push(el('p', { class: 'suave' }, detalhe));

    const janela = el('div', { class: 'modal-janela' },
      el('div', { class: 'modal-cabecalho' },
        el('h3', {}, titulo),
        btnFecharX,
      ),
      el('div', { class: 'modal-corpo' }, ...corpo),
      el('div', { class: 'modal-rodape' },
        btnCancelar,
        btnConfirmar,
      ),
    );

    overlay.appendChild(janela);
    overlay.addEventListener('click', (ev) => {
      if (ev.target === overlay) fechar(false);
    });

    document.body.appendChild(overlay);
    btnConfirmar.focus();
  });
}

/**
 * Diálogo modal com campo de entrada de texto (substitui window.prompt com interface industrial limpa).
 */
function modalPrompt({ titulo = 'Entrada de Dados', descricao = '', placeholder = '', valorPadrao = '', dica = '', botaoConfirmar = 'Salvar', botaoCancelar = 'Cancelar' }) {
  return new Promise((resolve) => {
    const overlay = el('div', { class: 'modal-overlay', role: 'dialog', 'aria-modal': 'true' });
    const campoInput = el('input', {
      type: 'text',
      value: valorPadrao,
      placeholder,
      class: 'largo',
      autocomplete: 'off',
    });

    function fechar(resultado) {
      document.removeEventListener('keydown', teclaHandler);
      overlay.remove();
      resolve(resultado);
    }

    function teclaHandler(ev) {
      if (ev.key === 'Escape') fechar(null);
      if (ev.key === 'Enter') fechar(campoInput.value);
    }
    document.addEventListener('keydown', teclaHandler);

    const btnConfirmar = el('button', {
      type: 'button',
      class: 'principal',
      onclick: () => fechar(campoInput.value),
    }, botaoConfirmar);

    const btnCancelar = el('button', {
      type: 'button',
      class: 'secundario',
      onclick: () => fechar(null),
    }, botaoCancelar);

    const corpo = [];
    if (descricao) corpo.push(el('p', {}, descricao));
    corpo.push(campoInput);
    if (dica) corpo.push(el('p', { class: 'suave', style: 'margin-top: 8px;' }, dica));

    const janela = el('div', { class: 'modal-janela' },
      el('div', { class: 'modal-cabecalho' },
        el('h3', {}, titulo),
        el('button', {
          type: 'button',
          class: 'modal-fechar',
          'aria-label': 'Fechar',
          onclick: () => fechar(null),
        }, '×'),
      ),
      el('div', { class: 'modal-corpo' }, ...corpo),
      el('div', { class: 'modal-rodape' },
        btnCancelar,
        btnConfirmar,
      ),
    );

    overlay.appendChild(janela);
    overlay.addEventListener('click', (ev) => {
      if (ev.target === overlay) fechar(null);
    });

    document.body.appendChild(overlay);
    campoInput.focus();
    campoInput.select();
  });
}

/**
 * Conecta um botão para alternar a visualização da senha (olho aberto / fechado).
 */
function configurarAlternadorSenha(inputEl, botaoEl) {
  if (!inputEl || !botaoEl) return;
  const iconeOlhoAberto = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`;
  const iconeOlhoFechado = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>`;

  botaoEl.innerHTML = iconeOlhoFechado;
  botaoEl.addEventListener('click', (ev) => {
    ev.preventDefault();
    const visivel = inputEl.type === 'text';
    inputEl.type = visivel ? 'password' : 'text';
    botaoEl.innerHTML = visivel ? iconeOlhoFechado : iconeOlhoAberto;
    botaoEl.setAttribute('aria-label', visivel ? 'Mostrar senha' : 'Ocultar senha');
  });
}
