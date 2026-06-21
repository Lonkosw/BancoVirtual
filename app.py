"""
Banco Imobiliario Online - Backend Flask
Sistema para administracao de caixa e transferencias entre jogadores.
"""

from datetime import datetime
from functools import wraps
import os
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

        db.commit()
        garantir_usuario_banco(db)
        garantir_configuracoes(db)
        db.close()
        print("Banco de dados inicializado")


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
        'SELECT id, nome, saldo, criado_em FROM usuarios WHERE id = ? AND nome != ?',
        (usuario_id, BANCO_NOME)
    ).fetchone()


def listar_jogadores(db):
    return db.execute(
        'SELECT id, nome, saldo, criado_em FROM usuarios WHERE nome != ? ORDER BY nome',
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
        nome = request.form.get('nome', '').strip()

        if not nome:
            flash('Digite seu nome!', 'erro')
            return redirect(url_for('entrada'))

        if len(nome) < 2:
            flash('Nome deve ter pelo menos 2 caracteres', 'erro')
            return redirect(url_for('entrada'))

        if nome == BANCO_NOME:
            flash('Esse nome e reservado para o banco da partida', 'erro')
            return redirect(url_for('entrada'))

        db = get_db()
        garantir_usuario_banco(db)

        usuario = db.execute(
            'SELECT id FROM usuarios WHERE nome = ?', (nome,)
        ).fetchone()

        if usuario:
            session['usuario_id'] = usuario['id']
            session['usuario_nome'] = nome
            flash(f'Bem-vindo de volta, {nome}!', 'sucesso')
            db.close()
            return redirect(url_for('dashboard'))

        inserir_usuario(db, nome, 0)
        db.commit()
        novo_usuario = db.execute(
            'SELECT id FROM usuarios WHERE nome = ?', (nome,)
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

    db.close()

    return render_template(
        'dashboard.html',
        usuario=usuario,
        transacoes=transacoes,
        banco_nome=BANCO_NOME
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
    db.close()

    return render_template(
        'admin.html',
        jogadores=jogadores,
        transacoes=transacoes,
        total_saldo=total_saldo,
        banco_nome=BANCO_NOME,
        valor_passou_inicio=valor_passou_inicio
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
    nome = request.form.get('nome', '').strip()

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

    if nome == BANCO_NOME:
        flash('Esse nome e reservado para o banco da partida', 'erro')
        return redirect(url_for('admin_dashboard'))

    db = get_db()
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
    garantir_usuario_banco(db)
    db.commit()
    db.close()

    session.pop('usuario_id', None)
    session.pop('usuario_nome', None)
    flash('Partida resetada com sucesso', 'sucesso')
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
