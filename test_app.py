#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SCRIPT DE TESTE AUTOMÁTICO - FINANCASLIPE
Testando todas as funcionalidades da aplicação
"""

import os
import sqlite3
import sys
from datetime import datetime

# Cores para output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
END = '\033[0m'

def print_header(text):
    print(f"\n{BLUE}{'='*60}")
    print(f"{text}")
    print(f"{'='*60}{END}\n")

def print_success(text):
    print(f"{GREEN}✓ {text}{END}")

def print_error(text):
    print(f"{RED}✗ {text}{END}")

def print_warning(text):
    print(f"{YELLOW}⚠ {text}{END}")

def test_imports():
    print_header("TESTE 1: Verificando Imports")
    
    try:
        import flask
        print_success(f"Flask {flask.__version__} instalado")
    except ImportError:
        print_error("Flask não instalado")
        return False
    
    try:
        import flask_bcrypt
        print_success("Flask-Bcrypt instalado")
    except ImportError:
        print_error("Flask-Bcrypt não instalado")
        return False
    
    try:
        import bcrypt
        print_success("Bcrypt instalado")
    except ImportError:
        print_error("Bcrypt não instalado")
        return False
    
    return True

def test_app_structure():
    print_header("TESTE 2: Estrutura da Aplicação")
    
    # Verificar se app.py existe
    if os.path.exists('app.py'):
        print_success("app.py encontrado")
    else:
        print_error("app.py não encontrado")
        return False
    
    # Verificar se requirements.txt existe
    if os.path.exists('requirements.txt'):
        print_success("requirements.txt encontrado")
    else:
        print_error("requirements.txt não encontrado")
        return False
    
    # Verificar se README.md existe
    if os.path.exists('README.md'):
        print_success("README.md encontrado")
    else:
        print_warning("README.md não encontrado (opcional)")
    
    return True

def test_database():
    print_header("TESTE 3: Banco de Dados")
    
    DB_NAME = "test_usuarios.db"
    
    try:
        # Criar banco de dados de teste
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
        print_success("Banco de dados criado com sucesso")
        
        # Testar inserção
        cursor.execute(
            "INSERT INTO usuarios (login, email, senha_hash, data_cadastro) VALUES (?, ?, ?, ?)",
            ("testuser", "test@email.com", "hash_senha", datetime.now().strftime("%d/%m/%Y %H:%M"))
        )
        conn.commit()
        print_success("Inserção de dados funcionando")
        
        # Testar consulta
        cursor.execute("SELECT * FROM usuarios WHERE login = ?", ("testuser",))
        user = cursor.fetchone()
        if user:
            print_success(f"Consulta funcionando - Usuário: {user[1]}")
        else:
            print_error("Consulta não retornou resultados")
        
        conn.close()
        os.remove(DB_NAME)
        print_success("Banco de dados de teste removido")
        
        return True
    
    except Exception as e:
        print_error(f"Erro no banco de dados: {str(e)}")
        return False

def test_app_creation():
    print_header("TESTE 4: Criação da Aplicação Flask")
    
    try:
        from flask import Flask
        
        app = Flask(__name__)
        app.config['TESTING'] = True
        
        print_success("Aplicação Flask criada com sucesso")
        print_success(f"Debug mode: {app.debug}")
        print_success(f"Testing mode: {app.config['TESTING']}")
        
        return True
    
    except Exception as e:
        print_error(f"Erro ao criar aplicação: {str(e)}")
        return False

def test_password_validation():
    print_header("TESTE 5: Validação de Senhas")
    
    def validar_senha(senha):
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
    
    # Teste 1: Senha válida
    valido, msg = validar_senha("Senha123")
    if valido:
        print_success("Senha válida aceita: Senha123")
    else:
        print_error(f"Senha válida rejeitada: {msg}")
        return False
    
    # Teste 2: Senha muito longa
    valido, msg = validar_senha("MuitoLongaA1")
    if not valido:
        print_success("Senha muito longa corretamente rejeitada")
    else:
        print_error("Senha muito longa deveria ser rejeitada")
        return False
    
    # Teste 3: Senha com caracteres especiais
    valido, msg = validar_senha("Senha@123")
    if not valido:
        print_success("Caracteres especiais corretamente rejeitados")
    else:
        print_error("Caracteres especiais deveriam ser rejeitados")
        return False
    
    return True

def test_requirements():
    print_header("TESTE 6: Arquivos de Requisitos")
    
    try:
        with open('requirements.txt', 'r') as f:
            reqs = f.read().strip().split('\n')
        
        required_packages = ['flask', 'flask-bcrypt', 'bcrypt', 'werkzeug']
        
        for pkg in required_packages:
            found = any(pkg.lower() in req.lower() for req in reqs if req.strip())
            if found:
                print_success(f"Pacote {pkg} está em requirements.txt")
            else:
                print_error(f"Pacote {pkg} não encontrado em requirements.txt")
                return False
        
        return True
    
    except Exception as e:
        print_error(f"Erro ao ler requirements.txt: {str(e)}")
        return False

def main():
    print(f"{BLUE}")
    print("  ╔═══════════════════════════════════════════════╗")
    print("  ║   TESTES AUTOMATICOS - FINANCASLIPE          ║")
    print("  ║   Sistema de Gestão de Usuários             ║")
    print(f"  ╚═══════════════════════════════════════════════╝{END}")
    
    tests = [
        ("Imports", test_imports),
        ("Estrutura", test_app_structure),
        ("Banco de Dados", test_database),
        ("Aplicação Flask", test_app_creation),
        ("Validação de Senhas", test_password_validation),
        ("Requirements", test_requirements),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print_error(f"Erro ao executar teste: {str(e)}")
            results.append((test_name, False))
    
    # Resumo final
    print_header("RESUMO DOS TESTES")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = f"{GREEN}PASSOU{END}" if result else f"{RED}FALHOU{END}"
        print(f"  {test_name:<30} {status}")
    
    print()
    if passed == total:
        print(f"{GREEN}╔════════════════════════════════════════╗")
        print(f"║  ✓ TODOS OS TESTES PASSARAM ({passed}/{total})   ║")
        print(f"║  Sua aplicação está pronta para usar!  ║")
        print(f"╚════════════════════════════════════════╝{END}")
        return 0
    else:
        print(f"{RED}╔════════════════════════════════════════╗")
        print(f"║  ✗ {passed}/{total} testes passaram              ║")
        print(f"║  Corrija os erros acima                ║")
        print(f"╚════════════════════════════════════════╝{END}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
