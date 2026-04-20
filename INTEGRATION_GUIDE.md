# 🔌 Guia de Integração: Nuvem e Produção

Este guia detalha como conectar o **Second Brain App** a serviços em nuvem, garantindo uma transição suave do ambiente de laboratório local para produção.

## 1. Google Gemini API (Modelos de Linguagem)

O sistema está preparado para atuar como um roteador de LLM. 

### Onde configurar:
- **Arquivo**: `app/services/llm_orchestrator.py`
- **Configuração**: Adicione sua chave no `.env` como `GEMINI_API_KEY`.

### Exemplo de Implementação:
Para adicionar suporte oficial, você deve inserir o SDK do Google no método `generate_chat_completion`:

```python
# app/services/llm_orchestrator.py
import google.generativeai as genai

# No __init__:
genai.configure(api_key=self.gemini_api_key)

# No generate_chat_completion:
if model_name.startswith("gemini-"):
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(messages)
    return {"message": {"content": response.text}}
```

## 2. Supabase (pgvector / Banco de Dados)

O Supabase fornece uma instância robusta de PostgreSQL com a extensão `pgvector`. Não é necessário código adicional, apenas a URL de conexão correta.

### Configuração no `.env`:
Substitua a URL local pela URL do seu projeto no Supabase:

```env
# Produção (Supabase)
POSTGRES_DSN=postgresql://postgres:[SUA_SENHA]@[SEU_ID_PROJETO].supabase.co:5432/postgres
POSTGRES_SCHEMA=research
```

**Nota**: Certifique-se de que a extensão `pgvector` está habilitada no painel do Supabase (`CREATE EXTENSION vector;`).

## 3. Modelos Locais (SentenceTransformers)

Para manter a privacidade total sem custo de API em nuvem:
1. Baixe o modelo usando o script `scripts/download_sentence_transformer.py`.
2. Mova a pasta resultante para `/models`.
3. Na interface do laboratório, selecione o modelo com o prefixo `local:`. Ex: `local:all-MiniLM-L6-v2`.

## 4. Segurança de Credenciais

⚠️ **NUNCA** faça commit do arquivo `.env`. 
Use sempre o `.env.example` como base. O projeto já está configurado para ignorar arquivos de segredo e binários de modelos através do `.gitignore`.
