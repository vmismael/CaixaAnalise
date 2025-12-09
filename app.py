import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="Conferência de Caixa", layout="wide")

# --- FUNÇÕES DE LIMPEZA ---

def limpar_valor(valor_str):
    """Converte dinheiro para float, suportando R$ e formatos BR/US."""
    if pd.isna(valor_str): return 0.0
    val = str(valor_str).strip()
    val = val.replace('R$', '').strip()
    
    if not val or val in ['-', 'nan', 'None']: return 0.0
    
    # Tira pontos de milhar e troca vírgula por ponto (Formato BR)
    # Ex: 1.250,00 -> 1250.00
    if ',' in val:
        val = val.replace('.', '').replace(',', '.')
    
    return pd.to_numeric(val, errors='coerce')

def extrair_os(texto):
    """
    Pega a OS no início do texto.
    Ex: '001-67494-55 ANA JULIA' -> '001-67494-55'
    """
    texto = str(texto).strip()
    # Pega sequência de números e traços no começo da linha
    match = re.search(r'^([\d-]+)', texto)
    if match:
        return match.group(1).strip()
    return None # Retorna None se não achar OS, para filtrarmos depois

def ler_arquivo_texto(uploaded_file):
    """Lê o arquivo de forma bruta tentando várias codificações."""
    bytes_data = uploaded_file.getvalue()
    for encoding in ['utf-8', 'latin1', 'cp1252']:
        try:
            return bytes_data.decode(encoding).splitlines()
        except UnicodeDecodeError:
            continue
    return bytes_data.decode('utf-8', errors='ignore').splitlines()

# --- PROCESSAMENTO ---

def processar_extrato(uploaded_file):
    """Processa o arquivo da BASE (Extrato/Convênio)."""
    try:
        linhas = ler_arquivo_texto(uploaded_file)
        
        # Tenta pegar Área na linha 8 (índice 8 = B9)
        area_nome = "Desconhecido"
        if len(linhas) > 8:
            partes = linhas[8].split(';')
            if len(partes) > 1:
                area_nome = partes[1].strip()

        # Acha cabeçalho (procura Cod O.S. ou Data;Nome)
        inicio = 0
        for i, linha in enumerate(linhas):
            if "Cod O.S." in linha or "Data;Nome" in linha:
                inicio = i
                break
        
        # Lê CSV
        df = pd.read_csv(io.StringIO("\n".join(linhas[inicio:])), sep=';', dtype=str)
        
        # Limpeza
        col_os = next((c for c in df.columns if 'Cod O.S.' in c or 'OS' in c), None)
        col_valor = next((c for c in df.columns if 'Valor' in c), None)
        
        if col_os and col_valor:
            df['OS_Final'] = df[col_os].str.strip()
            df['Valor_Final'] = df[col_valor].apply(limpar_valor)
            df['Area'] = area_nome
            df = df.dropna(subset=['OS_Final']) # Remove linhas vazias
            return df[['OS_Final', 'Valor_Final', 'Area', 'Nome']]
            
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro no extrato {uploaded_file.name}: {e}")
        return pd.DataFrame()

def processar_caixa(uploaded_file):
    """Processa o arquivo do CAIXA (Isis, Nathy, etc)."""
    try:
        linhas = ler_arquivo_texto(uploaded_file)
        
        # 1. Busca FLEXÍVEL pelo cabeçalho
        # Procura qualquer linha que tenha "VALOR" e ("NOME" ou "OS")
        header_idx = -1
        sep = ','
        
        for i, linha in enumerate(linhas):
            l_upper = linha.upper()
            # Ignoramos a exigência de "DATA". Basta ter Valor e Nome/OS.
            if "VALOR" in l_upper and ("NOME" in l_upper or "OS" in l_upper or "CONVENIO" in l_upper):
                header_idx = i
                # Decide separador
                sep = ';' if linha.count(';') > linha.count(',') else ','
                break
        
        if header_idx == -1:
            st.warning(f"⚠️ Não achei colunas (VALOR e NOME) no arquivo {uploaded_file.name}")
            return pd.DataFrame()

        # 2. Lê CSV
        df = pd.read_csv(
            io.StringIO("\n".join(linhas[header_idx:])), 
            sep=sep, 
            dtype=str, 
            on_bad_lines='skip'
        )
        
        # 3. Normaliza colunas (Maiúsculas e sem espaços)
        df.columns = [str(c).upper().strip() for c in df.columns]
        
        # 4. Identifica Colunas
        col_nome = next((c for c in df.columns if 'NOME' in c or 'HISTORICO' in c or 'DESCRI' in c), None)
        col_valor = next((c for c in df.columns if 'VALOR' in c), None)
        
        if col_nome and col_valor:
            # Extrai OS e Limpa Valor
            df['OS_Caixa'] = df[col_nome].apply(extrair_os)
            df['Valor_Caixa'] = df[col_valor].apply(limpar_valor)
            df['Arquivo'] = uploaded_file.name
            
            # Remove quem não tem OS (linhas de saldo, totais, ou texto solto)
            df = df.dropna(subset=['OS_Caixa'])
            
            return df[['OS_Caixa', 'Valor_Caixa', 'Arquivo']]
        
        return pd.DataFrame()

    except Exception as e:
        st.error(f"Erro técnico ao ler caixa {uploaded_file.name}: {e}")
        return pd.DataFrame()

# --- INTERFACE ---

st.title("Conferência de Caixa (Via OS)")

col1, col2 = st.columns(2)

with col1:
    st.header("1. Base de Dados (Extratos)")
    up_extratos = st.file_uploader("Arquivos da Quinzena", accept_multiple_files=True, key="ext")

with col2:
    st.header("2. Caixas (Meninas)")
    up_caixas = st.file_uploader("Arquivos dos Caixas", accept_multiple_files=True, key="cx")

# Processamento
df_base = pd.DataFrame()
df_caixa = pd.DataFrame()

if up_extratos:
    lista = [processar_extrato(f) for f in up_extratos]
    # Filtra dfs vazios
    lista = [d for d in lista if not d.empty]
    if lista:
        df_base = pd.concat(lista, ignore_index=True)
        st.success(f"Base: {len(df_base)} registros importados.")

if up_caixas:
    lista = [processar_caixa(f) for f in up_caixas]
    lista = [d for d in lista if not d.empty]
    if lista:
        df_caixa = pd.concat(lista, ignore_index=True)
        st.info(f"Caixa: {len(df_caixa)} registros importados.")

# Conferência
if not df_base.empty and not df_caixa.empty:
    st.divider()
    st.subheader("Resultado do Cruzamento (Pela OS)")
    
    # Merge apenas pela OS
    df_final = pd.merge(
        df_caixa,
        df_base,
        left_on='OS_Caixa',
        right_on='OS_Final',
        how='left',
        indicator=True
    )
    
    # Cálculos
    df_final['Diferenca'] = df_final['Valor_Caixa'] - df_final['Valor_Final']
    
    # Grupos
    # 1. Bateu (Existe na base e diferença < 0.05 centavos)
    mask_ok = (df_final['_merge'] == 'both') & (abs(df_final['Diferenca']) < 0.05)
    df_ok = df_final[mask_ok]
    
    # 2. Divergente (Existe na base mas valor errado)
    mask_div = (df_final['_merge'] == 'both') & (abs(df_final['Diferenca']) >= 0.05)
    df_div = df_final[mask_div]
    
    # 3. Não encontrado (OS do caixa não existe na base)
    mask_nao = (df_final['_merge'] == 'left_only')
    df_nao = df_final[mask_nao]
    
    # 4. Duplicados
    duplicados = df_caixa[df_caixa.duplicated(subset=['OS_Caixa'], keep=False)]
    
    # Abas
    t1, t2, t3, t4 = st.tabs(["✅ Tudo Certo", "⚠️ Valor Diferente", "❌ OS Não Encontrada", "👀 Duplicidade"])
    
    with t1:
        st.metric("Quantidade", len(df_ok))
        st.dataframe(df_ok[['OS_Caixa', 'Valor_Caixa', 'Area', 'Nome']])
        
    with t2:
        st.metric("Quantidade", len(df_div))
        if not df_div.empty:
            st.dataframe(df_div[['OS_Caixa', 'Valor_Caixa', 'Valor_Final', 'Diferenca', 'Area', 'Arquivo']].style.format("{:.2f}", subset=['Valor_Caixa', 'Valor_Final', 'Diferenca']))
            
    with t3:
        st.metric("Quantidade", len(df_nao))
        st.write("Estas OS constam no caixa, mas não nos arquivos de extrato importados:")
        st.dataframe(df_nao[['OS_Caixa', 'Valor_Caixa', 'Arquivo']])
        
    with t4:
        if not duplicados.empty:
            st.warning("OS lançada mais de uma vez no caixa:")
            st.dataframe(duplicados.sort_values('OS_Caixa'))
        else:
            st.success("Sem duplicidades.")

elif up_caixas and df_base.empty:
    st.warning("Aguardando upload dos Extratos (Base) para comparar.")
