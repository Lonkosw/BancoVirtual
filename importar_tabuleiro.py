"""
Importador do tabuleiro de propriedades.

Le um arquivo CSV e popula as tabelas `propriedades` e `alugueis`.

Uso:
    python importar_tabuleiro.py                      # usa tabuleiro_exemplo.csv
    python importar_tabuleiro.py meu_tabuleiro.csv    # usa arquivo informado
    python importar_tabuleiro.py meu.csv --substituir # apaga o tabuleiro atual antes

Colunas esperadas no CSV (cabecalho obrigatorio):
    nome, grupo, posicao, preco_compra, custo_casa, valor_hipoteca,
    aluguel_0, aluguel_1casa, aluguel_2casas, aluguel_3casas, aluguel_4casas, aluguel_hotel

- `nome` e unico. Reimportar o mesmo nome ATUALIZA os dados fixos daquela
  propriedade (preco, alugueis, etc.) sem apagar o dono/casas ja registrados,
  a menos que voce use --substituir.
- Os niveis de aluguel viram: 0=terreno, 1..4=casas, 5=hotel.
"""

import csv
import sqlite3
import sys

DATABASE = 'banco.db'

COLUNAS_ALUGUEL = [
    ('aluguel_0', 0),
    ('aluguel_1casa', 1),
    ('aluguel_2casas', 2),
    ('aluguel_3casas', 3),
    ('aluguel_4casas', 4),
    ('aluguel_hotel', 5),
]


def parse_float(valor, padrao=0.0):
    try:
        return float(str(valor).replace(',', '.').strip())
    except (TypeError, ValueError):
        return padrao


def parse_int(valor, padrao=0):
    try:
        return int(float(str(valor).strip()))
    except (TypeError, ValueError):
        return padrao


def importar(caminho_csv, substituir=False):
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row

    # Garante que as tabelas existam (caso rode antes do app.py).
    db.execute('''
        CREATE TABLE IF NOT EXISTS propriedades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL,
            grupo TEXT,
            posicao INTEGER DEFAULT 0,
            preco_compra REAL DEFAULT 0,
            custo_casa REAL DEFAULT 0,
            valor_hipoteca REAL DEFAULT 0,
            dono_id INTEGER,
            num_casas INTEGER DEFAULT 0,
            tem_hotel INTEGER DEFAULT 0,
            hipotecada INTEGER DEFAULT 0
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS alugueis (
            propriedade_id INTEGER NOT NULL,
            nivel INTEGER NOT NULL,
            valor REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (propriedade_id, nivel)
        )
    ''')

    if substituir:
        db.execute('DELETE FROM alugueis')
        db.execute('DELETE FROM propriedades')
        print('Tabuleiro anterior apagado (--substituir).')

    with open(caminho_csv, newline='', encoding='utf-8-sig') as f:
        leitor = csv.DictReader(f)
        total = 0
        for linha in leitor:
            nome = (linha.get('nome') or '').strip()
            if not nome:
                continue

            grupo = (linha.get('grupo') or '').strip()
            posicao = parse_int(linha.get('posicao'))
            preco = parse_float(linha.get('preco_compra'))
            custo_casa = parse_float(linha.get('custo_casa'))
            hipoteca = parse_float(linha.get('valor_hipoteca'))

            existente = db.execute(
                'SELECT id FROM propriedades WHERE nome = ?', (nome,)
            ).fetchone()

            if existente:
                prop_id = existente['id']
                db.execute('''
                    UPDATE propriedades
                    SET grupo = ?, posicao = ?, preco_compra = ?,
                        custo_casa = ?, valor_hipoteca = ?
                    WHERE id = ?
                ''', (grupo, posicao, preco, custo_casa, hipoteca, prop_id))
            else:
                cur = db.execute('''
                    INSERT INTO propriedades
                        (nome, grupo, posicao, preco_compra, custo_casa, valor_hipoteca)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (nome, grupo, posicao, preco, custo_casa, hipoteca))
                prop_id = cur.lastrowid

            for coluna, nivel in COLUNAS_ALUGUEL:
                valor = parse_float(linha.get(coluna))
                db.execute('''
                    INSERT INTO alugueis (propriedade_id, nivel, valor)
                    VALUES (?, ?, ?)
                    ON CONFLICT(propriedade_id, nivel) DO UPDATE SET valor = excluded.valor
                ''', (prop_id, nivel, valor))

            total += 1
            print(f'  OK  {nome} ({grupo}) - compra R$ {preco:.2f}')

    db.commit()
    db.close()
    print(f'\nImportacao concluida: {total} propriedade(s).')


if __name__ == '__main__':
    args = [a for a in sys.argv[1:]]
    substituir = '--substituir' in args
    args = [a for a in args if a != '--substituir']
    caminho = args[0] if args else 'tabuleiro_exemplo.csv'

    print(f'Importando "{caminho}" para {DATABASE}...')
    try:
        importar(caminho, substituir=substituir)
    except FileNotFoundError:
        print(f'ERRO: arquivo "{caminho}" nao encontrado.')
        sys.exit(1)
