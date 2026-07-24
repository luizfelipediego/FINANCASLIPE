#!/usr/bin/env python3
"""
create_admin.py

Script auxiliar para inicializar o banco (se necessário) e criar ou atualizar
uma conta de administrador sem que você precise colocar a senha em um arquivo.

Uso:
    python create_admin.py

O script pede o email e a senha de forma interativa.
"""
import sys
import getpass

try:
    from db import init_db, create_initial_admin, get_user_by_email, set_user_password
except Exception as e:
    print("Erro ao importar funções de db.py:", e)
    print("Certifique-se de estar executando este script na mesma pasta que db.py e que as dependências estão instaladas.")
    sys.exit(1)


def prompt_yes_no(prompt: str) -> bool:
    ans = input(prompt + " [y/N]: ").strip().lower()
    return ans == "y" or ans == "yes"


def main():
    print("== Criar / Atualizar administrador ==")
    email = input("Email do administrador: ").strip()
    if not email:
        print("Email não informado. Saindo.")
        return

    senha = getpass.getpass("Senha (não será exibida enquanto digita): ").strip()
    if not senha:
        print("Senha vazia. Saindo.")
        return

    # Inicializa (cria tabelas se necessário)
    try:
        init_db()
    except Exception as e:
        print("Falha ao inicializar o banco:", e)
        return

    # Verifica existência
    try:
        existing = get_user_by_email(email)
    except Exception as e:
        print("Erro ao consultar usuário existente:", e)
        return

    try:
        if existing:
            print(f"Já existe um usuário com o email {email} (id={existing.get('id')}).")
            if prompt_yes_no("Deseja sobrescrever/atualizar a senha desse usuário?"):
                set_user_password(existing.get("id"), senha)
                print("Senha atualizada com sucesso.")
            else:
                print("Nenhuma alteração feita.")
        else:
            create_initial_admin(email, senha, send_email_flag=False)
            print("Administrador criado com sucesso.")
    except Exception as e:
        print("Erro ao criar/atualizar administrador:", e)


if __name__ == "__main__":
    main()