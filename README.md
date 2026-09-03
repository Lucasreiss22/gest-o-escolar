# Sistema de Gestão Escolar (SGE)

## Visão Geral
Sistema web de gestão escolar completo, responsivo e multiusuário voltado para o controle acadêmico, financeiro, administrativo e pedagógico de instituições de ensino[cite: 5]. O projeto conta com diferentes níveis de acesso e permissões (RBAC) para garantir que cada usuário visualize apenas as funcionalidades autorizadas[cite: 5].

---

## 🛠️ Tecnologias Utilizadas
* **Back-end:** Python, Flask, Werkzeug, Psycopg2
* **Banco de Dados:** PostgreSQL
* **Front-end:** HTML5, CSS3, Jinja2 Templates, Bootstrap
* **Gerenciamento de Arquivos:** Upload local para salvamento de PDFs e anexos de provas/documentos

---

## 📋 Módulos e Funcionalidades Implementadas

* **Autenticação e Segurança:** 
  * Sistema de login seguro com controle de sessão.
  * Controle de Acesso Baseado em Papéis (RBAC), distinguindo perfis como administradores, professores e secretaria.

* **Painel Inicial (Dashboard):** 
  * Métricas em tempo real de alunos ativos, professores e turmas cadastradas.

* **Gestão de Alunos:** 
  * Cadastro completo de discentes, dados pessoais, endereços e histórico.
  * Vínculo com múltiplos responsáveis e pessoas autorizadas.
  * Lançamento de notas, anexos de provas em PDF e controle financeiro individual.

* **Gestão Pedagógica e Turmas:** 
  * Criação e gerenciamento de turmas, turnos e anos letivos.
  * Associação de alunos e professores responsáveis às turmas.
  * Calendário escolar integrado com eventos gerais e específicos.

* **Gestão de Professores e Funcionários:** 
  * Cadastro de funcionários com especificação de cargos (professores, administrativos, etc.).
  * Controle de especialidades e vínculos acadêmicos.

* **Módulo Financeiro:** 
  * Geração de mensalidades individuais e em lote para alunos ativos.
  * Controle de status de pagamentos (Pendente, Pago, Atrasado) e baixa de faturas.

* **Configurações e Usuários:** 
  * Tela de gerenciamento de usuários restrita a administradores do sistema[cite: 5].
  * Configurações gerais de parâmetros da instituição.

---

## 🚀 Como Executar o Projeto

1. Clone o repositório para o seu ambiente local.
2. Certifique-se de ter o **Python** e o **PostgreSQL** instalados.
3. Instale as dependências necessárias do projeto (como Flask e Psycopg2).
4. Configure as variáveis de ambiente necessárias (como a string de conexão com o banco de dados e a `SECRET_KEY`).
5. Execute a aplicação executando o arquivo principal:
   ```bash
   python app.py
