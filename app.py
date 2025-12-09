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
    
    # Se tiver virgula como separador decimal (Formato BR: 1.000,00)
    # Mas cuidado: 1,000.00 (US) vs 1.000,00 (BR)
    # Assumimos BR se houver virgula no final ou apenas virgula
    try:
        if ',' in val and '.' in val:
            val = val.replace('.', '').replace(',', '.')
        elif ',' in val:
            val = val.replace(',', '.')
        return float(val)
    except:
        return pd.to_numeric(val, errors='coerce')

def extrair_os(texto):
    """
    Pega a OS no início do texto.
    Ex: '001-67494-55 ANA JULIA' -> '001-67494-55'
    """
    texto = str(texto).strip()
    match = re.search(r'^([\d-]+)', texto)
    if match:
        return match.group(1).strip()
    return None 

def ler_arquivo_texto(uploaded_file):
    """Lê arquivo CSV/Texto tentando várias codificações."""
    bytes_data = uploaded_file.getvalue()
    for encoding in ['utf-8', 'latin1', 'cp1252']:
        try:
            return bytes_data.decode(encoding).splitlines()
        except UnicodeDecodeError:
            continue
    return bytes_data.decode('utf-8', errors='ignore').splitlines()

# --- PROCESSAMENTO ---

def processar_extrato(uploaded_file):
    """Processa o arquivo da BASE (Extrato/Convênio) - Geralmente CSV."""
    try:
        # Extratos parecem ser sempre CSV baseados no seu histórico
        linhas = ler_arquivo_texto(uploaded_file)
        
        area_nome = "Desconhecido"
        if len(linhas) > 8:
            partes = linhas[8].split(';')
            if len(partes) > 1:
                area_nome = partes[1].strip()

        inicio = 0
        for i, linha in enumerate(linhas):
            if "Cod O.S." in linha or "Data;Nome" in linha:
                inicio = i
                break
        
        df = pd.read_csv(io.StringIO("\n".join(linhas[inicio:])), sep=';', dtype=str)
        
        col_os = next((c for c in df.columns if 'Cod O.S.' in c or 'OS' in c), None)
        col_valor = next((c for c in df.columns if 'Valor' in c), None)
        
        if col_os and col_valor:
            df['OS_Final'] = df[col_os].str.strip()
            df['Valor_Final'] = df[col_valor].apply(limpar_valor)
            df['Area'] = area_nome
            df = df.dropna(subset=['OS_Final'])
            return df[['OS_Final', 'Valor_Final', 'Area', 'Nome']]
            
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro no extrato {uploaded_file.name}: {e}")
        return pd.DataFrame()

def normalizar_df_caixa(df, nome_arquivo):
    """Função auxiliar para limpar o DF depois de lido (seja do Excel ou CSV)"""
    # Padroniza colunas
    df.columns = [str(c).upper().strip() for c in df.columns]
    
    col_nome = next((c for c in df.columns if 'NOME' in c or 'HISTORICO' in c or 'DESCRI' in c), None)
    col_valor = next((c for c in df.columns if 'VALOR' in c), None)
    
    if col_nome and col_valor:
        df['OS_Caixa'] = df[col_nome].apply(extrair_os)
        df['Valor_Caixa'] = df[col_valor].apply(limpar_valor)
        df['Arquivo'] = nome_arquivo
        
        # Remove linhas que não são dados de pacientes (totais, saldos)
        df = df.dropna(subset=['OS_Caixa'])
        return df[['OS_Caixa', 'Valor_Caixa', 'Arquivo']]
    
    return pd.DataFrame()

def processar_caixa(uploaded_file):
    """
    Processa arquivos do CAIXA.
    Identifica automaticamente se é Excel (.xlsx) ou CSV.
    """
    try:
        nome_arquivo = uploaded_file.name
        dfs_para_juntar = []

        # >>> ESTRATÉGIA 1: ARQUIVO EXCEL (.xlsx, .xls)
        if nome_arquivo.lower().endswith(('.xlsx', '.xls')):
            try:
                # Lê todas as abas (sheet_name=None retorna um dicionario de DFs)
                dict_sheets = pd.read_excel(uploaded_file, sheet_name=None, header=None)
                
                for aba, df_bruto in dict_sheets.items():
                    # Procura em qual linha está o cabeçalho nesta aba
                    header_idx = -1
                    for i, row in df_bruto.head(20).iterrows():
                        # Converte a linha toda para texto para buscar "VALOR" e "NOME"
                        linha_texto = " ".join([str(x).upper() for x in row.values])
                        if "VALOR" in linha_texto and ("NOME" in linha_texto or "OS" in linha_texto):
                            header_idx = i
                            break
                    
                    if header_idx != -1:
                        # Pega os dados da linha do cabeçalho para baixo
                        df_aba = df_bruto.iloc[header_idx+1:].copy()
                        df_aba.columns = df_bruto.iloc[header_idx] # Define o nome das colunas
                        
                        # Processa e limpa
                        df_limpo = normalizar_df_caixa(df_aba, f"{nome_arquivo} ({aba})")
                        if not df_limpo.empty:
                            dfs_para_juntar.append(df_limpo)
                            
                if dfs_para_juntar:
                    return pd.concat(dfs_para_juntar, ignore_index=True)
                else:
                    st.warning(f"⚠️ Li o Excel {nome_arquivo}, mas não achei tabelas válidas nas abas.")
                    return pd.DataFrame()

            except Exception as e:
                st.error(f"Erro ao ler Excel {nome_arquivo}: {e}")
                return pd.DataFrame()

        # >>> ESTRATÉGIA 2: ARQUIVO CSV/TEXTO
        else:
            linhas = ler_arquivo_texto(uploaded_file)
            header_idx = -1
            sep = ','
            
            for i, linha in enumerate(linhas):
                l_upper = linha.upper()
                if "VALOR" in l_upper and ("NOME" in l_upper or "OS" in l_upper):
                    header_idx = i
                    sep = ';' if linha.count(';') > linha.count(',') else ','
                    break
            
            if header_idx == -1:
                st.warning(f"⚠️ Cabeçalho não encontrado em {nome_arquivo} (CSV).")
                return pd.DataFrame()

            df = pd.read_csv(io.StringIO("\n".join(linhas[header_idx:])), sep=sep, dtype=str, on_bad_lines='skip')
            return normalizar_df_caixa(df, nome_arquivo)

    except Exception as e:
        st.error(f"Erro técnico grave em {uploaded_file.name}: {e}")
        return pd.DataFrame()

# --- INTERFACE ---

st.title("Conferência de Caixa (Inteligente 🧠)")

col1, col2 = st.columns(2)

with col1:
    st.header("1. Base de Dados (Extratos)")
    st.info("Suba os arquivos CSV das áreas/convênios aqui.")
    up_extratos = st.file_uploader("Arquivos da Quinzena", accept_multiple_files=True, key="ext")

with col2:
    st.header("2. Caixas (Meninas)")
    st.info("Suba os arquivos CSV ou EXCEL dos caixas aqui.")
    up_caixas = st.file_uploader("Arquivos dos Caixas", accept_multiple_files=True, key="cx")

# Processamento
df_base = pd.DataFrame()
df_caixa = pd.DataFrame()

if up_extratos:
    lista = [processar_extrato(f) for f in up_extratos]
    lista = [d for d in lista if not d.empty]
    if lista:
        df_base = pd.concat(lista, ignore_index=True)
        st.success(f"Base carregada: {len(df_base)} exames importados.")

if up_caixas:
    lista = [processar_caixa(f) for f in up_caixas]
    lista = [d for d in lista if not d.empty]
    if lista:
        df_caixa = pd.concat(lista, ignore_index=True)
        st.success(f"Caixa carregado: {len(df_caixa)} lançamentos importados.")

# Conferência
if not df_base.empty and not df_caixa.empty:
    st.divider()
    st.subheader("📊 Resultado da Conferência")
    
    # Merge apenas pela OS
    df_final = pd.merge(
        df_caixa,
        df_base,
        left_on='OS_Caixa',
        right_on='OS_Final',
        how='left',
        indicator=True
    )
    
    df_final['Diferenca'] = df_final['Valor_Caixa'] - df_final['Valor_Final']
    
    # Grupos
    mask_ok = (df_final['_merge'] == 'both') & (abs(df_final['Diferenca']) < 0.05)
    df_ok = df_final[mask_ok]
    
    mask_div = (df_final['_merge'] == 'both') & (abs(df_final['Diferenca']) >= 0.05)
    df_div = df_final[mask_div]
