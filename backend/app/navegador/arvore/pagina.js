// Script da Sora que roda dentro da página (Playwright: page.evaluate).
//
// Lê a página como uma árvore de acessibilidade (papel, nome, valor, estados), distribui refs,
// reencontra elementos por evidência de identidade, junta a evidência de "dá para agir?" e faz
// as ações semânticas (sem mouse/teclado). Quem decide é o Python (app/navegador/arvore/*).
//
// Ideias do agent-desktop (github.com/vercel-labs/agent-desktop, Apache-2.0), reescritas para
// o DOM: wrappers sem significado não gastam profundidade, refs só para o que dá para acionar,
// leitura parcial quando o orçamento acaba, teste de clique em 5 pontos, campo de senha que
// nunca devolve o valor. Código escrito pela Sora.
(pedido) => {
  const VERSAO = 3;
  if (!window.__soraArvore || window.__soraArvore.versao !== VERSAO) {
    window.__soraArvore = (() => {
      const ATR_CURSOR = 'data-sora-cursor';
      const MAX_NOME = 120;
      const MAX_VALOR = 300;
      const MAX_TEXTO = 200;
      const MAX_LEITURAS_GUARDADAS = 10;

      const INTERATIVOS = new Set([
        'link', 'button', 'textbox', 'checkbox', 'radio', 'combobox', 'listbox', 'option',
        'menuitem', 'menuitemcheckbox', 'menuitemradio', 'tab', 'switch', 'slider',
        'spinbutton', 'treeitem', 'scrollarea',
      ]);
      const NOME_DO_CONTEUDO = new Set([
        'button', 'link', 'heading', 'cell', 'columnheader', 'rowheader', 'option', 'menuitem',
        'menuitemcheckbox', 'menuitemradio', 'tab', 'treeitem', 'checkbox', 'radio', 'switch',
        'tooltip', 'generic',
      ]);
      const CONTEXTO = new Set([
        'heading', 'dialog', 'alertdialog', 'alert', 'navigation', 'main', 'banner',
        'contentinfo', 'form', 'search', 'region', 'complementary', 'tablist', 'menu', 'menubar',
        'listbox', 'tree', 'grid', 'table', 'toolbar', 'iframe',
      ]);
      const IGNORAR = new Set([
        'SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'META', 'LINK', 'HEAD', 'BASE', 'TITLE',
      ]);
      const TIPOS_BOTAO = new Set(['button', 'submit', 'reset', 'image', 'file']);

      const S = {
        versao: VERSAO,
        refs: new Map(), // "<leitura>:<numero>" -> WeakRef(elemento)
        leituras: [], // ordem das leituras com refs guardadas
        candidatos: [],
        alvo: null,
      };

      // ---------- utilidades ----------

      const limpar = (t, max) => {
        const s = String(t == null ? '' : t).replace(/\s+/g, ' ').trim();
        return max && s.length > max ? s.slice(0, max - 1) + '…' : s;
      };
      const normal = (t) => limpar(t).normalize('NFKC').toLowerCase();
      const estiloDe = (el) => {
        try { return getComputedStyle(el); } catch (e) { return null; }
      };
      const retangulo = (el) => {
        const r = el.getBoundingClientRect();
        return [r.x, r.y, r.width, r.height].map((v) => Math.round(v * 10) / 10);
      };
      const naTela = (ret) => ret[2] > 0 && ret[3] > 0 && ret[0] + ret[2] > 0 &&
        ret[1] + ret[3] > 0 && ret[0] < innerWidth && ret[1] < innerHeight;
      const ativoProfundo = () => {
        let a = document.activeElement;
        while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement;
        return a;
      };
      const filhosDe = (el) => {
        if (el.shadowRoot) return Array.from(el.shadowRoot.childNodes);
        if (el.tagName === 'SLOT') {
          const atribuidos = el.assignedNodes({ flatten: true });
          if (atribuidos.length) return atribuidos;
        }
        return Array.from(el.childNodes);
      };
      const pai = (el) => {
        if (el.assignedSlot) return el.assignedSlot;
        if (el.parentNode instanceof ShadowRoot) return el.parentNode.host;
        return el.parentElement;
      };
      const contemProfundo = (raiz, el) => {
        for (let e = el; e; e = pai(e)) if (e === raiz) return true;
        return false;
      };
      function* todosOsElementos(raiz) {
        const pilha = [raiz];
        while (pilha.length) {
          const no = pilha.pop();
          if (no.nodeType !== 1) continue;
          if (IGNORAR.has(no.tagName) || no.hasAttribute(ATR_CURSOR)) continue;
          yield no;
          const filhos = no.shadowRoot ? Array.from(no.shadowRoot.children) : [];
          filhos.push(...Array.from(no.children));
          for (let i = filhos.length - 1; i >= 0; i--) pilha.push(filhos[i]);
        }
      }

      // ---------- visibilidade ----------

      const oculto = (el, estilo) => {
        if (!estilo) return true;
        if (el.hasAttribute(ATR_CURSOR)) return true;
        if (el.getAttribute('aria-hidden') === 'true') return true;
        if (estilo.display === 'none') return true;
        if (el instanceof HTMLInputElement && el.type === 'hidden') return true;
        if (estilo.display !== 'contents' && el.getClientRects().length === 0) return true;
        return false;
      };
      const invisivel = (estilo) => estilo.visibility === 'hidden' ||
        estilo.visibility === 'collapse' || Number(estilo.opacity) === 0;
      const visivel = (el) => {
        if (!el || !el.isConnected) return false;
        for (let e = el; e; e = pai(e)) {
          const est = estiloDe(e);
          if (e === el ? oculto(e, est) : (est && est.display === 'none')) return false;
          if (e.getAttribute && e.getAttribute('aria-hidden') === 'true') return false;
        }
        const est = estiloDe(el);
        return !!est && !invisivel(est);
      };

      // ---------- papel ----------

      const rolavel = (el, estilo) => {
        if (el === document.body || el === document.documentElement) return false;
        const y = /(auto|scroll)/.test(estilo.overflowY) && el.scrollHeight > el.clientHeight + 4;
        const x = /(auto|scroll)/.test(estilo.overflowX) && el.scrollWidth > el.clientWidth + 4;
        return x || y;
      };
      const clicavelGenerico = (el, estilo) => {
        if (el.hasAttribute('onclick')) return true;
        if (!estilo || estilo.cursor !== 'pointer') return false;
        const p = pai(el);
        const estPai = p && p.nodeType === 1 ? estiloDe(p) : null;
        if (estPai && estPai.cursor === 'pointer') return false;
        return limpar(el.textContent).length > 0 || !!el.querySelector('img,svg');
      };
      const papelDe = (el, estilo) => {
        const explicito = (el.getAttribute('role') || '').trim().split(/\s+/)[0].toLowerCase();
        if (explicito === 'searchbox') return 'textbox';
        if (explicito && explicito !== 'presentation' && explicito !== 'none') return explicito;
        const tag = el.tagName.toLowerCase();
        switch (tag) {
          case 'a': case 'area': return el.hasAttribute('href') ? 'link' : '';
          case 'button': case 'summary': return 'button';
          case 'input': {
            const tipo = (el.type || 'text').toLowerCase();
            if (tipo === 'checkbox' || tipo === 'radio') return tipo;
            if (tipo === 'range') return 'slider';
            if (tipo === 'number') return 'spinbutton';
            if (TIPOS_BOTAO.has(tipo)) return 'button';
            if (el.hasAttribute('list')) return 'combobox';
            return 'textbox';
          }
          case 'textarea': return 'textbox';
          case 'select': return el.multiple || el.size > 1 ? 'listbox' : 'combobox';
          case 'option': return 'option';
          case 'img': return el.getAttribute('alt') === '' ? '' : 'img';
          case 'svg': return el.getAttribute('aria-label') ? 'img' : '';
          case 'h1': case 'h2': case 'h3': case 'h4': case 'h5': case 'h6': return 'heading';
          case 'nav': return 'navigation';
          case 'main': return 'main';
          case 'header': return el.closest('article,section,main,aside,nav') ? '' : 'banner';
          case 'footer': return el.closest('article,section,main,aside,nav') ? '' : 'contentinfo';
          case 'aside': return 'complementary';
          case 'form': return 'form';
          case 'section': return el.hasAttribute('aria-label') || el.hasAttribute('aria-labelledby') ? 'region' : '';
          case 'article': return 'article';
          case 'dialog': return 'dialog';
          case 'ul': case 'ol': case 'menu': return 'list';
          case 'li': return 'listitem';
          case 'table': return 'table';
          case 'tr': return 'row';
          case 'td': return 'cell';
          case 'th': return 'columnheader';
          case 'fieldset': case 'details': return 'group';
          case 'iframe': return 'iframe';
          case 'progress': return 'progressbar';
          case 'meter': return 'meter';
          default: break;
        }
        if (el.isContentEditable && (el.contentEditable === 'true' || el.contentEditable === 'plaintext-only')) return 'textbox';
        if (estilo && rolavel(el, estilo)) return 'scrollarea';
        if (estilo && clicavelGenerico(el, estilo)) return 'generic';
        return '';
      };

      // ---------- nome, valor, estados ----------

      const textoDeIds = (ids) => ids.split(/\s+/).map((id) => {
        const alvo = id ? document.getElementById(id) : null;
        return alvo ? (alvo.innerText || alvo.textContent || '') : '';
      }).join(' ');
      const ehSenha = (el) => el instanceof HTMLInputElement && el.type === 'password';

      const nomeDe = (el, papel) => {
        const ids = el.getAttribute('aria-labelledby');
        if (ids) { const t = limpar(textoDeIds(ids), MAX_NOME); if (t) return [t, 'rotulo']; }
        const aria = limpar(el.getAttribute('aria-label'), MAX_NOME);
        if (aria) return [aria, 'rotulo'];
        if (el instanceof HTMLInputElement) {
          const tipo = (el.type || '').toLowerCase();
          if (tipo === 'image' && el.alt) return [limpar(el.alt, MAX_NOME), 'rotulo'];
          if (TIPOS_BOTAO.has(tipo) && tipo !== 'file') {
            const v = limpar(el.value || (tipo === 'submit' ? 'Enviar' : tipo === 'reset' ? 'Limpar' : ''), MAX_NOME);
            if (v) return [v, 'rotulo'];
          }
        }
        if (el.labels && el.labels.length) {
          const t = limpar(Array.from(el.labels).map((l) => l.innerText || l.textContent).join(' '), MAX_NOME);
          if (t) return [t, 'rotulo'];
        }
        const tag = el.tagName;
        if ((tag === 'IMG' || tag === 'AREA') && el.alt) return [limpar(el.alt, MAX_NOME), 'rotulo'];
        if (tag === 'FIELDSET') { const l = el.querySelector(':scope > legend'); if (l) return [limpar(l.textContent, MAX_NOME), 'rotulo']; }
        if (tag === 'TABLE' && el.caption) return [limpar(el.caption.textContent, MAX_NOME), 'rotulo'];
        if (tag === 'DETAILS') { const s = el.querySelector(':scope > summary'); if (s) return [limpar(s.textContent, MAX_NOME), 'conteudo']; }
        if (tag === 'svg') { const t = el.querySelector('title'); if (t) return [limpar(t.textContent, MAX_NOME), 'rotulo']; }
        if (NOME_DO_CONTEUDO.has(papel)) {
          const t = limpar(el.innerText || el.textContent, MAX_NOME);
          if (t) return [t, 'conteudo'];
          const img = el.querySelector('img[alt],svg[aria-label]');
          if (img) return [limpar(img.getAttribute('alt') || img.getAttribute('aria-label'), MAX_NOME), 'conteudo'];
        }
        const titulo = limpar(el.getAttribute('title'), MAX_NOME);
        if (titulo) return [titulo, 'titulo'];
        const dica = limpar(el.getAttribute('placeholder') || el.getAttribute('aria-placeholder'), MAX_NOME);
        if (dica) return [dica, 'dica'];
        return ['', ''];
      };
      const descricaoDe = (el, fonteNome) => {
        const ids = el.getAttribute('aria-describedby');
        if (ids) { const t = limpar(textoDeIds(ids), 160); if (t) return t; }
        if (fonteNome !== 'titulo') { const t = limpar(el.getAttribute('title'), 160); if (t) return t; }
        return '';
      };
      const valorDe = (el, papel) => {
        if (ehSenha(el)) return null;
        if (el instanceof HTMLSelectElement) {
          return limpar(Array.from(el.selectedOptions).map((o) => o.label || o.text).join(', '), MAX_VALOR);
        }
        if (el instanceof HTMLInputElement) {
          const tipo = (el.type || '').toLowerCase();
          if (tipo === 'checkbox' || tipo === 'radio' || TIPOS_BOTAO.has(tipo)) return null;
          return String(el.value).slice(0, MAX_VALOR);
        }
        if (el instanceof HTMLTextAreaElement) return String(el.value).slice(0, MAX_VALOR);
        if (papel === 'textbox' && el.isContentEditable) return limpar(el.innerText, MAX_VALOR);
        if (papel === 'slider' || papel === 'spinbutton' || papel === 'progressbar' || papel === 'meter') {
          const v = el.getAttribute('aria-valuetext') || el.getAttribute('aria-valuenow');
          if (v != null) return limpar(v, MAX_VALOR);
          if ('value' in el) return String(el.value);
        }
        if (papel === 'combobox') {
          const v = el.getAttribute('aria-valuetext');
          if (v) return limpar(v, MAX_VALOR);
        }
        return null;
      };
      const desabilitado = (el) => !!(el.disabled || el.getAttribute('aria-disabled') === 'true' ||
        (el.closest && (el.closest('fieldset[disabled]') || el.closest('[inert]'))));
      const marcado = (el) => {
        if (el instanceof HTMLInputElement && (el.type === 'checkbox' || el.type === 'radio')) {
          return el.indeterminate ? 'misto' : el.checked;
        }
        const a = el.getAttribute('aria-checked');
        if (a === 'mixed') return 'misto';
        if (a === 'true') return true;
        if (a === 'false') return false;
        return null;
      };
      const expandido = (el) => {
        const a = el.getAttribute('aria-expanded');
        if (a === 'true') return true;
        if (a === 'false') return false;
        if (el.tagName === 'SUMMARY' && el.parentElement && el.parentElement.tagName === 'DETAILS') return el.parentElement.open;
        if (el.tagName === 'DETAILS') return el.open;
        return null;
      };
      const selecionado = (el) => {
        const a = el.getAttribute('aria-selected');
        if (a === 'true') return true;
        if (a === 'false') return false;
        if (el instanceof HTMLOptionElement) return el.selected;
        return null;
      };
      const estadosDe = (el, ret) => {
        const e = [];
        if (el === ativoProfundo()) e.push('focado');
        if (desabilitado(el)) e.push('desabilitado');
        const m = marcado(el);
        if (m === true) e.push('marcado'); else if (m === 'misto') e.push('misto');
        if (el.getAttribute('aria-pressed') === 'true') e.push('pressionado');
        const x = expandido(el);
        if (x === true) e.push('expandido'); else if (x === false) e.push('recolhido');
        if (selecionado(el) === true) e.push('selecionado');
        if (el.required || el.getAttribute('aria-required') === 'true') e.push('obrigatorio');
        if (el.readOnly || el.getAttribute('aria-readonly') === 'true') e.push('somente_leitura');
        if (el.getAttribute('aria-invalid') === 'true') e.push('invalido');
        if (ehSenha(el)) e.push('senha');
        if (ret && !naTela(ret)) e.push('fora_da_tela');
        return e;
      };
      const editavel = (el) => {
        if (desabilitado(el)) return false;
        if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) return !el.readOnly;
        if (el instanceof HTMLSelectElement) return true;
        return !!el.isContentEditable;
      };
      const acoesDe = (el, papel, estilo) => {
        const a = [];
        const ehInput = el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement;
        if (['link', 'button', 'checkbox', 'radio', 'switch', 'tab', 'option', 'menuitem',
          'menuitemcheckbox', 'menuitemradio', 'treeitem', 'combobox', 'generic', 'cell', 'img',
          'listitem', 'row'].includes(papel)) a.push('clicar');
        if ((papel === 'textbox' || papel === 'spinbutton' || papel === 'slider' ||
          (papel === 'combobox' && ehInput)) && (ehInput || el.isContentEditable)) a.push('editar');
        if (['checkbox', 'radio', 'switch', 'menuitemcheckbox', 'menuitemradio'].includes(papel)) a.push('marcar');
        if (papel === 'combobox' || papel === 'listbox') a.push('selecionar');
        if (expandido(el) !== null) a.push('expandir');
        if (papel === 'scrollarea' || (estilo && rolavel(el, estilo))) a.push('rolar');
        if (el.tabIndex >= 0 || ehInput) a.push('focar');
        return a;
      };
      const ganhaRef = (papel, acoes) => INTERATIVOS.has(papel) ||
        acoes.includes('clicar') && papel === 'generic' || acoes.includes('editar');

      const geradoAutomatico = /^(:r|radix-|react-|ember|mui-|headlessui-|downshift-)|[0-9a-f]{8,}|\d{4,}/i;
      const idNativoDe = (el) => {
        if (el.id && !geradoAutomatico.test(el.id)) return { tipo: 'id', valor: el.id };
        for (const atr of ['data-testid', 'data-test', 'data-qa']) {
          const v = el.getAttribute(atr);
          if (v) return { tipo: 'testid', valor: v };
        }
        const nome = el.getAttribute('name');
        if (nome && /^(INPUT|SELECT|TEXTAREA|BUTTON)$/.test(el.tagName)) return { tipo: 'name', valor: nome };
        return null;
      };
      const caminhoDe = (el) => {
        const partes = [];
        let e = el;
        while (e && e !== document.documentElement) {
          const p = e.parentNode;
          if (!p) break;
          const irmaos = Array.from(p.children);
          partes.push((p instanceof ShadowRoot ? 's' : '') + irmaos.indexOf(e));
          e = p instanceof ShadowRoot ? p.host : p;
        }
        return partes.reverse().join('/');
      };
      const elementoDoCaminho = (caminho) => {
        if (!caminho) return null;
        let e = document.documentElement;
        for (const parte of caminho.split('/')) {
          if (!e) return null;
          const sombra = parte.startsWith('s');
          const base = sombra ? e.shadowRoot : e;
          if (!base) return null;
          e = base.children[Number(sombra ? parte.slice(1) : parte)] || null;
        }
        return e;
      };

      // ---------- leitura (observar) ----------

      const guardarRef = (leitura, numero, el) => {
        if (!S.leituras.includes(leitura)) {
          S.leituras.push(leitura);
          while (S.leituras.length > MAX_LEITURAS_GUARDADAS) {
            const velha = S.leituras.shift();
            for (const chave of Array.from(S.refs.keys())) if (chave.startsWith(velha + ':')) S.refs.delete(chave);
          }
        }
        S.refs.set(leitura + ':' + numero, new WeakRef(el));
      };
      const descreverRef = (el, papel, nome, fonte, numero, ret, acoes) => ({
        numero, papel, nome, nome_estavel: fonte !== 'valor',
        descricao: descricaoDe(el, fonte) || null, id_nativo: idNativoDe(el),
        caminho: caminhoDe(el), limites: ret, acoes, senha: ehSenha(el),
      });

      const contarFilhos = (el, semTexto) => {
        let n = 0;
        const fila = filhosDe(el);
        let passos = 0;
        while (fila.length && n < 50 && passos < 400) {
          passos++;
          const f = fila.shift();
          if (f.nodeType === 3) { if (!semTexto && limpar(f.textContent)) n++; continue; }
          if (f.nodeType !== 1 || IGNORAR.has(f.tagName)) continue;
          const est = estiloDe(f);
          if (oculto(f, est)) continue;
          if (papelDe(f, est) || f.getAttribute('aria-label')) n++;
          else fila.unshift(...filhosDe(f));
        }
        return n;
      };

      function observar(a) {
        const inicio = performance.now();
        const ctx = {
          leitura: a.id_leitura, n: a.comeco || 1, refs: [], nos: 0, completo: true,
          maxNos: a.max_nos || 1500, prazo: a.prazo_ms || 3000,
          profMax: a.esqueleto ? Math.min(a.profundidade_max || 10, 3) : (a.profundidade_max || 10),
          somenteInterativos: !!a.somente_interativos, compacto: !!a.compacto,
          esqueleto: !!a.esqueleto, limites: !!a.incluir_limites,
        };
        const estourou = () => ctx.nos >= ctx.maxNos || performance.now() - inicio > ctx.prazo;

        const novoRef = (el, papel, nome, fonte, ret, acoes) => {
          const numero = ctx.n++;
          guardarRef(ctx.leitura, numero, el);
          ctx.refs.push(descreverRef(el, papel, nome, fonte, numero, ret, acoes));
          return '@' + ctx.leitura + ':e' + numero;
        };

        // devolve uma lista de nós (um wrapper sem significado devolve os filhos dele)
        const visitar = (no, prof, dentroDeNomeado) => {
          if (no.nodeType === 3) {
            if (ctx.somenteInterativos || dentroDeNomeado) return [];
            const t = limpar(no.textContent, MAX_TEXTO);
            if (!t) return [];
            ctx.nos++;
            return [{ papel: 'text', nome: t }];
          }
          if (no.nodeType !== 1 || IGNORAR.has(no.tagName)) return [];
          const el = no;
          const estilo = estiloDe(el);
          if (oculto(el, estilo)) return [];
          const escondido = invisivel(estilo);
          const papel = escondido ? '' : papelDe(el, estilo);
          const [nome, fonte] = papel ? nomeDe(el, papel) : [limpar(el.getAttribute('aria-label'), MAX_NOME), 'rotulo'];
          const real = !!papel || (!!nome && !escondido);
          if (!real) return visitarFilhos(el, prof, dentroDeNomeado, null);

          ctx.nos++;
          const ret = retangulo(el);
          const acoes = acoesDe(el, papel || 'generic', estilo);
          const noSaida = { papel: papel || 'group' };
          if (nome) noSaida.nome = nome;
          const valor = valorDe(el, papel);
          if (valor) noSaida.valor = valor;
          const estados = estadosDe(el, ret);
          if (estados.length) noSaida.estados = estados;
          if (ctx.limites) noSaida.limites = ret;
          if (ganhaRef(papel, acoes)) noSaida.ref = novoRef(el, papel, nome, fonte, ret, acoes);

          const nomeado = NOME_DO_CONTEUDO.has(papel) && fonte === 'conteudo';
          if (prof + 1 >= ctx.profMax) {
            const n = contarFilhos(el, nomeado || ctx.somenteInterativos);
            if (n > 0) {
              noSaida.filhos_cortados = n;
              if (!noSaida.ref) noSaida.ref = novoRef(el, noSaida.papel, nome, fonte, ret, ['perfurar']);
            }
            return [noSaida];
          }
          const filhos = visitarFilhos(el, prof + 1, nomeado, noSaida);
          if (filhos.length) noSaida.filhos = filhos;
          return [noSaida];
        };
        const visitarFilhos = (el, prof, dentroDeNomeado, noPai) => {
          const saida = [];
          for (const f of filhosDe(el)) {
            if (estourou()) {
              ctx.completo = false;
              if (noPai) noPai.subarvore_cortada = true;
              break;
            }
            saida.push(...visitar(f, prof, dentroDeNomeado));
          }
          return saida;
        };

        let raiz = document.body || document.documentElement;
        if (a.usar_alvo) {
          if (!S.alvo || !S.alvo.isConnected) return { erro: 'raiz_sumiu' };
          raiz = S.alvo;
        }
        let arvore = a.usar_alvo ? visitar(raiz, 0, false) : visitarFilhos(raiz, 0, false, null);
        arvore = podar(arvore, ctx);
        return {
          url: location.href, titulo: document.title, completo: ctx.completo,
          nos_observados: ctx.nos, arvore, refs: ctx.refs, proximo: ctx.n,
          rolagem: [scrollX, scrollY, document.documentElement.scrollWidth, document.documentElement.scrollHeight, innerWidth, innerHeight],
        };
      }

      // -i: só o que tem ref + títulos + contêineres de contexto que guardam algo.
      // compacto: contêiner sem nome e sem ref com um filho só vira o filho.
      const podar = (nos, ctx) => {
        const saida = [];
        for (const no of nos) {
          const filhos = no.filhos ? podar(no.filhos, ctx) : [];
          if (filhos.length) no.filhos = filhos; else delete no.filhos;
          const contexto = CONTEXTO.has(no.papel) && (no.nome || no.papel === 'dialog' || no.papel === 'alertdialog' || no.papel === 'heading');
          if (ctx.somenteInterativos) {
            if (no.ref || no.papel === 'heading' || (contexto && (filhos.length || no.filhos_cortados))) {
              saida.push(no);
            } else {
              saida.push(...filhos);
            }
            continue;
          }
          if (ctx.compacto && !no.ref && !no.nome && no.papel !== 'text' && !no.filhos_cortados && !no.subarvore_cortada) {
            if (filhos.length <= 1) { saida.push(...filhos); continue; }
          }
          saida.push(no);
        }
        return saida;
      };

      // ---------- procurar ----------

      function procurar(a) {
        const inicio = performance.now();
        const prazo = a.prazo_ms || 5000;
        let raiz = document.body || document.documentElement;
        if (a.usar_alvo) {
          if (!S.alvo || !S.alvo.isConnected) return { erro: 'raiz_sumiu' };
          raiz = S.alvo;
        }
        const casa = (texto, procurado) => {
          if (procurado == null || procurado === '') return true;
          const t = normal(texto);
          const p = normal(procurado);
          return a.exato ? t === p : t.includes(p);
        };
        const papeis = new Set();
        let encontrados = [];
        let completo = true;
        for (const el of todosOsElementos(raiz)) {
          if (performance.now() - inicio > prazo) { completo = false; break; }
          const estilo = estiloDe(el);
          if (oculto(el, estilo) || invisivel(estilo)) continue;
          const papel = papelDe(el, estilo);
          if (papel) papeis.add(papel);
          if (a.papel && papel !== a.papel) continue;
          if (!papel && !a.texto) continue;
          const [nome] = papel ? nomeDe(el, papel) : ['', ''];
          if (a.nome != null && !casa(nome, a.nome)) continue;
          if (a.valor != null && !casa(valorDe(el, papel), a.valor)) continue;
          if (a.id_nativo != null) {
            const id = idNativoDe(el);
            if (!id || id.valor !== a.id_nativo) continue;
          }
          if (a.texto != null) {
            const proprio = [nome, valorDe(el, papel), el.innerText].filter(Boolean).join(' ');
            if (!casa(proprio, a.texto)) continue;
          }
          encontrados.push(el);
        }
        if (a.texto != null) {
          // fica o mais fundo de cada galho; sobe até 3 níveis para quem tem ref
          encontrados = encontrados.filter((el) => !encontrados.some((o) => o !== el && contemProfundo(el, o)));
          encontrados = encontrados.map((el) => {
            let e = el;
            for (let i = 0; i < 4 && e; i++, e = pai(e)) {
              if (e.nodeType !== 1) break;
              const est = estiloDe(e);
              const p = papelDe(e, est);
              if (ganhaRef(p, acoesDe(e, p || 'generic', est))) return e;
            }
            return el;
          });
          encontrados = encontrados.filter((el, i) => encontrados.indexOf(el) === i);
        }
        const total = encontrados.length;
        if (a.contar) return { total, completo };
        const limite = a.primeiro ? 1 : (a.limite || 20);
        const refs = [];
        let numero = a.comeco || 1;
        const correspondencias = encontrados.slice(0, limite).map((el) => {
          const estilo = estiloDe(el);
          const papel = papelDe(el, estilo) || 'text';
          const [nome, fonte] = nomeDe(el, papel);
          const ret = retangulo(el);
          const acoes = acoesDe(el, papel, estilo);
          const m = { papel };
          if (nome) m.nome = nome;
          const valor = valorDe(el, papel);
          if (valor) m.valor = valor;
          const estados = estadosDe(el, ret);
          if (estados.length) m.estados = estados;
          if (ganhaRef(papel, acoes)) {
            const n = numero++;
            guardarRef(a.id_leitura, n, el);
            refs.push(descreverRef(el, papel, nome, fonte, n, ret, acoes));
            m.ref = '@' + a.id_leitura + ':e' + n;
          } else {
            m.limites = ret;
            if (papel === 'text') m.texto = limpar(el.innerText, MAX_TEXTO);
          }
          return m;
        });
        const saida = { correspondencias, total, completo, refs, proximo: numero, url: location.href };
        if (a.papel && total === 0) saida.papeis_presentes = Array.from(papeis).sort().slice(0, 40);
        return saida;
      }

      // ---------- localizar (reencontrar a ref) ----------

      const descreverCandidato = (el, indice) => {
        const estilo = estiloDe(el);
        const papel = papelDe(el, estilo) || 'group';
        const [nome] = nomeDe(el, papel);
        return { indice, papel, nome, id_nativo: idNativoDe(el), limites: retangulo(el) };
      };
      function localizar(a) {
        S.candidatos = [];
        const ev = a.evidencia || {};
        const saida = { memoria: [], id: [], caminho: [], busca: [] };
        const vistos = new Map();
        const pegar = (el, camada) => {
          if (!el || !el.isConnected || !visivel(el)) return;
          let i = vistos.get(el);
          if (i === undefined) { i = S.candidatos.push(el) - 1; vistos.set(el, i); }
          saida[camada].push(descreverCandidato(el, i));
        };
        const ref = S.refs.get(a.chave);
        const original = ref ? ref.deref() : undefined;
        // 'removido': o objeto da leitura ainda existe, mas saiu da página
        saida.memoria_estado = original === undefined ? 'desconhecido'
          : original.isConnected ? 'vivo' : 'removido';
        if (original) pegar(original, 'memoria');
        if (ev.id_nativo) {
          const v = CSS.escape(ev.id_nativo.valor);
          const seletor = ev.id_nativo.tipo === 'id' ? `[id="${v}"]`
            : ev.id_nativo.tipo === 'testid' ? `[data-testid="${v}"],[data-test="${v}"],[data-qa="${v}"]`
              : `[name="${v}"]`;
          for (const el of todosOsElementos(document.documentElement)) {
            if (el.matches(seletor)) pegar(el, 'id');
          }
        }
        pegar(elementoDoCaminho(ev.caminho), 'caminho');
        let vistosNaBusca = 0;
        for (const el of todosOsElementos(document.body || document.documentElement)) {
          if (saida.busca.length >= 50 || vistosNaBusca > 20000) break;
          vistosNaBusca++;
          const estilo = estiloDe(el);
          if (oculto(el, estilo)) continue;
          if ((papelDe(el, estilo) || 'group') !== ev.papel) continue;
          pegar(el, 'busca');
        }
        return saida;
      }
      function fixar(a) {
        const el = S.candidatos[a.indice];
        if (!el || !el.isConnected) return false;
        S.alvo = el;
        if (a.chave) S.refs.set(a.chave, new WeakRef(el));
        return true;
      }

      // ---------- dá para agir? ----------

      const elementoNoPonto = (x, y) => {
        let e = document.elementFromPoint(x, y);
        while (e && e.shadowRoot) {
          const dentro = e.shadowRoot.elementFromPoint(x, y);
          if (!dentro || dentro === e) break;
          e = dentro;
        }
        return e;
      };
      const acerta = (el, e) => {
        if (!e) return null;
        if (e === el || contemProfundo(el, e)) return true;
        const rotulo = e.closest && e.closest('label');
        if (rotulo && rotulo.control === el) return true;
        return false;
      };
      const quadro = () => new Promise((ok) => requestAnimationFrame(() => requestAnimationFrame(ok)));
      async function evidencia(a) {
        const el = S.alvo;
        if (!el || !el.isConnected) return { conectado: false };
        const estilo = estiloDe(el);
        const papel = papelDe(el, estilo) || 'group';
        const ret1 = retangulo(el);
        await quadro();
        if (!el.isConnected) return { conectado: false };
        const ret = retangulo(el);
        const saida = {
          conectado: true, papel, visivel: visivel(el), limites: ret, limites_antes: ret1,
          desabilitado: desabilitado(el), editavel: editavel(el), acoes: acoesDe(el, papel, estilo),
          na_tela: naTela(ret), senha: ehSenha(el), pontos: [],
        };
        if (a.ponteiro && saida.visivel && saida.na_tela) {
          const [x, y, w, h] = ret;
          const pontos = [[0.5, 0.5], [0.25, 0.25], [0.75, 0.25], [0.25, 0.75], [0.75, 0.75]]
            .map(([fx, fy]) => [x + w * fx, y + h * fy])
            .filter(([px, py]) => px >= 0 && py >= 0 && px < innerWidth && py < innerHeight);
          for (const [px, py] of pontos) {
            const e = elementoNoPonto(px, py);
            const r = acerta(el, e);
            const p = { x: Math.round(px), y: Math.round(py), acerta: r };
            if (r === false) {
              const est = estiloDe(e);
              const pp = papelDe(e, est) || 'group';
              p.oclusor = { papel: pp, nome: nomeDe(e, pp)[0], limites: retangulo(e) };
            }
            saida.pontos.push(p);
          }
        }
        return saida;
      }
      function estado() {
        const el = S.alvo;
        if (!el || !el.isConnected) return { conectado: false };
        const estilo = estiloDe(el);
        const papel = papelDe(el, estilo) || 'group';
        const [nome] = nomeDe(el, papel);
        const ret = retangulo(el);
        const m = marcado(el);
        return {
          conectado: true, papel, nome, valor: valorDe(el, papel), senha: ehSenha(el),
          estados: estadosDe(el, ret), limites: ret, visivel: visivel(el),
          habilitado: !desabilitado(el), marcado: m === 'misto' ? null : m, misto: m === 'misto',
          expandido: expandido(el), selecionado: selecionado(el), focado: el === ativoProfundo(),
          tamanho_valor: ehSenha(el) ? String(el.value).length : null,
        };
      }

      // ---------- ações semânticas (sem mouse e sem teclado) ----------

      const setterNativo = (el) => {
        const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype
          : el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
        return Object.getOwnPropertyDescriptor(proto, 'value').set;
      };
      const avisar = (el) => {
        el.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      };
      function semantica(a) {
        const el = a.pagina ? null : S.alvo;
        if (!a.pagina && (!el || !el.isConnected)) return { conectado: false };
        switch (a.tipo) {
          case 'clicar': el.click(); return { feito: true };
          case 'focar': el.focus(); return { feito: true, focado: el === ativoProfundo() };
          case 'cursor_no_fim': {
            el.focus();
            if (typeof el.setSelectionRange === 'function' && typeof el.value === 'string') {
              try { el.setSelectionRange(el.value.length, el.value.length); } catch (e) { /* type=email */ }
            } else if (el.isContentEditable) {
              const r = document.createRange(); r.selectNodeContents(el); r.collapse(false);
              const s = getSelection(); s.removeAllRanges(); s.addRange(r);
            }
            return { feito: true, focado: el === ativoProfundo() };
          }
          case 'definir_valor': {
            if (el.isContentEditable && !('value' in el)) {
              el.focus(); el.textContent = a.texto; avisar(el); return { feito: true };
            }
            setterNativo(el).call(el, a.texto); avisar(el); return { feito: true };
          }
          case 'inserir_texto': {
            if (typeof el.setRangeText === 'function' && typeof el.value === 'string') {
              const ini = el.selectionStart ?? el.value.length;
              const fim = el.selectionEnd ?? el.value.length;
              el.setRangeText(a.texto, ini, fim, 'end'); avisar(el); return { feito: true };
            }
            if (el.isContentEditable) { el.focus(); document.execCommand('insertText', false, a.texto); return { feito: true }; }
            return { feito: false };
          }
          case 'abrir_details': {
            const d = el.tagName === 'DETAILS' ? el : el.parentElement;
            if (!d || d.tagName !== 'DETAILS') return { feito: false };
            d.open = !!a.abrir; return { feito: true };
          }
          case 'rolar': {
            const alvo = a.pagina ? (document.scrollingElement || document.documentElement) : el;
            const antes = [alvo.scrollLeft, alvo.scrollTop];
            alvo.scrollBy({ left: a.dx || 0, top: a.dy || 0, behavior: 'instant' });
            return { feito: true, antes, depois: [alvo.scrollLeft, alvo.scrollTop] };
          }
          case 'rolar_ate': {
            el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
            return { feito: true, na_tela: naTela(retangulo(el)) };
          }
          case 'selecionar_opcao': {
            if (!(el instanceof HTMLSelectElement)) return { feito: false };
            const alvoOpcao = Array.from(el.options).find((o) => normal(o.label || o.text) === normal(a.texto)) ||
              Array.from(el.options).find((o) => normal(o.value) === normal(a.texto));
            if (!alvoOpcao) return { feito: false, opcoes: Array.from(el.options).slice(0, 20).map((o) => limpar(o.label || o.text, 60)) };
            setterNativo(el).call(el, alvoOpcao.value); avisar(el);
            return { feito: true };
          }
          default: return { feito: false };
        }
      }
      // combobox/listbox feito em ARIA: depois de abrir, fixa a opção visível com esse nome
      function fixarOpcao(a) {
        const achadas = [];
        const visiveis = [];
        for (const el of todosOsElementos(document.body || document.documentElement)) {
          const estilo = estiloDe(el);
          if (oculto(el, estilo) || invisivel(estilo)) continue;
          if (papelDe(el, estilo) !== 'option') continue;
          const nome = nomeDe(el, 'option')[0];
          if (visiveis.length < 20) visiveis.push(nome);
          if (normal(nome) === normal(a.texto)) achadas.push(el);
        }
        if (achadas.length === 1) S.alvo = achadas[0];
        return { total: achadas.length, opcoes: visiveis };
      }
      function opcoesDoSelect() {
        const el = S.alvo;
        if (!(el instanceof HTMLSelectElement)) return null;
        return Array.from(el.options).map((o) => ({ rotulo: limpar(o.label || o.text, 80), valor: o.value }));
      }

      // ---------- sobreposições e texto (para esperas) ----------

      function superficies() {
        const saida = [];
        const seletor = 'dialog[open],[role=dialog],[role=alertdialog],[role=alert],[role=menu],[role=listbox],[aria-modal=true]';
        for (const el of todosOsElementos(document.body || document.documentElement)) {
          if (saida.length >= 6) break;
          if (!el.matches(seletor) || !visivel(el)) continue;
          if (el.matches('[role=listbox]') && el.tagName === 'SELECT') continue;
          const papel = papelDe(el, estiloDe(el)) || 'dialog';
          saida.push({ papel, nome: nomeDe(el, papel)[0] || null, modal: el.matches('[aria-modal=true]') || (el.tagName === 'DIALOG' && el.matches(':modal')) });
        }
        return saida;
      }
      function contarTexto(a) {
        let n = 0;
        for (const el of todosOsElementos(document.body || document.documentElement)) {
          const estilo = estiloDe(el);
          if (oculto(el, estilo) || invisivel(estilo)) continue;
          const papel = papelDe(el, estilo);
          if (a.papel && papel !== a.papel) continue;
          if (!a.papel && !papel && !el.childNodes.length) continue;
          let proprio;
          if (a.papel) {
            proprio = [nomeDe(el, papel)[0], valorDe(el, papel), descricaoDe(el, '')].filter(Boolean).join(' ');
          } else {
            proprio = Array.from(el.childNodes).filter((c) => c.nodeType === 3).map((c) => c.textContent).join(' ');
            const v = papel ? valorDe(el, papel) : null;
            if (v) proprio += ' ' + v;
            if (papel) proprio += ' ' + nomeDe(el, papel)[0];
          }
          if (!a.texto || normal(proprio).includes(normal(a.texto))) n++;
          if (n >= 1000) break;
        }
        return n;
      }

      // ---------- cursor do agente (só apresentação) ----------

      function cursor(a) {
        let host = document.querySelector('[' + ATR_CURSOR + ']');
        if (!host) {
          host = document.createElement('div');
          host.setAttribute(ATR_CURSOR, '');
          host.style.cssText = 'position:fixed;left:0;top:0;width:0;height:0;z-index:2147483647;pointer-events:none;transition:transform 260ms cubic-bezier(.2,.7,.2,1)';
          const sombra = host.attachShadow({ mode: 'closed' });
          sombra.innerHTML = '<svg width="22" height="22" viewBox="0 0 22 22" style="position:absolute;left:-3px;top:-2px;filter:drop-shadow(0 0 6px var(--cor))"><path d="M3 2 L19 11 L11 13 L8 20 Z" fill="var(--cor)" stroke="#050608" stroke-width="1.4"/></svg><span style="position:absolute;left:18px;top:16px;font:600 11px Inter,system-ui,sans-serif;color:#050608;background:var(--cor);border-radius:999px;padding:2px 8px;white-space:nowrap"></span>';
          host.__rotulo = sombra.querySelector('span');
          host.__sombra = sombra;
          document.documentElement.appendChild(host);
        }
        if (a.remover) { host.remove(); return true; }
        host.style.setProperty('--cor', a.cor || '#E2ECFF');
        host.__rotulo.textContent = a.rotulo || 'Sora';
        host.__rotulo.style.display = a.rotulo === '' ? 'none' : '';
        host.style.transform = `translate(${a.x}px, ${a.y}px)`;
        if (a.clique) {
          const onda = document.createElement('div');
          onda.style.cssText = `position:absolute;left:-14px;top:-14px;width:28px;height:28px;border-radius:50%;border:2px solid ${a.cor || '#E2ECFF'}`;
          host.__sombra.appendChild(onda);
          onda.animate([{ transform: 'scale(.3)', opacity: 1 }, { transform: 'scale(1.6)', opacity: 0 }], { duration: 450, easing: 'ease-out' }).onfinish = () => onda.remove();
        }
        return true;
      }

      return {
        versao: VERSAO, observar, procurar, localizar, fixar, evidencia, estado, semantica,
        opcoes_select: opcoesDoSelect, fixar_opcao: fixarOpcao, superficies, contar_texto: contarTexto, cursor,
        refs_guardadas: () => S.refs.size, alvo_atual: () => S.alvo,
      };
    })();
  }
  return window.__soraArvore[pedido.op](pedido.arg || {});
}
