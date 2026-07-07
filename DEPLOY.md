# Deploy — "O Capital" no PythonAnywhere

URL fixa e estável (passa no WiFi da UTFPR, sem túnel Cloudflare).

## 1. Suba o código

Opção A — via GitHub (recomendado):
```bash
git clone https://github.com/Lonkosw/BancoVirtual.git O-Capital
```
Opção B — envie os arquivos pelo painel "Files" do PythonAnywhere.

## 2. Crie o Web app

1. Aba **Web** → **Add a new web app** → **Manual configuration** → **Python 3.10** (ou superior).
2. Em **Virtualenv** (opcional) instale o Flask:
   ```bash
   pip install --user flask
   ```
   (o projeto usa só Flask + a stdlib; `requirements.txt` cobre isso.)

## 3. Aponte o WSGI (e defina os segredos aqui)

Edite o **WSGI configuration file** (link na aba Web), **apague tudo** e deixe só isto
(troque `SEU_USUARIO`, o PIN e a chave secreta):

```python
import sys, os

path = '/home/SEU_USUARIO/O-Capital'      # ajuste o caminho
if path not in sys.path:
    sys.path.insert(0, path)

# No plano grátis não há aba de "Environment variables": defina os segredos aqui.
os.environ['SECRET_KEY'] = 'troque-por-uma-frase-longa-e-aleatoria'
os.environ['ADMIN_PIN']  = '4732'         # seu PIN secreto do Comitê Central
# os.environ['DATABASE'] = '/home/SEU_USUARIO/O-Capital/banco.db'  # opcional (já é o padrão)

from wsgi import application               # importa o app e roda init_db()
```

O `banco.db` é criado automaticamente no primeiro acesso (`init_db()` roda no `wsgi.py`).
O disco do PythonAnywhere é persistente, então o SQLite sobrevive a reinícios.

> Em contas pagas você pode, em vez disso, exportar essas variáveis no ambiente e omitir
> as linhas `os.environ[...]` acima.

## 5. Reload

Clique em **Reload** na aba Web. Acesse `https://SEU_USUARIO.pythonanywhere.com`.

- Jogadores entram por nome na home.
- Comitê Central: `/admin/entrar` com o `ADMIN_PIN`.

## Observações

- **Não** suba `banco.db` para produção (está no `.gitignore`) — deixe o servidor criar o dele.
- Ao mudar as constantes `SEED_*_VERSAO` no `app.py`, o próximo boot **re-semeia** cartas/
  propriedades/quiz automaticamente (mantém o schema, recarrega o conteúdo).
- Para limpar a partida sem mexer no seed, use **Resetar partida** no painel admin.
