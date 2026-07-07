# Contexto do Projeto — "O Capital"

> Documento de handoff. Resume tudo que foi construído para que outro chat/dev
> consiga continuar de onde paramos. Escrito em pt-BR.

## 1. O que é

**"O Capital"** é um app web que substitui o **dinheiro e as cartas físicas** de um jogo
de tabuleiro estilo **Banco Imobiliário**, com um **tema filosófico marxista**
(burguesia, proletariado, consciência de classe). O tabuleiro continua físico; o app é o
**"banco"/caixa digital** que cada jogador acessa pelo celular.

- **Admin = "Comitê Central"** (protegido por PIN) controla a partida: cria jogadores,
  mexe em saldos, vende propriedades, cobra aluguel, tira cartas.
- **Jogadores = "Camaradas"** entram por nome, veem saldo, propriedades, cartas e transferem.
- **Banco interno = "O Estado"** (usuário `__BANCO__`, saldo "infinito"), origem/destino de
  todo dinheiro que entra/sai do jogo.

## 2. Stack e estrutura

- **Backend:** Python + **Flask** (arquivo único `app.py`).
- **Banco:** **SQLite** (`banco.db`), criado/migrado por `init_db()` no boot.
- **Frontend:** Jinja2 (`templates/`) + `static/style.css` (sem framework JS; JS inline nos templates).
- **Fonte:** Google Fonts **Oswald** (títulos) + Inter (corpo).
- **Exposição:** **Cloudflare Tunnel** (`tools/cloudflared.exe`) gera uma URL pública temporária.

```
project-new/
|-- app.py                    # todo o backend (rotas + helpers + schema)
|-- banco.db                  # SQLite local (NÃO versionado)
|-- importar_tabuleiro.py     # importa o tabuleiro de um CSV
|-- tabuleiro_exemplo.csv     # tabuleiro de exemplo (6 propriedades ficticias)
|-- init_test_users.py        # cria jogadores de teste
|-- requirements.txt
|-- templates/  (base, entrada, dashboard, transferir, admin, admin_entrar, 404, 500)
|-- static/style.css          # tema "Manifesto"
|-- tools/cloudflared.exe      # binario do tunel (NÃO versionado, ~52MB)
```

## 3. Como rodar

```bash
python app.py                              # sobe em http://localhost:5000 (debug=True)
python importar_tabuleiro.py               # importa tabuleiro_exemplo.csv
python importar_tabuleiro.py meu.csv --substituir   # importa um tabuleiro real
tools/cloudflared.exe tunnel --url http://localhost:5000   # gera URL publica
```

- **PIN admin padrão:** `1234` (env `ADMIN_PIN`). Admin em `/admin/entrar`.
- Variáveis de ambiente: `SECRET_KEY`, `DATABASE`, `ADMIN_PIN` (todas com defaults).
- `init_db()` cria as tabelas (idempotente) e **semeia as 45 cartas** no primeiro boot.

## 4. Modelo de dados (tabelas em `banco.db`)

- **usuarios** `(id, nome UNIQUE, saldo, criado_em, falido)` — `nome` também tem índice
  único `idx_usuarios_nome_nocase` (impede duplicata ignorando maiúsc/minúsc).
- **transacoes** `(id, usuario_origem_id, usuario_destino_id, valor, data_hora, descricao)`.
- **configuracoes** `(chave, valor)` — guarda `valor_passou_inicio` (padrão 200).
- **propriedades** `(id, nome, grupo, posicao, preco_compra, custo_casa, valor_hipoteca,
  dono_id, num_casas 0-4, tem_hotel 0/1, hipotecada 0/1)`.
- **alugueis** `(propriedade_id, nivel 0-5, valor)` — 0=terreno, 1-4=casas, 5=hotel.
- **cartas** `(id, classe, numero, titulo, texto, valor, percentual, guardavel)`.
  - `classe` ∈ `burguesia | proletariado | rara`. `valor` = lump-sum imediato (+/-),
    `percentual` = fração do saldo a pagar (ex 0.20). Sem valor/percentual = só exibição.
  - `guardavel=1` nas 2 cartas de proteção (Sindicato / Influência Política).
- **baralho** `(classe, carta_id, usada)` — embaralhamento sem repetir (reembaralha ao esgotar).
- **cartas_tiradas** `(id, carta_id, usuario_id, data_hora, aplicada, valor_aplicado,
  protecao_usada, protecao_usada_em)` — histórico do que cada jogador tirou.

## 5. Funcionalidades implementadas

1. **Caixa/banco:** login por nome, transferências entre jogadores, painel admin com PIN,
   creditar/debitar/definir saldo, "passou pelo início" (valor configurável), reset da partida.
2. **Propriedades:** comprar (admin atribui a um jogador), construir casa/hotel, **cobrar
   aluguel automático** (calcula pelo nível), hipotecar/quitar (sem juros), devolver ao banco.
3. **Importar tabuleiro** de CSV (`importar_tabuleiro.py`). O usuário vai mandar um CSV real
   com colunas: `nome,grupo,posicao,preco_compra,custo_casa,valor_hipoteca,aluguel_0,
   aluguel_1casa,aluguel_2casas,aluguel_3casas,aluguel_4casas,aluguel_hotel`.
4. **Falência:** ao cobrar aluguel/carta acima do saldo, o sistema **vende os bens ao banco**
   (terreno pelo valor_hipoteca, construções pelo custo_casa), paga o credor e, se ainda
   faltar, **decreta falência** (`falido=1`). Visível: **carimbo "FALIDO"** + card acinzentado
   no admin e na tela do jogador; **contador ativos/falidos** no topo do admin.
5. **Cartas de Sorte/Revés (45):** admin escolhe camarada + baralho e **tira carta** (sem
   repetir). **Aplica o dinheiro com 1 clique** ("Aplicar ao caixa"); efeitos de mover/turno
   são texto pro jogador executar no tabuleiro físico. A carta **aparece sozinha** na tela do
   jogador (polling em `/api/minhas-cartas` a cada 4s) com **badge "NOVA"** e animação de
   revelação só na carta nova.
6. **Inventário de cartas de proteção ("Usar carta"):** as 2 cartas guardáveis entram no
   inventário do jogador; ele clica **"Usar"** quando quiser (**token + aviso** — não cancela
   cobrança automaticamente). O admin **vê quem tem proteção** e recebe **aviso quando alguém
   usa** (aba Cartas → painel "Proteções").
7. **Tema visual "Manifesto":** construtivista soviético, escuro + vermelho-sangue + **neon** +
   latão/dourado; fonte-cartaz Oswald. Vocabulário leve (Comitê Central, Camaradas, O Estado).
   **Painel admin com abas** (Camaradas / Propriedades / Cartas / Movimentos / Partida) que
   **lembram a última aba** via localStorage (não volta pro topo após cada ação). Tela do
   jogador também em abas (Cartas / Propriedades / Histórico).
8. **Identidade:** normalização de nomes (trim + colapsa espaços) e comparação
   case-insensitive no login e no cadastro → não cria mais contas sósias ("Theo" == "theo").

## 6. Decisões de design importantes

- **O app é um BANCO, não um motor de tabuleiro/turnos.** Dinheiro é automatizado; mover
  casas, pular turnos e efeitos permanentes são **exibidos como texto** para execução física.
- **Admin controla** compra/aluguel/cartas (não os jogadores) — exceto **usar proteção**, que
  é ação do jogador.
- **Falência:** vende ao banco → paga credor → decreta falido. **Sem juros de hipoteca.**
- **Cartas:** admin escolhe o baralho a cada sorteio (não há classe fixa por jogador).
  Baralho embaralhado **sem repetir**.
- **Proteção:** **token + aviso** (o app confia que o admin não cobra), não cancela automático.

## 7. Rotas principais (em `app.py`)

- Jogador: `/entrada` (login), `/dashboard`, `/transferir`, `/sair`,
  `/cartas/<tirada_id>/usar` (usar proteção), `/api/saldo`, `/api/minhas-cartas`.
- Admin (`@requer_admin`): `/admin`, `/admin/entrar`, `/admin/jogadores/novo`,
  `.../saldo`, `.../passou-inicio`, `.../excluir`, `/admin/resetar`,
  `/admin/propriedades/<id>/{comprar,construir,vender-casa,hipotecar,liberar,cobrar}`,
  `/admin/cartas/tirar`, `/admin/cartas/<tirada_id>/aplicar`.
- Helpers-chave: `liquidar_todas_propriedades`, `aplicar_valor_carta`, `tirar_carta`,
  `calcular_aluguel_atual`, `normalizar_nome`, `garantir_*` (migrações idempotentes no init_db).

## 8. Estado atual / repositório

- **GitHub:** https://github.com/Lonkosw/BancoVirtual — branch **`21/06`** (default do repo).
- **NÃO versionado** (via `.gitignore`): `banco.db` e `*.db`, `*.log`, `tools/`, `*.bak`, `.env`.
- `banco.db` local tinha os jogadores `caua`, `theo` (dados reais de teste).
- Servidor roda com `debug=True` (auto-reload). Já caiu algumas vezes no reload —
  reiniciar com `nohup python app.py > flask.out.log 2> flask.err.log &`.

## 9. Gotchas (armadilhas)

- A **URL do túnel Cloudflare muda a cada reinício** (é grátis/efêmera). Sempre reextrair do
  log: `grep -hoE "https://[a-z-]+\.trycloudflare\.com" cloudflared.err.log`.
- Depois de mudar CSS/JS, o navegador cacheia → **Ctrl+F5**.
- `SECRET_KEY`/`ADMIN_PIN` são defaults — trocar por env em produção; `debug=True` deve sair.
- Mudanças em templates/CSS são servidas na hora (sem restart); mudança em `app.py` recarrega.

## 10. Pendências e próximas ideias

**Documentação:** `README.md` e `INICIO_RAPIDO.md` ainda descrevem o app antigo
("Banco Imobiliário") — precisam ser atualizados para "O Capital".

**Backlog de ideias (o usuário escolhe o que fazer):**
1. **Vitória / ranking de patrimônio** (fecho natural da falência).
2. **QR code** para os jogadores entrarem na partida.
3. **Saldo em tempo real** no dashboard (mesmo polling das cartas).
4. **Desfazer (undo)** da última ação do admin.
5. **Autenticação por PIN** por jogador (a normalização de nomes já foi feita; falta o PIN).
6. **Efeitos automáticos na largada** (cartas "+$X permanente/por largada").
7. **Sons e vibração** (receber dinheiro, tirar carta, falir).
8. **Modo telão/placar** (tela só-leitura para uma TV).
9. **Relatório de fim de partida** (estatísticas + evolução de patrimônio).
10. **Editor de cartas/tabuleiro** no admin (sem CSV/código).

**Evolução da falência (fase 2):** congelar jogador falido (some das listas de
transferência/cobrança), botões "Reabilitar" / "Remover da partida", condição de fim de jogo.

**Evolução das cartas (fase 2):** as cartas de proteção hoje são "token + aviso"; poderiam
**cancelar automaticamente** a próxima cobrança se desejado.
