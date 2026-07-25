# -*- coding: utf-8 -*-
"""
SISTEMA DE GESTAO DE USUARIOS COM ISOLAMENTO DE DADOS
-------------------------------------------------------
Framework: Flask (Python)
Banco de dados: SQLite
Seguranca: Bcrypt (hash de senhas - senhas nunca sao armazenadas em texto puro)
Reset de senha: via e-mail (SMTP)
"""

import os
import sqlite3
import secrets
from datetime import datetime, timedelta
from flask import Flask, render_template_string, request, redirect, url_for, session, flash
from flask_bcrypt import Bcrypt
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
bcrypt = Bcrypt(app)

# ============================================================
# CONFIGURACOES DE E-MAIL (ALTERE COM SEUS DADOS)
# ============================================================
EMAIL_REMETENTE = "seu_email@gmail.com"
EMAIL_SENHA = "sua_senha_de_app"  # Use uma "Senha de App" do Gmail
SMTP_SERVIDOR = "smtp.gmail.com"
SMTP_PORTA = 587

# ============================================================
# BANCO DE DADOS - INICIALIZACAO
# ============================================================
DB_NAME = "usuarios.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            login TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            senha_hash TEXT NOT NULL,
            data_cadastro TEXT NOT NULL,
            token_reset TEXT,
            token_expira TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ============================================================
# HELPERS DE BANCO DE DADOS
# ============================================================
def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def validar_senha(senha):
    """Valida se a senha atende aos criterios: ate 10 chars, letras e/ou numeros."""
    if len(senha) > 10:
        return False, "A senha deve ter no maximo 10 caracteres."
    if not senha.isalnum():
        return False, "A senha deve conter apenas letras e numeros."
    tem_maiuscula = any(c.isupper() for c in senha)
    tem_minuscula = any(c.islower() for c in senha)
    tem_numero = any(c.isdigit() for c in senha)
    if not (tem_maiuscula or tem_minuscula or tem_numero):
        return False, "A senha deve conter pelo menos letras ou numeros."
    return True, "Senha valida."

def enviar_email(destinatario, assunto, corpo):
    """Envia e-mail via SMTP."""
    msg = MIMEMultipart()
    msg['From'] = EMAIL_REMETENTE
    msg['To'] = destinatario
    msg['Subject'] = assunto
    msg.attach(MIMEText(corpo, 'html'))
    try:
        server = smtplib.SMTP(SMTP_SERVIDOR, SMTP_PORTA)
        server.starttls()
        server.login(EMAIL_REMETENTE, EMAIL_SENHA)
        server.sendmail(EMAIL_REMETENTE, destinatario, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")
        return False

# ============================================================
# TEMPLATES HTML (embutidos para simplicidade)
# ============================================================
TEMPLATE_BASE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ titulo }}</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, sans-serif; background: #f0f2f5; }
        .container { max-width: 500px; margin: 60px auto; background: #fff;
            padding: 40px; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.1); }
        h1 { color: #1a73e8; margin-bottom: 25px; font-size: 1.5em; }
        label { display: block; margin: 12px 0 5px; font-weight: 600; color: #333; }
        input[type="text"], input[type="password"], input[type="email"] {
            width: 100%; padding: 12px; border: 1px solid #ccc; border-radius: 8px; font-size: 1em; }
        input:focus { outline: none; border-color: #1a73e8; }
        button { width: 100%; padding: 14px; background: #1a73e8; color: #fff;
            border: none; border-radius: 8px; font-size: 1em; cursor: pointer; margin-top: 20px; }
        button:hover { background: #1557b0; }
        .flash { padding: 12px; border-radius: 8px; margin-bottom: 15px; }
        .flash-success { background: #d4edda; color: #155724; }
        .flash-danger { background: #f8d7da; color: #721c24; }
        .flash-info { background: #d1ecf1; color: #0c5460; }
        a { color: #1a73e8; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .link { text-align: center; margin-top: 15px; }
        .info { background: #e8f0fe; padding: 10px; border-radius: 8px; margin-top: 15px;
            font-size: 0.85em; color: #333; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #1a73e8; color: #fff; }
        .btn-small { padding: 6px 14px; font-size: 0.85em; }
        .nav { margin-bottom: 20px; }
        .nav a { margin-right: 15px; }
    </style>
</head>
<body>
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="flash flash-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </div>
</body>
</html>
"""

TEMPLATE_CADASTRO = """
{% extends "base" %}
{% block content %}
<h1>Criar Conta</h1>
<form method="POST" action="/cadastro">
    <label>Login (unico):</label>
    <input type="text" name="login" required placeholder="Escolha seu login">
    <label>E-mail:</label>
    <input type="email" name="email" required placeholder="seu@email.com">
    <label>Senha (ate 10 caracteres, letras e/ou numeros):</label>
    <input type="password" name="senha" required maxlength="10" placeholder="********">
    <button type="submit">Cadastrar</button>
</form>
<div class="link">Ja tem conta? <a href="/login">Fazer login</a></div>
<div class="info">Suas credenciais sao isoladas. Nenhum outro usuario tem acesso aos seus dados.</div>
{% endblock %}
"""

TEMPLATE_LOGIN = """
{% extends "base" %}
{% block content %}
<h1>Entrar</h1>
<form method="POST" action="/login">
    <label>Login:</label>
    <input type="text" name="login" required placeholder="Seu login">
    <label>Senha:</label>
    <input type="password" name="senha" required placeholder="********">
    <button type="submit">Entrar</button>
</form>
<div class="link"><a href="/recuperar">Esqueceu a senha?</a></div>
<div class="link">Nao tem conta? <a href="/cadastro">Criar conta</a></div>
{% endblock %}
"""

TEMPLATE_DASHBOARD = """
{% extends "base" %}
{% block content %}
<h1>Bem-vindo, {{ usuario_login }}!</h1>
<p>Seu ID de usuario: <strong>{{ usuario_id }}</strong></p>
<p>Sua sessao esta isolada. Nenhum dado de outros usuarios e acessivel.</p>
<button onclick="window.location.href='/logout'">Sair</button>
{% endblock %}
"""

TEMPLATE_ADMIN = """
{% extends "base" %}
{% block content %}
<h1>Painel do Administrador</h1>
<div class="nav">
    <a href="/admin">Usuarios</a>
    <a href="/logout">Sair</a>
</div>
<table>
    <tr>
        <th>ID</th>
        <th>Login</th>
        <th>E-mail</th>
        <th>Cadastro</th>
        <th>Reset de Senha</th>
    </tr>
    {% for u in usuarios %}
    <tr>
        <td>{{ u.id }}</td>
        <td>{{ u.login }}</td>
        <td>{{ u.email }}</td>
        <td>{{ u.data_cadastro }}</td>
        <td>
            <form method="POST" action="/admin/reset/{{ u.id }}" style="display:inline;">
                <button type="submit" class="btn-small">Reenviar troca de senha</button>
            </form>
        </td>
    </tr>
    {% endfor %}
</table>
<div class="info">As senhas dos usuarios NAO sao exibidas nem armazenadas em texto puro.
Apenas o hash e guardado no banco de dados.</div>
{% endblock %}
"""

TEMPLATE_RECUPERAR = """
{% extends "base" %}
{% block content %}
<h1>Recuperar Senha</h1>
<form method="POST" action="/recuperar">
    <label>Digite seu e-mail cadastrado:</label>
    <input type="email" name="email" required placeholder="seu@email.com">
    <button type="submit">Enviar link de redefinicao</button>
</form>
<div class="link"><a href="/login">Voltar para login</a></div>
{% endblock %}
"""

TEMPLATE_REDEFINIR = """
{% extends "base" %}
{% block content %}
<h1>Redefinir Senha</h1>
<form method="POST" action="/redefinir/{{ token }}">
    <label>Nova senha (ate 10 caracteres):</label>
    <input type="password" name="senha" required maxlength="10" placeholder="********">
    <button type="submit">Redefinir</button>
</form>
{% endblock %}
"""

# ============================================================
# FUNCAO HELPER PARA RENDERIZAR TEMPLATES
# ============================================================
def _render(template_content, titulo, **kwargs):
    """Renderiza um template filho dentro do template base."""
    start = template_content.find('{% block content %}') + len('{% block content %}')
    end = template_content.find('{% endblock %}')
    block_content = template_content[start:end]
    full_template = TEMPLATE_BASE.replace('{% block content %}{% endblock %}', block_content)
    return render_template_string(full_template, titulo=titulo, **kwargs)

# ============================================================
# ROTAS
# ============================================================
@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/cadastro", methods=["GET", "POST"])
def cadastro():
    if request.method == "POST":
        login = request.form["login"].strip()
        email = request.form["email"].strip()
        senha = request.form["senha"]

        valido, msg = validar_senha(senha)
        if not valido:
            flash(msg, "danger")
            return redirect(url_for("cadastro"))

        senha_hash = bcrypt.generate_password_hash(senha).decode("utf-8")
        conn = get_db()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO usuarios (login, email, senha_hash, data_cadastro) VALUES (?, ?, ?, ?)",
                (login, email, senha_hash, datetime.now().strftime("%d/%m/%Y %H:%M"))
            )
            conn.commit()
            flash("Cadastro realizado com sucesso! Faca login.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Este login ja existe. Escolha outro.", "danger")
            return redirect(url_for("cadastro"))
        finally:
            conn.close()
    return _render(TEMPLATE_CADASTRO, "Cadastro")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_input = request.form["login"].strip()
        senha = request.form["senha"]
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM usuarios WHERE login = ?", (login_input,))
        user = cursor.fetchone()
        conn.close()
        if user and bcrypt.check_password_hash(user["senha_hash"], senha):
            session["usuario_id"] = user["id"]
            session["usuario_login"] = user["login"]
            flash("Login realizado com sucesso!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Login ou senha invalidos.", "danger")
            return redirect(url_for("login"))
    return _render(TEMPLATE_LOGIN, "Login")

@app.route("/dashboard")
def dashboard():
    if "usuario_id" not in session:
        flash("Voce precisa estar logado.", "danger")
        return redirect(url_for("login"))
    return _render(TEMPLATE_DASHBOARD, "Dashboard", usuario_id=session.get("usuario_id"), usuario_login=session.get("usuario_login"))

@app.route("/logout")
def logout():
    session.clear()
    flash("Voce saiu do sistema.", "info")
    return redirect(url_for("login"))

@app.route("/admin")
def admin():
    if session.get("usuario_login") != "admin":
        flash("Acesso restrito ao administrador.", "danger")
        return redirect(url_for("login"))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, login, email, data_cadastro FROM usuarios ORDER BY id")
    usuarios = cursor.fetchall()
    conn.close()
    return _render(TEMPLATE_ADMIN, "Admin", usuarios=usuarios)

@app.route("/admin/reset/<int:user_id>", methods=["POST"])
def admin_reset(user_id):
    if session.get("usuario_login") != "admin":
        flash("Acesso restrito.", "danger")
        return redirect(url_for("login"))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM usuarios WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if user:
        token = secrets.token_urlsafe(32)
        expira = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("UPDATE usuarios SET token_reset = ?, token_expira = ? WHERE id = ?",
                       (token, expira, user_id))
        conn.commit()
        link = f"http://localhost:5000/redefinir/{token}"
        corpo = f"""
        <h2>Redefinicao de Senha</h2>
        <p>Foi solicitada a redefinicao da sua senha.</p>
        <p>Clique no link abaixo para criar uma nova senha:</p>
        <p><a href="{link}">Redefinir minha senha</a></p>
        <p>Este link expira em 1 hora.</p>
        """
        if enviar_email(user["email"], "Redefinicao de Senha", corpo):
            flash(f"E-mail de redefinicao enviado para o usuario ID {user_id}.", "success")
        else:
            flash("Erro ao enviar e-mail. Verifique as configuracoes de SMTP.", "danger")
    else:
        flash("Usuario nao encontrado.", "danger")
    conn.close()
    return redirect(url_for("admin"))

@app.route("/recuperar", methods=["GET", "POST"])
def recuperar():
    if request.method == "POST":
        email = request.form["email"].strip()
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM usuarios WHERE email = ?", (email,))
        user = cursor.fetchone()
        if user:
            token = secrets.token_urlsafe(32)
            expira = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("UPDATE usuarios SET token_reset = ?, token_expira = ? WHERE id = ?",
                           (token, expira, user["id"]))
            conn.commit()
            link = f"http://localhost:5000/redefinir/{token}"
            corpo = f"""
            <h2>Recuperacao de Senha</h2>
            <p>Voce solicitou a recuperacao de senha.</p>
            <p><a href="{link}">Clique aqui para redefinir sua senha</a></p>
            <p>Este link expira em 1 hora.</p>
            """
            if enviar_email(email, "Recuperacao de Senha", corpo):
                flash("Link de recuperacao enviado para seu e-mail.", "success")
            else:
                flash("Erro ao enviar e-mail.", "danger")
        else:
            flash("Se o e-mail estiver cadastrado, voce recebera um link.", "info")
        conn.close()
        return redirect(url_for("login"))
    return _render(TEMPLATE_RECUPERAR, "Recuperar Senha")

@app.route("/redefinir/<token>", methods=["GET", "POST"])
def redefinir(token):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE token_reset = ?", (token,))
    user = cursor.fetchone()
    if not user:
        flash("Token invalido ou expirado.", "danger")
        conn.close()
        return redirect(url_for("login"))
    expira = datetime.strptime(user["token_expira"], "%Y-%m-%d %H:%M:%S")
    if datetime.now() > expira:
        flash("Token expirado. Solicite novamente.", "danger")
        conn.close()
        return redirect(url_for("recuperar"))
    if request.method == "POST":
        nova_senha = request.form["senha"]
        valido, msg = validar_senha(nova_senha)
        if not valido:
            flash(msg, "danger")
            return redirect(url_for("redefinir", token=token))
        nova_hash = bcrypt.generate_password_hash(nova_senha).decode("utf-8")
        cursor.execute("UPDATE usuarios SET senha_hash = ?, token_reset = NULL, token_expira = NULL WHERE id = ?",
                       (nova_hash, user["id"]))
        conn.commit()
        conn.close()
        flash("Senha redefinida com sucesso! Faca login.", "success")
        return redirect(url_for("login"))
    conn.close()
    return _render(TEMPLATE_REDEFINIR, "Redefinir Senha", token=token)

# ============================================================
# CRIAR USUARIO ADMIN PADRAO (executar uma vez)
# ============================================================
def criar_admin():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE login = 'admin'")
    if not cursor.fetchone():
        senha_hash = bcrypt.generate_password_hash("Admin123").decode("utf-8")
        cursor.execute(
            "INSERT INTO usuarios (login, email, senha_hash, data_cadastro) VALUES (?, ?, ?, ?)",
            ("admin", "admin@sistema.com", senha_hash, datetime.now().strftime("%d/%m/%Y %H:%M"))
        )
        conn.commit()
        print("Admin criado - Login: admin | Senha: Admin123")
    conn.close()

criar_admin()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
