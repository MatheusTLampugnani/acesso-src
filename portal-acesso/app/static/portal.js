(function () {
  const BASE = '/acesso';

  function caminhoDo(link) {
    try {
      return new URL(link.href, location.href).pathname;
    } catch {
      return '';
    }
  }

  function pertence(caminho, sistema) {
    return caminho === sistema || caminho + '/' === sistema || caminho.startsWith(sistema);
  }

  function barra(conteudo) {
    const div = document.createElement('div');
    div.style.cssText = [
      'position: fixed',
      'bottom: 16px',
      'right: 16px',
      'z-index: 9999',
      'display: flex',
      'gap: 12px',
      'align-items: center',
      'background: rgba(15, 19, 28, 0.92)',
      'backdrop-filter: blur(16px)',
      '-webkit-backdrop-filter: blur(16px)',
      'border: 1px solid rgba(255, 255, 255, 0.12)',
      'border-radius: 9999px',
      'padding: 7px 18px',
      'font: 500 13.5px "Inter", system-ui, -apple-system, sans-serif',
      'color: #f1f5f9',
      'box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5)',
      'transition: transform 0.2s ease',
    ].join(';');

    div.innerHTML = conteudo;
    document.body.appendChild(div);
    return div;
  }

  const estiloLink = 'color:#60a5fa; text-decoration:none; font-weight:500; transition: color 0.15s ease;';

  fetch(BASE + '/api/eu', { credentials: 'same-origin' }).then(async (resposta) => {
    let dados = {};
    try {
      dados = await resposta.json();
    } catch { /* json parse error */ }

    if (resposta.status === 401) {
      if (dados && dados.modo === 'bloquear') {
        location.href = BASE + '/entrar?volta=' + encodeURIComponent(location.pathname);
        return;
      }
      const div = barra(`<a href="${BASE}/entrar?volta=/" style="${estiloLink}">Entrar no Portal →</a>`);
      div.onmouseenter = () => div.style.transform = 'translateY(-2px)';
      div.onmouseleave = () => div.style.transform = 'translateY(0)';
      return;
    }
    if (!resposta.ok) return;

    const liberados = (dados.sistemas || []).map((s) => s.caminho);
    document.querySelectorAll('a[href]').forEach((link) => {
      const caminho = caminhoDo(link);
      const protegido = (dados.todos_caminhos || []).some((s) => pertence(caminho, s));
      if (protegido && !liberados.some((s) => pertence(caminho, s))) {
        const elementoCard = link.closest('.app-card') || link.closest('.card') || link;
        elementoCard.style.display = 'none';
      }
    });

    const nome = document.createElement('span');
    nome.innerHTML = `<span style="display:inline-block; width:7px; height:7px; border-radius:50%; background:#10b981; margin-right:8px; box-shadow:0 0 6px rgba(16,185,129,0.7);"></span>${dados.nome}`;

    const div = barra(
      `<span></span>`
      + `<span style="color:rgba(255,255,255,0.2);">|</span>`
      + `<a href="${BASE}/" style="${estiloLink}">${dados.admin ? 'Gerenciar Acessos' : 'Minha Conta'}</a>`
      + `<span style="color:rgba(255,255,255,0.2);">|</span>`
      + `<a href="#" style="${estiloLink}; color:#f87171;" data-sair>Sair</a>`,
    );

    div.firstChild.replaceWith(nome);
    div.onmouseenter = () => div.style.transform = 'translateY(-2px)';
    div.onmouseleave = () => div.style.transform = 'translateY(0)';

    div.querySelector('[data-sair]').addEventListener('click', async (ev) => {
      ev.preventDefault();
      await fetch(BASE + '/api/sair', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-Portal': '1' },
      });
      location.href = BASE + '/entrar?volta=/';
    });
  }).catch(() => {
    /* Portal de acesso fora do ar: a página inicial permanece inalterada sem quebrar */
  });
})();
