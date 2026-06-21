# Inicio Rapido

## 1. Instale dependencias

```bash
pip install -r requirements.txt
```

## 2. Rode o servidor

```bash
python app.py
```

Abra:

```text
http://localhost:5000
```

## 3. Entre como jogador

Na tela inicial, digite o nome do jogador.

- Se o jogador ja existe, ele entra na propria conta.
- Se ainda nao existe, ele e criado com saldo `0`.
- Para dar saldo inicial, use o painel do banco.

## 4. Entre no painel do banco

Clique em "Banco" na barra superior.

PIN padrao:

```text
1234
```

No painel do banco voce pode:

- Criar jogadores com saldo inicial.
- Definir quanto cada jogador recebe ao passar pelo inicio.
- Pagar rapidamente "Passou pelo inicio" no cartao de cada jogador.
- Creditar dinheiro.
- Debitar dinheiro.
- Definir saldo exato.
- Ver o historico global.
- Resetar a partida digitando `RESETAR`.

## 5. Popular dados de teste

Opcional:

```bash
python init_test_users.py
```

Isso cria Joao, Maria, Pedro, Ana e Carlos com R$ 1500,00 cada.

## Dicas

- Troque o PIN antes de jogar com outras pessoas.
- Use o banco para iniciar saldos e resolver pagamentos ao tabuleiro.
- Use "Passou pelo inicio" quando um jogador completar a volta.
- Use transferencias entre jogadores para aluguel, compra/venda ou acordos.
- Faca backup de `banco.db` se quiser preservar uma partida.

## Acesso remoto

Com o app rodando:

```bash
cloudflared tunnel --url http://localhost:5000
```

Compartilhe a URL gerada com os participantes.
