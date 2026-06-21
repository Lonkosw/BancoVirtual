"""
Inicializa uma partida de teste com jogadores e saldos.
Execute quando quiser popular um banco SQLite local para demonstracao.
"""

import sqlite3


DATABASE = 'banco.db'
BANCO_NOME = '__BANCO__'
SALDO_BANCO = 999999999.0
VALOR_PASSOU_INICIO_PADRAO = 200.0


def garantir_schema(cursor):
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL,
            saldo REAL DEFAULT 0,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_origem_id INTEGER NOT NULL,
            usuario_destino_id INTEGER NOT NULL,
            valor REAL NOT NULL,
            data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            descricao TEXT,
            FOREIGN KEY (usuario_origem_id) REFERENCES usuarios(id),
            FOREIGN KEY (usuario_destino_id) REFERENCES usuarios(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        )
    ''')

    cursor.execute(
        'INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES (?, ?)',
        ('valor_passou_inicio', str(VALOR_PASSOU_INICIO_PADRAO))
    )


def garantir_banco(cursor):
    banco = cursor.execute(
        'SELECT id FROM usuarios WHERE nome = ?',
        (BANCO_NOME,)
    ).fetchone()

    if banco:
        cursor.execute('UPDATE usuarios SET saldo = ? WHERE id = ?', (SALDO_BANCO, banco[0]))
        return banco[0]

    inserir_usuario(cursor, BANCO_NOME, SALDO_BANCO)
    return cursor.lastrowid


def tabela_usuarios_tem_senha(cursor):
    colunas = cursor.execute('PRAGMA table_info(usuarios)').fetchall()
    return any(coluna[1] == 'senha' for coluna in colunas)


def inserir_usuario(cursor, nome, saldo):
    if tabela_usuarios_tem_senha(cursor):
        cursor.execute(
            'INSERT INTO usuarios (nome, senha, saldo) VALUES (?, ?, ?)',
            (nome, 'sem-senha', saldo)
        )
    else:
        cursor.execute(
            'INSERT INTO usuarios (nome, saldo) VALUES (?, ?)',
            (nome, saldo)
        )


def criar_usuarios_teste():
    usuarios_teste = [
        ('Joao', 1500.00),
        ('Maria', 1500.00),
        ('Pedro', 1500.00),
        ('Ana', 1500.00),
        ('Carlos', 1500.00),
    ]

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    garantir_schema(cursor)
    banco_id = garantir_banco(cursor)

    try:
        for nome, saldo in usuarios_teste:
            existente = cursor.execute(
                'SELECT id FROM usuarios WHERE nome = ?',
                (nome,)
            ).fetchone()

            if existente:
                print(f"- Jogador '{nome}' ja existe")
                continue

            inserir_usuario(cursor, nome, saldo)
            jogador_id = cursor.lastrowid
            cursor.execute('''
                INSERT INTO transacoes
                (usuario_origem_id, usuario_destino_id, valor, descricao)
                VALUES (?, ?, ?, ?)
            ''', (banco_id, jogador_id, saldo, 'Saldo inicial de teste'))
            print(f"+ Jogador '{nome}' criado com saldo R$ {saldo:.2f}")

        conn.commit()
        print("\nPartida de teste criada com sucesso.")
        print("PIN admin padrao do app: 1234")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    criar_usuarios_teste()
