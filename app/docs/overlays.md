# Overlays: Radix UI × Ariakit × os nossos (item 32)

_Brisa · 2026-10-10 · Parte B, Etapa 1_

## Recomendação

**Não adotar Radix nem Ariakit agora.** Os overlays de `components/overlay` (Modal, Popover, BottomSheet) já resolvem o essencial e custam ~3 kB gz. Uma biblioteca acrescentaria de **+14 a +45 kB gz** (de 9% a 28% do bundle atual, ~162 kB gz) para resolver quatro falhas pontuais, que são baratas de corrigir na mão (abaixo).

Isso não é "claramente melhor", então a API e os arquivos continuam os mesmos. Se a gente precisar de menus com submenu, combobox ou autocomplete, vale reavaliar. Nesse caso a escolha é **Radix**, que é mais leve por componente, publica um pacote por primitiva e vem com o Floating UI embutido.

## Como medimos

O pacote foi isolado num diretório temporário, com `esbuild --bundle --minify` e `react`/`react-dom` como externos. Os números são gzip.

| Pacote | O que entrou | min | **gz** |
|---|---|---:|---:|
| Nossos overlays | Modal + Popover + BottomSheet + useDialogA11y (438 linhas com CSS) | ~9 kB | **~3 kB** |
| `@radix-ui/react-dialog` 1.2 | Dialog | 41,6 kB | **14,2 kB** |
| Radix | Dialog + Popover + DropdownMenu | 105,9 kB | **34,7 kB** |
| `@radix-ui/react-tooltip` 1.3 | Tooltip | 54,7 kB | **19,5 kB** |
| `@ariakit/react` 0.4.41 | Dialog | 57,4 kB | **20,8 kB** |
| Ariakit | Dialog + Popover + Menu | 126,0 kB | **44,8 kB** |
| Ariakit | Tooltip | 87,7 kB | **31,7 kB** |

## Comparação

| Critério | Nossos | Radix | Ariakit |
|---|---|---|---|
| **Foco** (entrada, prender o Tab, devolver ao sair) | ✅ `useDialogA11y`: foco inicial (`initialFocusRef` / `[data-autofocus]`), Tab circular e devolução | ✅ FocusScope | ✅ |
| **Teclado** (Esc, setas no menu, typeahead) | Esc ✅ · setas só onde foi feito à mão (`gestao/MenuItemAcoes`) · sem typeahead | ✅ completo, com typeahead | ✅ completo, com typeahead |
| **Overlays aninhados** (Popover dentro de Modal) | ❌ o Esc fecha **os dois** (dois listeners no `document`, nenhum checa `defaultPrevented`) | ✅ DismissableLayer em pilha | ✅ |
| **Fundo inerte** (leitor de tela não sai do diálogo) | ⚠️ só `aria-modal="true"` (vale para VoiceOver/NVDA atuais; o resto da página continua navegável no modo virtual de alguns leitores) | ✅ `aria-hidden` nos irmãos | ✅ |
| **Trava de rolagem** | ⚠️ `body.overflow = hidden`: o layout pula quando há barra de rolagem | ✅ react-remove-scroll, compensa a barra | ✅ |
| **Posicionamento** | ⚠️ cálculo próprio: inverte em cima/embaixo, prende nas bordas | ✅ Floating UI (flip, shift, collision) | ✅ Floating UI |
| **Portal** | ✅ `createPortal(document.body)` | ✅ | ✅ |
| **Folha arrastável no celular** | ✅ (BottomSheet com arraste e velocidade) | ❌ não existe (teria que manter o nosso) | ❌ |
| **Estilo** | o nosso CSS | sem estilo | sem estilo |
| **API** | `open/onClose/title/...` (props) | compostos (`Root/Trigger/Content`) | stores (`useDialogStore`) |
| **Bundle** | ~3 kB | +14 a +35 kB | +21 a +45 kB |

O Radix ganha em robustez, mas exigiria um adaptador para manter a mesma API de props, e o BottomSheet continuaria sendo nosso. O Ariakit é o mais completo (inclusive para combobox), mas também o mais pesado, e a API em stores destoa do resto do app.

## Correções propostas para os nossos overlays (dono: Forja)

Com estas quatro correções, os nossos overlays cobrem o que Radix e Ariakit dariam para o uso atual. Total estimado: menos de 1 kB.

1. **Pilha de camadas para o Esc.** Um `camadas.ts` com `empilhar(id)` e `topo()`. Modal, Popover e BottomSheet só reagem ao Esc e ao clique fora quando são o topo. Isso corrige o Esc que fecha Popover e Modal juntos.
2. **Fundo inerte.** Ao abrir Modal ou BottomSheet, aplicar `inert` aos irmãos do portal em `document.body` (o `#root`) e remover ao fechar.
3. **Trava de rolagem sem pulo.** Junto com `overflow: hidden`, aplicar `padding-right: <largura da barra>` (`window.innerWidth - document.documentElement.clientWidth`).
4. **Menus.** Usar `MenuItemAcoes` (setas, Home/End, Esc, devolução do foco) como padrão para todo menu "…". O `studio/MenuAgente` ainda é um menu sem navegação por setas.

## Tooltip e Toast

Os componentes de `components/base` (Tooltip e Toast) foram feitos sem biblioteca: o Tooltip do Radix sozinho custaria 19,5 kB gz. Comportamento:
- **Tooltip:** abre ao passar o mouse e ao focar, e fecha com Esc. Usa `aria-describedby` e não prende o foco.
- **Toast:** região `aria-live` (`polite` normal; `assertive` só para erro), com fila e fechamento automático que pausa ao passar o mouse ou focar. Não rouba o foco.
