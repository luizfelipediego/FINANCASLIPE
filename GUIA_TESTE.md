# 🚀 GUIA DE TESTE - FINANCASLIPE

## **PASSO 1: Clonar o Repositório**

```bash
git clone https://github.com/luizfelipediego/FINANCASLIPE.git
cd FINANCASLIPE
```

---

## **PASSO 2: Criar um Ambiente Virtual (Recomendado)**

**No Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**No macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

---

## **PASSO 3: Instalar as Dependências**

```bash
pip install -r requirements.txt
```

**Esperado:**
```
Successfully installed bcrypt-4.1.2 flask-3.0.0 flask-bcrypt-1.0.1 werkzeug-3.0.1
```

---

## **PASSO 4: Executar a Aplicação**

```bash
python app.py
```

**Esperado (no terminal):**
```
Admin criado - Login: admin | Senha: Admin123
 * Serving Flask app 'app'
 * Debug mode: on
 * Running on http://127.0.0.1:5000
```

---

## **PASSO 5: Acessar a Aplicação**

Abra seu navegador e acesse:
```
http://localhost:5000
```

---

## **PASSO 6: Testar as Funcionalidades**

### **Teste 1: Fazer Login com Admin**
1. Será redirecionado para `/login`
2. Use as credenciais padrão:
   - **Login:** `admin`
   - **Senha:** `Admin123`
3. Clique em "Entrar"
4. Você verá o Dashboard

### **Teste 2: Criar Nova Conta**
1. Na página de login, clique em "Criar conta"
2. Preencha:
   - Login: `usuario1`
   - E-mail: `usuario1@email.com`
   - Senha: `Senha123` (máximo 10 caracteres, letras e números)
3. Clique em "Cadastrar"
4. Faça login com a nova conta

### **Teste 3: Acessar Painel Admin**
1. Faça login com `admin` e `Admin123`
2. Acesse: `http://localhost:5000/admin`
3. Você verá a lista de usuários

### **Teste 4: Recuperação de Senha**
1. Na página de login, clique em "Esqueceu a senha?"
2. Digite um e-mail cadastrado
3. **Nota:** Será exibido um erro de SMTP porque o e-mail não está configurado

---

## **⚠️ ERROS COMUNS E SOLUÇÕES**

### **Erro 1: ModuleNotFoundError: No module named 'flask'**
**Solução:**
```bash
pip install -r requirements.txt
```

### **Erro 2: Address already in use (porta 5000 ocupada)**
**Solução 1:** Mate o processo anterior
```bash
# Windows
netstat -ano | findstr :5000
taskkill /PID <PID> /F

# macOS/Linux
lsof -i :5000
kill -9 <PID>
```

**Solução 2:** Use outra porta (edite `app.py` linha 462):
```python
app.run(debug=True, port=5001)
```

### **Erro 3: Arquivo de banco de dados bloqueado**
**Solução:** Delete o arquivo `usuarios.db` e reinicie:
```bash
rm usuarios.db
python app.py
```

### **Erro 4: ModuleNotFoundError: No module named 'flask_bcrypt'**
**Solução:**
```bash
pip install flask-bcrypt
```

---

## **📝 FUNCIONALIDADES DISPONÍVEIS**

✅ **Autenticação:**
- Login/Logout
- Cadastro de usuários
- Senha com hash bcrypt

✅ **Dashboard:**
- Visualização de dados do usuário
- Isolamento de dados

✅ **Painel Admin:**
- Visualizar todos os usuários
- Reenviar link de redefinição de senha

✅ **Recuperação de Senha:**
- Solicitação de reset por e-mail
- Link com expiração de 1 hora

---

## **📧 CONFIGURAR E-MAIL (Opcional)**

Para ativar o envio de e-mails, edite o arquivo `app.py` (linhas 28-30):

```python
EMAIL_REMETENTE = "seu_email@gmail.com"
EMAIL_SENHA = "sua_senha_de_app"  # Gere em https://myaccount.google.com/apppasswords
SMTP_SERVIDOR = "smtp.gmail.com"
SMTP_PORTA = 587
```

### **Como gerar Senha de App do Gmail:**
1. Acesse: https://myaccount.google.com/apppasswords
2. Selecione "Mail" e "Windows Computer"
3. Copie a senha gerada
4. Substitua em `EMAIL_SENHA`

---

## **🎯 RESUMO DOS TESTES**

| Funcionalidade | Status | Comando |
|---|---|---|
| Iniciar app | ✅ | `python app.py` |
| Login admin | ✅ | Acesse `http://localhost:5000` |
| Criar usuário | ✅ | Clique em "Criar conta" |
| Dashboard | ✅ | Faça login |
| Painel Admin | ✅ | Acesse `/admin` como admin |
| Recuperar senha | ⚠️ | Requer configuração de e-mail |

---

## **✨ Seu aplicativo está pronto para usar! 🚀**

Se encontrar algum problema, execute:
```bash
pip install --upgrade -r requirements.txt
```

E reinicie a aplicação.
