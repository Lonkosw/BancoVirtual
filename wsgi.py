"""
Entrada WSGI para producao (PythonAnywhere, Gunicorn, etc.).

No PythonAnywhere, aponte o "WSGI configuration file" para importar `application`
deste modulo. Ex.:

    import sys
    path = '/home/SEU_USUARIO/O-Capital'
    if path not in sys.path:
        sys.path.insert(0, path)
    from wsgi import application

Variaveis de ambiente recomendadas em producao:
    SECRET_KEY   - chave secreta de sessao (obrigatorio trocar)
    ADMIN_PIN    - PIN do Comite Central (obrigatorio trocar)
    DATABASE     - caminho absoluto do banco (opcional; padrao ao lado do app.py)
"""

from app import app as application, init_db

# Garante que o schema exista e os seeds rodem no primeiro boot do worker.
init_db()

if __name__ == '__main__':
    application.run()
