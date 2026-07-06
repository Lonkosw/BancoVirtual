"""
Banco Imobiliario Online - Backend Flask
Sistema para administracao de caixa e transferencias entre jogadores.
"""

from datetime import datetime
from functools import wraps
import os
import random
import sqlite3

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'mude-esta-chave-em-producao')
app.config['DATABASE'] = os.environ.get('DATABASE', 'banco.db')
app.config['ADMIN_PIN'] = os.environ.get('ADMIN_PIN', '1234')
BANCO_NOME = '__BANCO__'
SALDO_BANCO = 999999999.0
VALOR_PASSOU_INICIO_PADRAO = 200.0


# ============== BANCO DE DADOS ==============

def get_db():
    """Conecta ao banco de dados SQLite."""
    db = sqlite3.connect(app.config['DATABASE'])
    db.row_factory = sqlite3.Row
    return db


def tabela_usuarios_tem_senha(db):
    colunas = db.execute('PRAGMA table_info(usuarios)').fetchall()
    return any(coluna['name'] == 'senha' for coluna in colunas)


def inserir_usuario(db, nome, saldo):
    """Insere usuario em schemas novos e em bancos antigos com coluna senha."""
    if tabela_usuarios_tem_senha(db):
        cursor = db.execute(
            'INSERT INTO usuarios (nome, senha, saldo) VALUES (?, ?, ?)',
            (nome, 'sem-senha', saldo)
        )
    else:
        cursor = db.execute(
            'INSERT INTO usuarios (nome, saldo) VALUES (?, ?)',
            (nome, saldo)
        )
    return cursor.lastrowid


def init_db():
    """Inicializa as tabelas do banco de dados."""
    with app.app_context():
        db = get_db()
        cursor = db.cursor()

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

        cursor.execute('''
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
                hipotecada INTEGER DEFAULT 0,
                FOREIGN KEY (dono_id) REFERENCES usuarios(id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alugueis (
                propriedade_id INTEGER NOT NULL,
                nivel INTEGER NOT NULL,
                valor REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (propriedade_id, nivel),
                FOREIGN KEY (propriedade_id) REFERENCES propriedades(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cartas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                classe TEXT NOT NULL,
                numero INTEGER NOT NULL,
                titulo TEXT NOT NULL,
                texto TEXT NOT NULL,
                valor REAL,
                percentual REAL,
                guardavel INTEGER DEFAULT 0
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS baralho (
                classe TEXT NOT NULL,
                carta_id INTEGER NOT NULL,
                usada INTEGER DEFAULT 0,
                PRIMARY KEY (classe, carta_id),
                FOREIGN KEY (carta_id) REFERENCES cartas(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cartas_tiradas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                carta_id INTEGER NOT NULL,
                usuario_id INTEGER NOT NULL,
                data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                aplicada INTEGER DEFAULT 0,
                valor_aplicado REAL,
                protecao_usada INTEGER DEFAULT 0,
                protecao_usada_em TIMESTAMP,
                FOREIGN KEY (carta_id) REFERENCES cartas(id),
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
            )
        ''')

        db.commit()
        garantir_coluna_falido(db)
        garantir_usuario_banco(db)
        garantir_configuracoes(db)
        garantir_cartas(db)
        garantir_colunas_protecao(db)
        garantir_indice_nome(db)
        db.close()
        print("Banco de dados inicializado")


def garantir_coluna_falido(db):
    """Adiciona a coluna 'falido' em bancos antigos sem quebrar o schema."""
    colunas = db.execute('PRAGMA table_info(usuarios)').fetchall()
    if not any(coluna['name'] == 'falido' for coluna in colunas):
        db.execute('ALTER TABLE usuarios ADD COLUMN falido INTEGER DEFAULT 0')
        db.commit()


def garantir_indice_nome(db):
    """Impede nomes duplicados ignorando maiusculas/minusculas e acentuacao ASCII.

    Se ainda houver duplicados no banco, a criacao falha e a protecao fica inativa
    ate que sejam resolvidos (o codigo ja bloqueia novos duplicados de qualquer forma).
    """
    try:
        db.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_nome_nocase '
            'ON usuarios(nome COLLATE NOCASE)'
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()


def garantir_usuario_banco(db):
    """Cria o usuario interno que representa o caixa do jogo."""
    banco = db.execute('SELECT id FROM usuarios WHERE nome = ?', (BANCO_NOME,)).fetchone()
    if banco:
        db.execute('UPDATE usuarios SET saldo = ? WHERE id = ?', (SALDO_BANCO, banco['id']))
    else:
        inserir_usuario(db, BANCO_NOME, SALDO_BANCO)
    db.commit()


def obter_banco_id(db):
    garantir_usuario_banco(db)
    banco = db.execute('SELECT id FROM usuarios WHERE nome = ?', (BANCO_NOME,)).fetchone()
    return banco['id']


def garantir_configuracoes(db):
    existente = db.execute(
        'SELECT valor FROM configuracoes WHERE chave = ?',
        ('valor_passou_inicio',)
    ).fetchone()

    if not existente:
        db.execute(
            'INSERT INTO configuracoes (chave, valor) VALUES (?, ?)',
            ('valor_passou_inicio', str(VALOR_PASSOU_INICIO_PADRAO))
        )
        db.commit()


def obter_config_float(db, chave, padrao):
    garantir_configuracoes(db)
    row = db.execute('SELECT valor FROM configuracoes WHERE chave = ?', (chave,)).fetchone()
    if not row:
        return padrao
    try:
        return float(row['valor'])
    except (TypeError, ValueError):
        return padrao


def salvar_config(db, chave, valor):
    db.execute('''
        INSERT INTO configuracoes (chave, valor)
        VALUES (?, ?)
        ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor
    ''', (chave, str(valor)))


def obter_jogador(db, usuario_id):
    return db.execute(
        'SELECT id, nome, saldo, criado_em, falido FROM usuarios WHERE id = ? AND nome != ?',
        (usuario_id, BANCO_NOME)
    ).fetchone()


def listar_jogadores(db):
    return db.execute(
        'SELECT id, nome, saldo, criado_em, falido FROM usuarios WHERE nome != ? ORDER BY nome',
        (BANCO_NOME,)
    ).fetchall()


def registrar_movimento(db, origem_id, destino_id, valor, descricao):
    db.execute('''
        INSERT INTO transacoes
        (usuario_origem_id, usuario_destino_id, valor, descricao)
        VALUES (?, ?, ?, ?)
    ''', (origem_id, destino_id, valor, descricao))


def formatar_descricao(texto):
    texto = (texto or '').strip()
    return texto[:140] if texto else None


def normalizar_nome(nome):
    """Remove espacos nas pontas e colapsa espacos internos, evitando nomes sosias."""
    return ' '.join((nome or '').split())


# ============== PROPRIEDADES ==============

NIVEL_HOTEL = 5  # nivel 0 = terreno puro, 1-4 = casas, 5 = hotel


def nivel_construcao(prop):
    """Nivel atual de construcao: 0 (terreno), 1-4 (casas) ou 5 (hotel)."""
    if prop['tem_hotel']:
        return NIVEL_HOTEL
    return prop['num_casas']


def unidades_construidas(prop):
    """Quantas unidades foram pagas (para calcular liquidacao)."""
    if prop['tem_hotel']:
        return 5  # 4 casas convertidas + 1 hotel
    return prop['num_casas']


def calcular_aluguel_atual(db, prop):
    """Aluguel devido no nivel atual. Zero se hipotecada."""
    if prop['hipotecada']:
        return 0.0
    nivel = nivel_construcao(prop)
    row = db.execute(
        'SELECT valor FROM alugueis WHERE propriedade_id = ? AND nivel = ?',
        (prop['id'], nivel)
    ).fetchone()
    return float(row['valor']) if row else 0.0


def valor_liquidacao(prop):
    """Quanto o banco paga ao recomprar a propriedade em uma divida/falencia.

    Terreno volta pelo valor de hipoteca (0 se ja hipotecada, pois o dinheiro
    ja foi adiantado). Construcoes sao devolvidas pelo custo_casa pago em cada.
    """
    terreno = 0.0 if prop['hipotecada'] else float(prop['valor_hipoteca'])
    construcoes = unidades_construidas(prop) * float(prop['custo_casa'])
    return terreno + construcoes


def obter_propriedade(db, propriedade_id):
    return db.execute(
        'SELECT * FROM propriedades WHERE id = ?', (propriedade_id,)
    ).fetchone()


def listar_propriedades(db):
    """Lista propriedades com nome do dono, ordenadas por posicao no tabuleiro."""
    return db.execute('''
        SELECT p.*, u.nome AS dono_nome
        FROM propriedades p
        LEFT JOIN usuarios u ON p.dono_id = u.id
        ORDER BY p.posicao, p.grupo, p.nome
    ''').fetchall()


def propriedades_do_jogador(db, usuario_id):
    return db.execute(
        'SELECT * FROM propriedades WHERE dono_id = ? ORDER BY posicao, nome',
        (usuario_id,)
    ).fetchall()


def liquidar_todas_propriedades(db, usuario_id, banco_id, descricao):
    """Vende todas as propriedades do jogador ao banco e credita o saldo dele.

    Retorna o total arrecadado. As propriedades voltam a ficar disponiveis.
    """
    props = propriedades_do_jogador(db, usuario_id)
    total = 0.0
    for p in props:
        valor = valor_liquidacao(p)
        if valor > 0:
            db.execute(
                'UPDATE usuarios SET saldo = saldo + ? WHERE id = ?',
                (valor, usuario_id)
            )
            registrar_movimento(
                db, banco_id, usuario_id, valor,
                f'{descricao}: venda de {p["nome"]}'
            )
            total += valor
        db.execute('''
            UPDATE propriedades
            SET dono_id = NULL, num_casas = 0, tem_hotel = 0, hipotecada = 0
            WHERE id = ?
        ''', (p['id'],))
    return total


def rotulo_nivel(prop):
    """Texto amigavel do nivel de construcao."""
    if prop['tem_hotel']:
        return 'Hotel'
    if prop['num_casas'] == 0:
        return 'Terreno'
    if prop['num_casas'] == 1:
        return '1 casa'
    return f"{prop['num_casas']} casas"


# ============== CARTAS (SORTE / REVES) ==============

# (classe, numero, titulo, texto, valor, percentual)
# valor: montante imediato no caixa (+ receber / - pagar). None = sem dinheiro automatico.
# percentual: fracao do saldo a pagar (ex: 0.20). Cartas sem valor/percentual sao so exibicao;
# a parte de mover/pular turno/etc. o jogador executa no tabuleiro fisico pelo texto.
CARTAS_SEED = [
    # ----- BURGUESIA -----
    ('burguesia', 1, 'Leitura do Testamento',
     'Seu avo era um grande latifundiario e deixou parte da fortuna para voce. Receba 1 propriedade agricola aleatoria gratuitamente.', None, None),
    ('burguesia', 2, 'Escola Bilingue Privada', 'Pague $500 e avance 2 casas.', -500.0, None),
    ('burguesia', 3, 'Estagio na Empresa do Pai', 'Receba $1.000.', 1000.0, None),
    ('burguesia', 4, 'Carro Importado de Presente', 'Avance 3 casas.', None, None),
    ('burguesia', 5, 'Recebendo as Acoes da Familia', 'Passe pela largada: +$1.500.', 1500.0, None),
    ('burguesia', 6, 'Compra de Titulos Publicos', 'Pague $2.000. Receba +$300 por largada.', -2000.0, None),
    ('burguesia', 7, 'Isencao Fiscal Governamental', 'Nao pague impostos por 2 voltas.', None, None),
    ('burguesia', 8, 'Aquisicao de Industria Textil', 'Pague $5.000. Receba $1.000 ao passar.', -5000.0, None),
    ('burguesia', 9, 'Fusao de Empresas', 'Dobre o aluguel de uma propriedade.', None, None),
    ('burguesia', 10, 'Condominio de Luxo', 'Compre imovel por $4.500. Aluguel $1.200.', None, None),
    ('burguesia', 11, 'Investimento em Startup', 'Pague $1.500. Proxima largada: $3.000.', -1500.0, None),
    ('burguesia', 12, 'Lobby Bem-Sucedido', 'Receba $2.000.', 2000.0, None),
    ('burguesia', 13, 'Expansao Internacional', 'Avance ate a proxima propriedade e receba $1.000.', 1000.0, None),
    ('burguesia', 14, 'Processo Trabalhista Comum', 'Pague $700.', -700.0, None),
    ('burguesia', 15, 'Flutuacao Cambial', 'Pague $500.', -500.0, None),
    ('burguesia', 16, 'Auditoria da Receita Federal', 'Pague 20% do dinheiro.', None, 0.20),
    ('burguesia', 17, 'Escandalo de Compliance', 'Pague $4.000 e fique 2 rodadas sem alugueis.', -4000.0, None),
    ('burguesia', 18, 'Quebra da Bolha Especulativa', 'Propriedades perdem metade do valor.', None, None),
    ('burguesia', 19, 'Privatizacao Fracassada', 'Pague $1.500.', -1500.0, None),
    ('burguesia', 20, 'Crise Economica', 'Nao receba alugueis por 1 rodada.', None, None),
    # ----- PROLETARIADO -----
    ('proletariado', 1, 'Trabalho Infantil / Jovem Aprendiz', 'Receba $200.', 200.0, None),
    ('proletariado', 2, 'Promocao por Tempo de Servico', '+ $500 permanente na largada.', None, None),
    ('proletariado', 3, 'Bico Altamente Lucrativo', 'Receba $800 e avance 1 casa.', 800.0, None),
    ('proletariado', 4, 'Bolsa de Estudos Integral', 'Receba $5.000 e avance 5 casas.', 5000.0, None),
    ('proletariado', 5, 'Consciencia de Classe / Sindicato', 'Ganhe uma carta de protecao.', None, None),
    ('proletariado', 6, 'Mutirao da Comunidade', 'Receba $800.', 800.0, None),
    ('proletariado', 7, 'Concurso Publico', '+ $500 permanente na largada.', None, None),
    ('proletariado', 8, 'Curso Tecnico Gratuito', 'Avance 3 casas e receba $300.', 300.0, None),
    ('proletariado', 9, 'Decimo Terceiro Salario', 'Receba $1.000.', 1000.0, None),
    ('proletariado', 10, 'Cooperativa de Trabalhadores', 'Receba $1.500 e ignore o proximo aluguel.', 1500.0, None),
    ('proletariado', 11, 'Falecimento do Pai', 'Pague $600 e $100 nas proximas 5 largadas.', -600.0, None),
    ('proletariado', 12, 'Escola Publica Sucateada', 'Volte 2 casas.', None, None),
    ('proletariado', 13, 'Faculdade Noturna', 'Pague $300 por 5 rodadas.', None, None),
    ('proletariado', 14, 'Estagio Nao Remunerado', 'Fique uma rodada sem salario.', None, None),
    ('proletariado', 15, 'Pane no Onibus', 'Pague $100 ou perca a vez.', None, None),
    ('proletariado', 16, 'Desemprego de Longa Duracao', 'Fique 1 rodada sem jogar.', None, None),
    ('proletariado', 17, 'Demissao por Reestruturacao', 'Pague $400 e perca o proximo salario.', -400.0, None),
    ('proletariado', 18, 'Inflacao do Supermercado', 'Pague $350.', -350.0, None),
    ('proletariado', 19, 'Burnout', 'Fique 2 rodadas sem jogar.', None, None),
    ('proletariado', 20, 'Enchente na Periferia', 'Pague $1.200 ou fique 3 rodadas sem jogar.', None, None),
    # ----- RARAS -----
    ('rara', 1, 'Heranca Bilionaria', 'Receba $8.000 e avance ate a proxima propriedade.', 8000.0, None),
    ('rara', 2, 'Influencia Politica', 'Ignore uma penalidade.', None, None),
    ('rara', 3, 'Indenizacao Trabalhista', 'Receba $2.000.', 2000.0, None),
    ('rara', 4, 'Viralizou na Internet', 'Receba $3.000 e avance 5 casas.', 3000.0, None),
    ('rara', 5, 'Ascensao Social', 'Receba $10.000 e escolha migrar para a burguesia ou permanecer.', 10000.0, None),
]

CLASSES_VALIDAS = ('burguesia', 'proletariado', 'rara')

ROTULO_CLASSE = {
    'burguesia': 'Burguesia',
    'proletariado': 'Proletariado',
    'rara': 'Rara',
}


def garantir_cartas(db):
    """Semeia as cartas e o baralho apenas se ainda nao existirem."""
    total = db.execute('SELECT COUNT(*) AS c FROM cartas').fetchone()['c']
    if total:
        return
    for (classe, numero, titulo, texto, valor, percentual) in CARTAS_SEED:
        cur = db.execute(
            'INSERT INTO cartas (classe, numero, titulo, texto, valor, percentual) VALUES (?, ?, ?, ?, ?, ?)',
            (classe, numero, titulo, texto, valor, percentual)
        )
        db.execute(
            'INSERT INTO baralho (classe, carta_id, usada) VALUES (?, ?, 0)',
            (classe, cur.lastrowid)
        )
    db.commit()


def tirar_carta(db, classe):
    """Sorteia uma carta do baralho da classe, sem repetir ate esgotar (dai reembaralha)."""
    disponiveis = db.execute(
        'SELECT carta_id FROM baralho WHERE classe = ? AND usada = 0', (classe,)
    ).fetchall()

    if not disponiveis:
        db.execute('UPDATE baralho SET usada = 0 WHERE classe = ?', (classe,))
        db.commit()
        disponiveis = db.execute(
            'SELECT carta_id FROM baralho WHERE classe = ? AND usada = 0', (classe,)
        ).fetchall()

    if not disponiveis:
        return None

    escolhido = random.choice([linha['carta_id'] for linha in disponiveis])
    db.execute(
        'UPDATE baralho SET usada = 1 WHERE classe = ? AND carta_id = ?',
        (classe, escolhido)
    )
    db.commit()
    return db.execute('SELECT * FROM cartas WHERE id = ?', (escolhido,)).fetchone()


def carta_tem_dinheiro(carta):
    return carta['valor'] is not None or carta['percentual'] is not None


def aplicar_valor_carta(db, usuario_id, carta, banco_id):
    """Aplica a parte de dinheiro da carta no caixa. Retorna o valor efetivo (sinalizado).

    Recebimento credita do Estado. Pagamento maior que o saldo vende os bens do jogador
    (mesmo fluxo de falencia do aluguel) e, se ainda faltar, decreta falencia.
    """
    row = db.execute('SELECT saldo FROM usuarios WHERE id = ?', (usuario_id,)).fetchone()
    saldo = float(row['saldo']) if row else 0.0

    if carta['percentual'] is not None:
        montante = -(saldo * float(carta['percentual']))
    elif carta['valor'] is not None:
        montante = float(carta['valor'])
    else:
        return 0.0

    descricao = f'Carta: {carta["titulo"]}'

    if montante >= 0:
        db.execute('UPDATE usuarios SET saldo = saldo + ? WHERE id = ?', (montante, usuario_id))
        registrar_movimento(db, banco_id, usuario_id, montante, descricao)
        return montante

    pagar = -montante
    if saldo < pagar:
        saldo += liquidar_todas_propriedades(db, usuario_id, banco_id, 'Falencia (carta)')

    if saldo >= pagar:
        db.execute('UPDATE usuarios SET saldo = saldo - ? WHERE id = ?', (pagar, usuario_id))
        registrar_movimento(db, usuario_id, banco_id, pagar, descricao)
        return -pagar

    resto = max(saldo, 0.0)
    if resto > 0:
        registrar_movimento(db, usuario_id, banco_id, resto, descricao + ' (falencia)')
    db.execute('UPDATE usuarios SET saldo = 0, falido = 1 WHERE id = ?', (usuario_id,))
    return -resto


def cartas_do_jogador(db, usuario_id, limite=15):
    return db.execute('''
        SELECT ct.id, ct.data_hora, ct.aplicada, ct.valor_aplicado,
               c.classe, c.numero, c.titulo, c.texto, c.valor, c.percentual
        FROM cartas_tiradas ct
        JOIN cartas c ON ct.carta_id = c.id
        WHERE ct.usuario_id = ?
        ORDER BY ct.id DESC
        LIMIT ?
    ''', (usuario_id, limite)).fetchall()


def listar_cartas_tiradas(db, limite=20):
    return db.execute('''
        SELECT ct.id, ct.data_hora, ct.aplicada, ct.valor_aplicado, ct.usuario_id,
               u.nome AS jogador,
               c.classe, c.numero, c.titulo, c.texto, c.valor, c.percentual
        FROM cartas_tiradas ct
        JOIN cartas c ON ct.carta_id = c.id
        JOIN usuarios u ON ct.usuario_id = u.id
        ORDER BY ct.id DESC
        LIMIT ?
    ''', (limite,)).fetchall()


def garantir_colunas_protecao(db):
    """Migra bancos antigos para o inventario de cartas de protecao e marca as cartas guardaveis."""
    colunas_cartas = [c['name'] for c in db.execute('PRAGMA table_info(cartas)')]
    if 'guardavel' not in colunas_cartas:
        db.execute('ALTER TABLE cartas ADD COLUMN guardavel INTEGER DEFAULT 0')

    colunas_tiradas = [c['name'] for c in db.execute('PRAGMA table_info(cartas_tiradas)')]
    if 'protecao_usada' not in colunas_tiradas:
        db.execute('ALTER TABLE cartas_tiradas ADD COLUMN protecao_usada INTEGER DEFAULT 0')
    if 'protecao_usada_em' not in colunas_tiradas:
        db.execute('ALTER TABLE cartas_tiradas ADD COLUMN protecao_usada_em TIMESTAMP')

    # Marca as cartas guardaveis (idempotente): Sindicato e Influencia Politica.
    db.execute('''
        UPDATE cartas SET guardavel = 1
        WHERE (classe = 'proletariado' AND numero = 5)
           OR (classe = 'rara' AND numero = 2)
    ''')
    db.commit()


def protecoes_do_jogador(db, usuario_id):
    """Cartas de protecao que o jogador possui e ainda nao usou."""
    return db.execute('''
        SELECT ct.id, c.classe, c.titulo, c.texto
        FROM cartas_tiradas ct
        JOIN cartas c ON ct.carta_id = c.id
        WHERE ct.usuario_id = ? AND c.guardavel = 1 AND ct.protecao_usada = 0
        ORDER BY ct.id
    ''', (usuario_id,)).fetchall()


def jogadores_com_protecao(db):
    """Lista jogadores que tem protecoes guardadas (para o painel do banco)."""
    return db.execute('''
        SELECT u.nome, COUNT(*) AS qtd
        FROM cartas_tiradas ct
        JOIN cartas c ON ct.carta_id = c.id
        JOIN usuarios u ON ct.usuario_id = u.id
        WHERE c.guardavel = 1 AND ct.protecao_usada = 0
        GROUP BY u.id
        ORDER BY u.nome
    ''').fetchall()


def protecoes_usadas_recentes(db, limite=10):
    """Protecoes usadas recentemente (aviso para o banco)."""
    return db.execute('''
        SELECT u.nome, c.titulo, ct.protecao_usada_em
        FROM cartas_tiradas ct
        JOIN cartas c ON ct.carta_id = c.id
        JOIN usuarios u ON ct.usuario_id = u.id
        WHERE ct.protecao_usada = 1
        ORDER BY ct.protecao_usada_em DESC, ct.id DESC
        LIMIT ?
    ''', (limite,)).fetchall()


# ============== DECORADORES ==============

def requer_usuario(f):
    """Protege rotas que exigem jogador ativo."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_id' not in session:
            flash('Entre com seu nome primeiro', 'erro')
            return redirect(url_for('entrada'))
        return f(*args, **kwargs)
    return decorated_function


def requer_admin(f):
    """Protege rotas de administracao do banco."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logado'):
            flash('Entre com o PIN do banco para administrar a partida', 'erro')
            return redirect(url_for('admin_entrar'))
        return f(*args, **kwargs)
    return decorated_function


# ============== ROTAS DE JOGADOR ==============

@app.route('/')
def index():
    """Redireciona para dashboard se jogador logado, senao para entrada."""
    if 'usuario_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('entrada'))


@app.route('/entrada', methods=['GET', 'POST'])
def entrada():
    """Tela inicial - inserir nome estilo Kahoot."""
    if request.method == 'POST':
        nome = normalizar_nome(request.form.get('nome', ''))

        if not nome:
            flash('Digite seu nome!', 'erro')
            return redirect(url_for('entrada'))

        if len(nome) < 2:
            flash('Nome deve ter pelo menos 2 caracteres', 'erro')
            return redirect(url_for('entrada'))

        if nome.upper() == BANCO_NOME:
            flash('Esse nome e reservado para o banco da partida', 'erro')
            return redirect(url_for('entrada'))

        db = get_db()
        garantir_usuario_banco(db)

        usuario = db.execute(
            'SELECT id, nome FROM usuarios WHERE nome = ? COLLATE NOCASE', (nome,)
        ).fetchone()

        if usuario:
            session['usuario_id'] = usuario['id']
            session['usuario_nome'] = usuario['nome']
            flash(f'Bem-vindo de volta, {usuario["nome"]}!', 'sucesso')
            db.close()
            return redirect(url_for('dashboard'))

        inserir_usuario(db, nome, 0)
        db.commit()
        novo_usuario = db.execute(
            'SELECT id FROM usuarios WHERE nome = ? COLLATE NOCASE', (nome,)
        ).fetchone()

        session['usuario_id'] = novo_usuario['id']
        session['usuario_nome'] = nome
        flash(f'Bem-vindo ao jogo, {nome}!', 'sucesso')
        db.close()
        return redirect(url_for('dashboard'))

    return render_template('entrada.html')


@app.route('/sair')
def sair():
    """Remove a sessao do jogador."""
    nome = session.get('usuario_nome', 'Jogador')
    session.pop('usuario_id', None)
    session.pop('usuario_nome', None)
    flash(f'Ate logo, {nome}!', 'info')
    return redirect(url_for('entrada'))


@app.route('/dashboard')
@requer_usuario
def dashboard():
    """Dashboard com saldo, historico e opcoes."""
    db = get_db()

    usuario = obter_jogador(db, session['usuario_id'])
    if not usuario:
        session.pop('usuario_id', None)
        session.pop('usuario_nome', None)
        db.close()
        flash('Jogador nao encontrado. Entre novamente.', 'erro')
        return redirect(url_for('entrada'))

    transacoes = db.execute('''
        SELECT
            t.id, t.valor, t.data_hora, t.descricao,
            u1.nome as origem,
            u2.nome as destino
        FROM transacoes t
        JOIN usuarios u1 ON t.usuario_origem_id = u1.id
        JOIN usuarios u2 ON t.usuario_destino_id = u2.id
        WHERE t.usuario_origem_id = ? OR t.usuario_destino_id = ?
        ORDER BY t.data_hora DESC
        LIMIT 20
    ''', (session['usuario_id'], session['usuario_id'])).fetchall()

    minhas_propriedades = []
    for p in propriedades_do_jogador(db, session['usuario_id']):
        item = dict(p)
        item['aluguel_atual'] = calcular_aluguel_atual(db, p)
        item['nivel_texto'] = rotulo_nivel(p)
        minhas_propriedades.append(item)

    minhas_cartas = cartas_do_jogador(db, session['usuario_id'])
    minhas_protecoes = protecoes_do_jogador(db, session['usuario_id'])
    db.close()

    return render_template(
        'dashboard.html',
        usuario=usuario,
        transacoes=transacoes,
        banco_nome=BANCO_NOME,
        minhas_propriedades=minhas_propriedades,
        minhas_cartas=minhas_cartas,
        minhas_protecoes=minhas_protecoes,
        rotulo_classe=ROTULO_CLASSE
    )


@app.route('/transferir', methods=['GET', 'POST'])
@requer_usuario
def transferir():
    """Pagina para transferencias entre jogadores."""
    if request.method == 'POST':
        usuario_destino_nome = request.form.get('usuario_destino', '').strip()
        descricao = formatar_descricao(request.form.get('descricao', ''))

        try:
            valor = float(request.form.get('valor', '0'))
            if valor <= 0:
                raise ValueError
        except ValueError:
            flash('Valor invalido - deve ser maior que zero', 'erro')
            return redirect(url_for('transferir'))

        if not usuario_destino_nome:
            flash('Selecione um jogador de destino', 'erro')
            return redirect(url_for('transferir'))

        db = get_db()

        usuario_origem = obter_jogador(db, session['usuario_id'])
        usuario_destino = db.execute(
            'SELECT id FROM usuarios WHERE nome = ? AND nome != ?',
            (usuario_destino_nome, BANCO_NOME)
        ).fetchone()

        if not usuario_origem:
            session.pop('usuario_id', None)
            session.pop('usuario_nome', None)
            db.close()
            flash('Jogador nao encontrado. Entre novamente.', 'erro')
            return redirect(url_for('entrada'))

        if not usuario_destino:
            flash('Jogador de destino nao encontrado', 'erro')
            db.close()
            return redirect(url_for('transferir'))

        if usuario_origem['id'] == usuario_destino['id']:
            flash('Voce nao pode transferir para si mesmo', 'erro')
            db.close()
            return redirect(url_for('transferir'))

        if usuario_origem['saldo'] < valor:
            flash('Saldo insuficiente', 'erro')
            db.close()
            return redirect(url_for('transferir'))

        try:
            cursor = db.cursor()
            cursor.execute(
                'UPDATE usuarios SET saldo = saldo - ? WHERE id = ?',
                (valor, session['usuario_id'])
            )
            cursor.execute(
                'UPDATE usuarios SET saldo = saldo + ? WHERE id = ?',
                (valor, usuario_destino['id'])
            )
            registrar_movimento(
                db,
                session['usuario_id'],
                usuario_destino['id'],
                valor,
                descricao
            )
            db.commit()
            flash(f'Transferencia de R$ {valor:.2f} realizada com sucesso!', 'sucesso')
        except Exception as e:
            db.rollback()
            flash(f'Erro na transferencia: {str(e)}', 'erro')
        finally:
            db.close()

        return redirect(url_for('dashboard'))

    db = get_db()
    usuarios = db.execute(
        'SELECT id, nome FROM usuarios WHERE id != ? AND nome != ? ORDER BY nome',
        (session['usuario_id'], BANCO_NOME)
    ).fetchall()
    db.close()

    return render_template('transferir.html', usuarios=usuarios)


@app.route('/cartas/<int:tirada_id>/usar', methods=['POST'])
@requer_usuario
def usar_protecao(tirada_id):
    """O jogador usa uma carta de protecao que possui (token: registra e avisa o banco)."""
    db = get_db()
    row = db.execute('''
        SELECT ct.id, ct.usuario_id, ct.protecao_usada, c.guardavel, c.titulo
        FROM cartas_tiradas ct
        JOIN cartas c ON ct.carta_id = c.id
        WHERE ct.id = ?
    ''', (tirada_id,)).fetchone()

    if not row or row['usuario_id'] != session['usuario_id']:
        db.close()
        flash('Carta nao encontrada', 'erro')
        return redirect(url_for('dashboard'))

    if not row['guardavel']:
        db.close()
        flash('Essa carta nao e uma protecao', 'erro')
        return redirect(url_for('dashboard'))

    if row['protecao_usada']:
        db.close()
        flash('Voce ja usou essa protecao', 'info')
        return redirect(url_for('dashboard'))

    db.execute(
        'UPDATE cartas_tiradas SET protecao_usada = 1, protecao_usada_em = CURRENT_TIMESTAMP WHERE id = ?',
        (tirada_id,)
    )
    db.commit()
    db.close()
    flash(f'Voce usou sua carta de protecao ({row["titulo"]})! Avise o Comite Central.', 'sucesso')
    return redirect(url_for('dashboard'))


# ============== ROTAS DE ADMINISTRACAO ==============

@app.route('/admin/entrar', methods=['GET', 'POST'])
def admin_entrar():
    """Entrada do administrador/banco da partida."""
    if request.method == 'POST':
        pin = request.form.get('pin', '')
        if pin == app.config['ADMIN_PIN']:
            session['admin_logado'] = True
            flash('Banco da partida conectado', 'sucesso')
            return redirect(url_for('admin_dashboard'))
        flash('PIN do banco incorreto', 'erro')
        return redirect(url_for('admin_entrar'))

    return render_template('admin_entrar.html')


@app.route('/admin/sair')
def admin_sair():
    """Remove a sessao administrativa."""
    session.pop('admin_logado', None)
    flash('Banco desconectado', 'info')
    return redirect(url_for('entrada'))


@app.route('/admin')
@requer_admin
def admin_dashboard():
    """Painel administrativo da partida."""
    db = get_db()
    garantir_usuario_banco(db)
    valor_passou_inicio = obter_config_float(
        db,
        'valor_passou_inicio',
        VALOR_PASSOU_INICIO_PADRAO
    )

    jogadores = listar_jogadores(db)
    total_saldo = sum(j['saldo'] for j in jogadores)
    total_falidos = sum(1 for j in jogadores if j['falido'])
    total_ativos = len(jogadores) - total_falidos
    transacoes = db.execute('''
        SELECT
            t.id, t.valor, t.data_hora, t.descricao,
            u1.nome as origem,
            u2.nome as destino
        FROM transacoes t
        JOIN usuarios u1 ON t.usuario_origem_id = u1.id
        JOIN usuarios u2 ON t.usuario_destino_id = u2.id
        ORDER BY t.data_hora DESC
        LIMIT 50
    ''').fetchall()

    propriedades = []
    for p in listar_propriedades(db):
        item = dict(p)
        item['aluguel_atual'] = calcular_aluguel_atual(db, p)
        item['nivel_texto'] = rotulo_nivel(p)
        item['liquidacao'] = valor_liquidacao(p)
        propriedades.append(item)

    cartas_recentes = listar_cartas_tiradas(db)
    protecoes_posse = jogadores_com_protecao(db)
    protecoes_usadas = protecoes_usadas_recentes(db)
    db.close()

    return render_template(
        'admin.html',
        jogadores=jogadores,
        transacoes=transacoes,
        total_saldo=total_saldo,
        total_ativos=total_ativos,
        total_falidos=total_falidos,
        banco_nome=BANCO_NOME,
        valor_passou_inicio=valor_passou_inicio,
        propriedades=propriedades,
        cartas_recentes=cartas_recentes,
        protecoes_posse=protecoes_posse,
        protecoes_usadas=protecoes_usadas,
        rotulo_classe=ROTULO_CLASSE
    )


@app.route('/admin/config/passou-inicio', methods=['POST'])
@requer_admin
def admin_config_passou_inicio():
    """Atualiza o valor pago quando um jogador passa pelo inicio."""
    try:
        valor = float(request.form.get('valor_passou_inicio', '0') or 0)
        if valor < 0:
            raise ValueError
    except ValueError:
        flash('Valor ao passar pelo inicio invalido', 'erro')
        return redirect(url_for('admin_dashboard'))

    db = get_db()
    salvar_config(db, 'valor_passou_inicio', valor)
    db.commit()
    db.close()

    flash(f'Valor ao passar pelo inicio definido para R$ {valor:.2f}', 'sucesso')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/jogadores/novo', methods=['POST'])
@requer_admin
def admin_criar_jogador():
    """Cria jogador pelo painel do banco, opcionalmente com saldo inicial."""
    nome = normalizar_nome(request.form.get('nome', ''))

    try:
        saldo_inicial = float(request.form.get('saldo_inicial', '0') or 0)
        if saldo_inicial < 0:
            raise ValueError
    except ValueError:
        flash('Saldo inicial invalido', 'erro')
        return redirect(url_for('admin_dashboard'))

    if len(nome) < 2:
        flash('Nome deve ter pelo menos 2 caracteres', 'erro')
        return redirect(url_for('admin_dashboard'))

    if nome.upper() == BANCO_NOME:
        flash('Esse nome e reservado para o banco da partida', 'erro')
        return redirect(url_for('admin_dashboard'))

    db = get_db()
    existente = db.execute(
        'SELECT 1 FROM usuarios WHERE nome = ? COLLATE NOCASE', (nome,)
    ).fetchone()
    if existente:
        db.close()
        flash('Ja existe um jogador com esse nome', 'erro')
        return redirect(url_for('admin_dashboard'))

    try:
        banco_id = obter_banco_id(db)
        jogador_id = inserir_usuario(db, nome, saldo_inicial)

        if saldo_inicial > 0:
            registrar_movimento(
                db,
                banco_id,
                jogador_id,
                saldo_inicial,
                'Saldo inicial'
            )

        db.commit()
        flash(f'Jogador {nome} criado com sucesso', 'sucesso')
    except sqlite3.IntegrityError:
        db.rollback()
        flash('Ja existe um jogador com esse nome', 'erro')
    finally:
        db.close()

    return redirect(url_for('admin_dashboard'))


@app.route('/admin/jogadores/<int:usuario_id>/passou-inicio', methods=['POST'])
@requer_admin
def admin_passou_inicio(usuario_id):
    """Credita o valor configurado quando um jogador passa pelo inicio."""
    db = get_db()
    jogador = obter_jogador(db, usuario_id)

    if not jogador:
        db.close()
        flash('Jogador nao encontrado', 'erro')
        return redirect(url_for('admin_dashboard'))

    valor = obter_config_float(db, 'valor_passou_inicio', VALOR_PASSOU_INICIO_PADRAO)
    if valor <= 0:
        db.close()
        flash('Defina um valor maior que zero para passar pelo inicio', 'erro')
        return redirect(url_for('admin_dashboard'))

    try:
        banco_id = obter_banco_id(db)
        db.execute('UPDATE usuarios SET saldo = saldo + ? WHERE id = ?', (valor, usuario_id))
        registrar_movimento(db, banco_id, usuario_id, valor, 'Passou pelo inicio')
        db.commit()
        flash(f'{jogador["nome"]} recebeu R$ {valor:.2f} por passar pelo inicio', 'sucesso')
    except Exception as e:
        db.rollback()
        flash(f'Erro ao pagar passagem pelo inicio: {str(e)}', 'erro')
    finally:
        db.close()

    return redirect(url_for('admin_dashboard'))


@app.route('/admin/jogadores/<int:usuario_id>/saldo', methods=['POST'])
@requer_admin
def admin_ajustar_saldo(usuario_id):
    """Credita, debita ou define saldo de um jogador."""
    acao = request.form.get('acao')
    descricao = formatar_descricao(request.form.get('descricao', ''))

    try:
        valor = float(request.form.get('valor', '0'))
        if valor < 0:
            raise ValueError
    except ValueError:
        flash('Valor invalido', 'erro')
        return redirect(url_for('admin_dashboard'))

    db = get_db()
    jogador = obter_jogador(db, usuario_id)

    if not jogador:
        db.close()
        flash('Jogador nao encontrado', 'erro')
        return redirect(url_for('admin_dashboard'))

    banco_id = obter_banco_id(db)

    try:
        if acao == 'creditar':
            if valor <= 0:
                raise ValueError('Valor deve ser maior que zero')
            db.execute('UPDATE usuarios SET saldo = saldo + ? WHERE id = ?', (valor, usuario_id))
            registrar_movimento(
                db,
                banco_id,
                usuario_id,
                valor,
                descricao or 'Credito do banco'
            )
            flash(f'R$ {valor:.2f} creditados para {jogador["nome"]}', 'sucesso')

        elif acao == 'debitar':
            if valor <= 0:
                raise ValueError('Valor deve ser maior que zero')
            if jogador['saldo'] < valor:
                flash('Saldo insuficiente para debitar esse valor', 'erro')
                db.close()
                return redirect(url_for('admin_dashboard'))
            db.execute('UPDATE usuarios SET saldo = saldo - ? WHERE id = ?', (valor, usuario_id))
            registrar_movimento(
                db,
                usuario_id,
                banco_id,
                valor,
                descricao or 'Debito do banco'
            )
            flash(f'R$ {valor:.2f} debitados de {jogador["nome"]}', 'sucesso')

        elif acao == 'definir':
            diferenca = valor - jogador['saldo']
            db.execute('UPDATE usuarios SET saldo = ? WHERE id = ?', (valor, usuario_id))

            if diferenca > 0:
                registrar_movimento(
                    db,
                    banco_id,
                    usuario_id,
                    diferenca,
                    descricao or f'Saldo definido para R$ {valor:.2f}'
                )
            elif diferenca < 0:
                registrar_movimento(
                    db,
                    usuario_id,
                    banco_id,
                    abs(diferenca),
                    descricao or f'Saldo definido para R$ {valor:.2f}'
                )

            flash(f'Saldo de {jogador["nome"]} definido para R$ {valor:.2f}', 'sucesso')

        else:
            flash('Acao invalida', 'erro')
            db.close()
            return redirect(url_for('admin_dashboard'))

        db.commit()
    except ValueError as e:
        db.rollback()
        flash(str(e), 'erro')
    except Exception as e:
        db.rollback()
        flash(f'Erro ao ajustar saldo: {str(e)}', 'erro')
    finally:
        db.close()

    return redirect(url_for('admin_dashboard'))


@app.route('/admin/jogadores/<int:usuario_id>/excluir', methods=['POST'])
@requer_admin
def admin_excluir_jogador(usuario_id):
    """Exclui jogador sem historico de transacoes."""
    db = get_db()
    jogador = obter_jogador(db, usuario_id)
    if not jogador:
        db.close()
        flash('Jogador nao encontrado', 'erro')
        return redirect(url_for('admin_dashboard'))

    transacoes = db.execute('''
        SELECT COUNT(*) AS total FROM transacoes
        WHERE usuario_origem_id = ? OR usuario_destino_id = ?
    ''', (usuario_id, usuario_id)).fetchone()['total']

    if transacoes:
        db.close()
        flash('Jogador com historico nao pode ser excluido. Use resetar partida se precisar limpar tudo.', 'erro')
        return redirect(url_for('admin_dashboard'))

    db.execute('DELETE FROM usuarios WHERE id = ?', (usuario_id,))
    db.commit()
    db.close()
    flash(f'Jogador {jogador["nome"]} excluido', 'sucesso')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/resetar', methods=['GET', 'POST'])
@requer_admin
def admin_resetar():
    """Reseta jogadores e historico da partida."""
    if request.method == 'GET':
        flash('Use o botao de reset dentro do painel para confirmar a limpeza da partida', 'info')
        return redirect(url_for('admin_dashboard'))

    confirmar = request.form.get('confirmar', '').strip().upper()
    if confirmar != 'RESETAR':
        flash('Digite RESETAR para confirmar a limpeza da partida', 'erro')
        return redirect(url_for('admin_dashboard'))

    db = get_db()
    db.execute('DELETE FROM transacoes')
    db.execute('DELETE FROM usuarios WHERE nome != ?', (BANCO_NOME,))
    # Devolve todas as propriedades ao banco (evita donos orfaos apos o reset)
    db.execute('''
        UPDATE propriedades
        SET dono_id = NULL, num_casas = 0, tem_hotel = 0, hipotecada = 0
    ''')
    garantir_usuario_banco(db)
    db.commit()
    db.close()

    session.pop('usuario_id', None)
    session.pop('usuario_nome', None)
    flash('Partida resetada com sucesso', 'sucesso')
    return redirect(url_for('admin_dashboard'))


# ============== ROTAS DE PROPRIEDADES (ADMIN) ==============

@app.route('/admin/propriedades/<int:propriedade_id>/comprar', methods=['POST'])
@requer_admin
def admin_comprar_propriedade(propriedade_id):
    """Atribui uma propriedade a um jogador, debitando o preco de compra."""
    db = get_db()
    prop = obter_propriedade(db, propriedade_id)
    if not prop:
        db.close()
        flash('Propriedade nao encontrada', 'erro')
        return redirect(url_for('admin_dashboard'))

    if prop['dono_id']:
        db.close()
        flash(f'{prop["nome"]} ja tem dono. Venda ou libere antes.', 'erro')
        return redirect(url_for('admin_dashboard'))

    jogador = obter_jogador(db, request.form.get('dono_id', type=int))
    if not jogador:
        db.close()
        flash('Selecione um jogador valido para comprar', 'erro')
        return redirect(url_for('admin_dashboard'))

    preco = float(prop['preco_compra'])
    if jogador['saldo'] < preco:
        db.close()
        flash(f'{jogador["nome"]} nao tem saldo para comprar {prop["nome"]}', 'erro')
        return redirect(url_for('admin_dashboard'))

    try:
        banco_id = obter_banco_id(db)
        db.execute('UPDATE usuarios SET saldo = saldo - ? WHERE id = ?', (preco, jogador['id']))
        db.execute('UPDATE propriedades SET dono_id = ? WHERE id = ?', (jogador['id'], propriedade_id))
        registrar_movimento(db, jogador['id'], banco_id, preco, f'Compra de {prop["nome"]}')
        db.commit()
        flash(f'{jogador["nome"]} comprou {prop["nome"]} por R$ {preco:.2f}', 'sucesso')
    except Exception as e:
        db.rollback()
        flash(f'Erro na compra: {str(e)}', 'erro')
    finally:
        db.close()
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/propriedades/<int:propriedade_id>/construir', methods=['POST'])
@requer_admin
def admin_construir(propriedade_id):
    """Constroi uma casa (ou hotel no 5o nivel), debitando o custo do dono."""
    db = get_db()
    prop = obter_propriedade(db, propriedade_id)
    if not prop or not prop['dono_id']:
        db.close()
        flash('Propriedade sem dono nao pode receber construcoes', 'erro')
        return redirect(url_for('admin_dashboard'))

    if prop['hipotecada']:
        db.close()
        flash('Nao e possivel construir em propriedade hipotecada', 'erro')
        return redirect(url_for('admin_dashboard'))

    if prop['tem_hotel']:
        db.close()
        flash(f'{prop["nome"]} ja tem hotel (nivel maximo)', 'erro')
        return redirect(url_for('admin_dashboard'))

    dono = obter_jogador(db, prop['dono_id'])
    custo = float(prop['custo_casa'])
    if not dono or dono['saldo'] < custo:
        db.close()
        flash('Dono sem saldo para construir', 'erro')
        return redirect(url_for('admin_dashboard'))

    try:
        banco_id = obter_banco_id(db)
        if prop['num_casas'] >= 4:
            # 5a construcao vira hotel (as 4 casas sao convertidas)
            db.execute(
                'UPDATE propriedades SET num_casas = 4, tem_hotel = 1 WHERE id = ?',
                (propriedade_id,)
            )
            texto = f'Hotel construido em {prop["nome"]}'
        else:
            db.execute(
                'UPDATE propriedades SET num_casas = num_casas + 1 WHERE id = ?',
                (propriedade_id,)
            )
            texto = f'Casa construida em {prop["nome"]}'
        db.execute('UPDATE usuarios SET saldo = saldo - ? WHERE id = ?', (custo, dono['id']))
        registrar_movimento(db, dono['id'], banco_id, custo, texto)
        db.commit()
        flash(f'{texto} (-R$ {custo:.2f})', 'sucesso')
    except Exception as e:
        db.rollback()
        flash(f'Erro ao construir: {str(e)}', 'erro')
    finally:
        db.close()
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/propriedades/<int:propriedade_id>/vender-casa', methods=['POST'])
@requer_admin
def admin_vender_casa(propriedade_id):
    """Vende uma construcao de volta ao banco pelo custo_casa (hotel -> 4 casas)."""
    db = get_db()
    prop = obter_propriedade(db, propriedade_id)
    if not prop or not prop['dono_id']:
        db.close()
        flash('Propriedade sem dono', 'erro')
        return redirect(url_for('admin_dashboard'))

    if not prop['tem_hotel'] and prop['num_casas'] == 0:
        db.close()
        flash(f'{prop["nome"]} nao tem construcoes para vender', 'erro')
        return redirect(url_for('admin_dashboard'))

    custo = float(prop['custo_casa'])
    try:
        banco_id = obter_banco_id(db)
        if prop['tem_hotel']:
            db.execute(
                'UPDATE propriedades SET tem_hotel = 0, num_casas = 4 WHERE id = ?',
                (propriedade_id,)
            )
            texto = f'Hotel vendido em {prop["nome"]}'
        else:
            db.execute(
                'UPDATE propriedades SET num_casas = num_casas - 1 WHERE id = ?',
                (propriedade_id,)
            )
            texto = f'Casa vendida em {prop["nome"]}'
        db.execute('UPDATE usuarios SET saldo = saldo + ? WHERE id = ?', (custo, prop['dono_id']))
        registrar_movimento(db, banco_id, prop['dono_id'], custo, texto)
        db.commit()
        flash(f'{texto} (+R$ {custo:.2f})', 'sucesso')
    except Exception as e:
        db.rollback()
        flash(f'Erro ao vender construcao: {str(e)}', 'erro')
    finally:
        db.close()
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/propriedades/<int:propriedade_id>/hipotecar', methods=['POST'])
@requer_admin
def admin_hipotecar(propriedade_id):
    """Alterna hipoteca. Ao hipotecar o banco paga; ao quitar o dono devolve (sem juros)."""
    db = get_db()
    prop = obter_propriedade(db, propriedade_id)
    if not prop or not prop['dono_id']:
        db.close()
        flash('Propriedade sem dono nao pode ser hipotecada', 'erro')
        return redirect(url_for('admin_dashboard'))

    dono = obter_jogador(db, prop['dono_id'])
    valor = float(prop['valor_hipoteca'])
    try:
        banco_id = obter_banco_id(db)
        if prop['hipotecada']:
            # Quitar: dono paga o valor de volta, sem juros
            if not dono or dono['saldo'] < valor:
                db.close()
                flash('Dono sem saldo para quitar a hipoteca', 'erro')
                return redirect(url_for('admin_dashboard'))
            db.execute('UPDATE usuarios SET saldo = saldo - ? WHERE id = ?', (valor, dono['id']))
            db.execute('UPDATE propriedades SET hipotecada = 0 WHERE id = ?', (propriedade_id,))
            registrar_movimento(db, dono['id'], banco_id, valor, f'Quitacao de hipoteca de {prop["nome"]}')
            flash(f'Hipoteca de {prop["nome"]} quitada (-R$ {valor:.2f})', 'sucesso')
        else:
            if prop['num_casas'] > 0 or prop['tem_hotel']:
                db.close()
                flash('Venda as construcoes antes de hipotecar', 'erro')
                return redirect(url_for('admin_dashboard'))
            db.execute('UPDATE usuarios SET saldo = saldo + ? WHERE id = ?', (valor, dono['id']))
            db.execute('UPDATE propriedades SET hipotecada = 1 WHERE id = ?', (propriedade_id,))
            registrar_movimento(db, banco_id, dono['id'], valor, f'Hipoteca de {prop["nome"]}')
            flash(f'{prop["nome"]} hipotecada (+R$ {valor:.2f})', 'sucesso')
        db.commit()
    except Exception as e:
        db.rollback()
        flash(f'Erro na hipoteca: {str(e)}', 'erro')
    finally:
        db.close()
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/propriedades/<int:propriedade_id>/liberar', methods=['POST'])
@requer_admin
def admin_liberar_propriedade(propriedade_id):
    """Devolve a propriedade ao banco sem pagamento (correcao manual)."""
    db = get_db()
    prop = obter_propriedade(db, propriedade_id)
    if not prop:
        db.close()
        flash('Propriedade nao encontrada', 'erro')
        return redirect(url_for('admin_dashboard'))
    db.execute('''
        UPDATE propriedades
        SET dono_id = NULL, num_casas = 0, tem_hotel = 0, hipotecada = 0
        WHERE id = ?
    ''', (propriedade_id,))
    db.commit()
    db.close()
    flash(f'{prop["nome"]} devolvida ao banco', 'info')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/propriedades/<int:propriedade_id>/cobrar', methods=['POST'])
@requer_admin
def admin_cobrar_aluguel(propriedade_id):
    """Cobra o aluguel de um jogador que caiu na propriedade.

    Se o inquilino nao tiver saldo, vende as propriedades dele ao banco para
    cobrir a divida. Se ainda faltar, paga o possivel e decreta falencia.
    """
    db = get_db()
    prop = obter_propriedade(db, propriedade_id)
    if not prop or not prop['dono_id']:
        db.close()
        flash('Propriedade sem dono nao gera aluguel', 'erro')
        return redirect(url_for('admin_dashboard'))

    if prop['hipotecada']:
        db.close()
        flash(f'{prop["nome"]} esta hipotecada: nao cobra aluguel', 'erro')
        return redirect(url_for('admin_dashboard'))

    inquilino = obter_jogador(db, request.form.get('inquilino_id', type=int))
    if not inquilino:
        db.close()
        flash('Selecione um jogador valido que caiu na propriedade', 'erro')
        return redirect(url_for('admin_dashboard'))

    if inquilino['id'] == prop['dono_id']:
        db.close()
        flash('O dono nao paga aluguel a si mesmo', 'erro')
        return redirect(url_for('admin_dashboard'))

    aluguel = calcular_aluguel_atual(db, prop)
    if aluguel <= 0:
        db.close()
        flash('Aluguel dessa propriedade e zero', 'info')
        return redirect(url_for('admin_dashboard'))

    dono_id = prop['dono_id']
    dono_nome = db.execute('SELECT nome FROM usuarios WHERE id = ?', (dono_id,)).fetchone()['nome']
    descricao = f'Aluguel de {prop["nome"]}'

    try:
        banco_id = obter_banco_id(db)
        saldo = inquilino['saldo']

        if saldo < aluguel:
            # Precisa liquidar bens para tentar pagar
            arrecadado = liquidar_todas_propriedades(db, inquilino['id'], banco_id, 'Falencia')
            saldo += arrecadado
            flash(f'{inquilino["nome"]} vendeu bens por R$ {arrecadado:.2f} para pagar', 'info')

        if saldo >= aluguel:
            db.execute('UPDATE usuarios SET saldo = saldo - ? WHERE id = ?', (aluguel, inquilino['id']))
            db.execute('UPDATE usuarios SET saldo = saldo + ? WHERE id = ?', (aluguel, dono_id))
            registrar_movimento(db, inquilino['id'], dono_id, aluguel, descricao)
            db.commit()
            flash(f'{inquilino["nome"]} pagou R$ {aluguel:.2f} de aluguel a {dono_nome}', 'sucesso')
        else:
            # Falencia: paga o que resta e o jogador sai
            resto = max(saldo, 0.0)
            if resto > 0:
                db.execute('UPDATE usuarios SET saldo = 0 WHERE id = ?', (inquilino['id'],))
                db.execute('UPDATE usuarios SET saldo = saldo + ? WHERE id = ?', (resto, dono_id))
                registrar_movimento(db, inquilino['id'], dono_id, resto, f'{descricao} (falencia)')
            db.execute('UPDATE usuarios SET saldo = 0, falido = 1 WHERE id = ?', (inquilino['id'],))
            db.commit()
            flash(
                f'{inquilino["nome"]} nao conseguiu pagar R$ {aluguel:.2f}. '
                f'Pagou R$ {resto:.2f} a {dono_nome} e FALIU.',
                'erro'
            )
    except Exception as e:
        db.rollback()
        flash(f'Erro ao cobrar aluguel: {str(e)}', 'erro')
    finally:
        db.close()
    return redirect(url_for('admin_dashboard'))


# ============== ROTAS DE CARTAS (ADMIN) ==============

@app.route('/admin/cartas/tirar', methods=['POST'])
@requer_admin
def admin_tirar_carta():
    """Sorteia uma carta do baralho escolhido para o jogador selecionado."""
    classe = request.form.get('classe', '')
    if classe not in CLASSES_VALIDAS:
        flash('Baralho invalido', 'erro')
        return redirect(url_for('admin_dashboard'))

    db = get_db()
    jogador = obter_jogador(db, request.form.get('usuario_id', type=int))
    if not jogador:
        db.close()
        flash('Selecione um camarada valido', 'erro')
        return redirect(url_for('admin_dashboard'))

    carta = tirar_carta(db, classe)
    if not carta:
        db.close()
        flash('Nenhuma carta nesse baralho', 'erro')
        return redirect(url_for('admin_dashboard'))

    db.execute(
        'INSERT INTO cartas_tiradas (carta_id, usuario_id) VALUES (?, ?)',
        (carta['id'], jogador['id'])
    )
    db.commit()
    db.close()

    flash(f'{jogador["nome"]} tirou [{ROTULO_CLASSE[classe]}] {carta["titulo"]}: {carta["texto"]}', 'info')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/cartas/<int:tirada_id>/aplicar', methods=['POST'])
@requer_admin
def admin_aplicar_carta(tirada_id):
    """Aplica ao caixa a parte de dinheiro da carta tirada (1 clique do admin)."""
    db = get_db()
    tirada = db.execute('SELECT * FROM cartas_tiradas WHERE id = ?', (tirada_id,)).fetchone()
    if not tirada:
        db.close()
        flash('Sorteio nao encontrado', 'erro')
        return redirect(url_for('admin_dashboard'))

    if tirada['aplicada']:
        db.close()
        flash('Essa carta ja foi aplicada', 'info')
        return redirect(url_for('admin_dashboard'))

    carta = db.execute('SELECT * FROM cartas WHERE id = ?', (tirada['carta_id'],)).fetchone()
    if not carta_tem_dinheiro(carta):
        db.close()
        flash('Essa carta nao tem efeito de dinheiro (efeito manual no tabuleiro)', 'info')
        return redirect(url_for('admin_dashboard'))

    jogador = obter_jogador(db, tirada['usuario_id'])
    if not jogador:
        db.close()
        flash('Jogador da carta nao encontrado', 'erro')
        return redirect(url_for('admin_dashboard'))

    try:
        banco_id = obter_banco_id(db)
        efetivo = aplicar_valor_carta(db, tirada['usuario_id'], carta, banco_id)
        db.execute(
            'UPDATE cartas_tiradas SET aplicada = 1, valor_aplicado = ? WHERE id = ?',
            (efetivo, tirada_id)
        )
        db.commit()
        if efetivo >= 0:
            flash(f'{jogador["nome"]} recebeu R$ {efetivo:.2f} pela carta "{carta["titulo"]}"', 'sucesso')
        else:
            flash(f'{jogador["nome"]} pagou R$ {abs(efetivo):.2f} pela carta "{carta["titulo"]}"', 'sucesso')
    except Exception as e:
        db.rollback()
        flash(f'Erro ao aplicar carta: {str(e)}', 'erro')
    finally:
        db.close()

    return redirect(url_for('admin_dashboard'))


# ============== ROTAS DE API (JSON) ==============

@app.route('/api/usuarios')
@requer_usuario
def api_usuarios():
    """Retorna lista de jogadores."""
    db = get_db()
    usuarios = db.execute(
        'SELECT nome FROM usuarios WHERE id != ? AND nome != ? ORDER BY nome',
        (session['usuario_id'], BANCO_NOME)
    ).fetchall()
    db.close()

    return jsonify([u['nome'] for u in usuarios])


@app.route('/api/saldo')
@requer_usuario
def api_saldo():
    """Retorna saldo do jogador logado."""
    db = get_db()
    usuario = obter_jogador(db, session['usuario_id'])
    db.close()

    return jsonify({'saldo': usuario['saldo'] if usuario else 0})


@app.route('/api/minhas-cartas')
@requer_usuario
def api_minhas_cartas():
    """Retorna as cartas do jogador logado (para atualizacao sem recarregar)."""
    db = get_db()
    cartas = cartas_do_jogador(db, session['usuario_id'])
    protecoes = protecoes_do_jogador(db, session['usuario_id'])
    db.close()

    return jsonify({
        'cartas': [
            {
                'id': c['id'],
                'classe': c['classe'],
                'classe_rotulo': ROTULO_CLASSE.get(c['classe'], c['classe']),
                'titulo': c['titulo'],
                'texto': c['texto'],
                'aplicada': bool(c['aplicada']),
                'valor_aplicado': c['valor_aplicado'],
            }
            for c in cartas
        ],
        'protecoes': [
            {
                'id': p['id'],
                'classe': p['classe'],
                'classe_rotulo': ROTULO_CLASSE.get(p['classe'], p['classe']),
                'titulo': p['titulo'],
                'texto': p['texto'],
            }
            for p in protecoes
        ],
    })


@app.route('/api/admin/resumo')
@requer_admin
def api_admin_resumo():
    """Retorna resumo da partida para o painel administrativo."""
    db = get_db()
    jogadores = listar_jogadores(db)
    valor_passou_inicio = obter_config_float(
        db,
        'valor_passou_inicio',
        VALOR_PASSOU_INICIO_PADRAO
    )
    total_transacoes = db.execute('SELECT COUNT(*) AS total FROM transacoes').fetchone()['total']
    db.close()

    return jsonify({
        'jogadores': len(jogadores),
        'saldo_total': sum(j['saldo'] for j in jogadores),
        'transacoes': total_transacoes,
        'valor_passou_inicio': valor_passou_inicio,
    })


# ============== TRATAMENTO DE ERROS ==============

@app.errorhandler(404)
def not_found(error):
    """Pagina nao encontrada."""
    return render_template('404.html'), 404


@app.errorhandler(500)
def server_error(error):
    """Erro interno do servidor."""
    return render_template('500.html'), 500


# ============== MAIN ==============

if __name__ == '__main__':
    init_db()

    print("Servidor iniciando em http://localhost:5000")
    print("PIN admin padrao: 1234 (altere com a variavel ADMIN_PIN)")
    app.run(debug=True, host='0.0.0.0', port=5000)
