# Sistema de Gestao de Usuarios com Isolamento de Dados

## Como executar

1. Instale o Python 3.8+
2. Instale as dependencias:
   ```
   pip install -r requirements.txt
   ```
3. Configure o e-mail no arquivo `app.py` (variaveis EMAIL_REMETENTE, EMAIL_SENHA)
4. Execute:
   ```
   python app.py
   ```
5. Acesse: http://localhost:5000

## Credenciais do administrador
- Login: admin
- Senha: Admin123

## Funcionalidades
- Cadastro de usuarios com login unico
- Senhas com hash bcrypt (nunca armazenadas em texto puro)
- Painel administrativo (apenas o admin ve todos os usuarios)
- Redefinicao de senha por e-mail (token com expiracao de 1 hora)
- Isolamento total de dados entre usuarios
- Cada usuario so ve seus proprios dados na sessao
