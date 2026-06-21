# Banco Imobiliario Online

Aplicacao Flask para administrar o dinheiro de uma partida estilo Banco Imobiliario. Jogadores entram pelo nome, consultam saldo, transferem dinheiro entre si e o banco da mesa gerencia saldos, jogadores e historico global por um painel administrativo.

## Funcionalidades

- Entrada rapida de jogador por nome, sem cadastro e sem senha.
- Dashboard individual com saldo atual e historico das ultimas transacoes.
- Transferencias entre jogadores com validacao de saldo.
- Painel do banco protegido por PIN.
- Criacao de jogadores com saldo inicial.
- Credito, debito ou definicao direta de saldo pelo banco.
- Valor configuravel para "passou pelo inicio", com botao rapido por jogador.
- Historico global dos ultimos movimentos da partida.
- Reset completo de jogadores e historico.
- APIs JSON para saldo, lista de jogadores e resumo administrativo.
- Layout responsivo para celular, tablet e desktop.

## Estrutura

```text
project-new/
|-- app.py                    # Servidor Flask e rotas
|-- banco.db                  # Banco SQLite local
|-- init_test_users.py        # Popula uma partida de teste
|-- requirements.txt          # Dependencias Python
|-- INICIO_RAPIDO.md          # Guia curto de execucao
|-- templates/
|   |-- admin.html            # Painel do banco
|   |-- admin_entrar.html     # Entrada por PIN do banco
|   |-- base.html             # Layout base
|   |-- dashboard.html        # Tela do jogador
|   |-- entrada.html          # Entrada por nome
|   |-- transferir.html       # Transferencia entre jogadores
|   |-- 404.html
|   `-- 500.html
`-- static/
    `-- style.css             # Estilos responsivos
```

## Instalacao

Pre-requisitos:

- Python 3.7 ou superior
- pip

Instale as dependencias:

```bash
pip install -r requirements.txt
```

Execute a aplicacao:

```bash
python app.py
```

Acesse:

```text
http://localhost:5000
```

## Fluxo de uso

### Jogador

1. Abra `http://localhost:5000`.
2. Digite o nome do jogador.
3. Veja saldo e historico.
4. Use "Transferir dinheiro" para enviar valores a outro jogador.

Se o nome ainda nao existir, o app cria o jogador automaticamente com saldo `0`. Para comecar uma partida com saldo inicial, use o painel do banco.

### Banco da partida

1. Clique em "Banco" na barra superior.
2. Digite o PIN administrativo.
3. Crie jogadores e defina saldos iniciais.
4. Configure o valor de "Passar pelo inicio".
5. Use o botao "Passou pelo inicio" no cartao do jogador quando ele completar a volta.
6. Use as acoes "Creditar", "Debitar" ou "Definir" para controlar dinheiro durante a partida.
7. Consulte o historico global para auditar movimentacoes.

PIN padrao:

```text
1234
```

Altere em producao com variavel de ambiente:

```bash
set ADMIN_PIN=seu-pin
python app.py
```

No PowerShell:

```powershell
$env:ADMIN_PIN="seu-pin"
python app.py
```

## Dados de teste

Para criar jogadores de exemplo:

```bash
python init_test_users.py
```

O script cria:

- Joao
- Maria
- Pedro
- Ana
- Carlos

Cada um recebe saldo inicial de R$ 1500,00 registrado como movimento do banco.

## APIs

Rotas de jogador:

- `GET /api/usuarios`: lista nomes dos outros jogadores.
- `GET /api/saldo`: retorna o saldo do jogador logado.

Rota administrativa:

- `GET /api/admin/resumo`: retorna quantidade de jogadores, saldo total em jogo, numero de transacoes e `valor_passou_inicio`.

As rotas de jogador exigem sessao de jogador. A rota administrativa exige sessao de banco.

## Configuracao

Variaveis opcionais:

```text
SECRET_KEY  Chave de sessao Flask
DATABASE    Caminho do arquivo SQLite
ADMIN_PIN   PIN do painel do banco
```

Exemplo PowerShell:

```powershell
$env:SECRET_KEY="gere-uma-chave-forte"
$env:DATABASE="banco.db"
$env:ADMIN_PIN="9876"
python app.py
```

## Cloudflare Tunnel

Com o servidor local rodando, execute em outro terminal:

```bash
cloudflared tunnel --url http://localhost:5000
```

Compartilhe a URL gerada com os jogadores. O Flask ja roda em `0.0.0.0`, entao o tunnel consegue encaminhar para a porta local `5000`.

## Observacoes de seguranca

Este projeto foi desenhado para partidas locais e rapidas.

Antes de usar em ambiente publico:

- Troque `SECRET_KEY`.
- Troque `ADMIN_PIN`.
- Desative `debug=True` em producao.
- Use HTTPS, por exemplo via Cloudflare Tunnel.
- Faca backup do `banco.db` quando a partida importar.

## Desenvolvimento

Teste rapido de sintaxe:

```bash
python -m compileall app.py init_test_users.py
```

Como a aplicacao usa SQLite, e simples testar com bancos temporarios ou copias do `banco.db`.
