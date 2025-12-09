import streamlit as st
import pandas as pd
import io
import re

st.set_page_config(page_title="Conferência de Caixa", layout="wide")

# --- FUNÇÕES DE LIMPEZA E EXTRAÇÃO ---

def limpar_valor(valor_str):
    """Converte dinheiro para float."""
    if pd.isna(valor_str): return 0.0
    val = str(valor_str).strip()
    val = val.replace('R$', '').strip()
    
    if not val or val in ['-', 'nan', 'None']: return 0.0
    
    try:
        # Lógica BR: Se tem virgula no final (ex: 100,00) ou (1.000,00)
        if ',' in val:
            val = val.replace('.', '').replace(',', '.')
        return float(val)
    except:
        return 0.0

def extrair_os_avancado(texto):
    """
    Tenta extrair a OS de várias formas.
    Padrão esperado: 001-67494-55 ou similar no início.
    """
    texto = str(texto).strip()
    # Regex: Procura grupo de digitos-digitos-digitos no INICIO da string
    match = re.search(r'^([\d]+-[\d]+-[\d]+)', texto) 
    if match:
        return match.group(1).strip()
    
    # Tentativa 2: Procura qualquer sequencia longa de numeros e traços
    match2 = re.search(r'([\d-]{5,})', texto)
    if match2:
        return match2.group(1).strip()
        
    return None

def ler_arquivo_texto(uploaded_file):
    """Lê arquivo bruto."""
    bytes_data = uploaded_file.getvalue()
    for encoding in ['utf-8', 'latin1', 'cp1252']:
        try:
            return bytes_data.decode(encoding).splitlines()
        except UnicodeDecodeError:
            continue
    return bytes_data.decode('utf-8', errors='ignore').splitlines()

# --- PROCESSAMENTO ---

def processar_extrato(uploaded_file):
    """Lê Base de Dados (Extrato)."""
    try:
        linhas = ler_arquivo_texto(uploaded_file)
        
        # 1. Tenta achar Área (B9)
        area_nome = "Desconhecido"
        if len(linhas) > 8:
            partes = linhas[8].split(';')
            if len(partes) > 1:
                area_nome = partes[1].strip()

        # 2. Acha cabeçalho
        inicio = 0
        for i, linha in enumerate(linhas):
            if "Cod O.S." in linha or "Data;Nome" in linha:
                inicio = i
                break
        
        # 3. Lê CSV
        df = pd.read_csv(io.StringIO("\n".join(linhas[inicio:])), sep=';', dtype=str)
        
        # 4. Identifica colunas
        col_os = next((c for c in df.columns if 'Cod O.S.' in c or 'OS' in c), None)
        col_valor = next((c for c in df.columns if 'Valor' in c), None)
        col_nome = next((c for c in df.columns if 'Nome' in c), 'Nome')
        
        if col_os and col_valor:
            df['OS_Final'] = df[col_os].astype(str).str.strip() # Remove espaços invisíveis
            df['Valor_Final'] = df[col_valor].apply(limpar_valor)
            df['Area'] = area_nome
            
            # Filtra lixo
            df = df.dropna(subset=['OS_Final'])
            df = df[df['OS_Final'].str.len() > 3] # Remove OS muito curta (lixo)
            
            return df[['OS_Final', 'Valor_Final', 'Area', col_nome]]
            
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro no extrato {uploaded_file.name}: {e}")
        return pd.DataFrame()

def normalizar_df_caixa(df, nome_arquivo):
    """Padroniza dataframe do caixa vindo do Excel ou CSV."""
    # Coloca tudo em maiúsculo e tira espaços dos nomes das colunas
    df.columns = [str(c).upper().strip().replace('  ', ' ') for c in df.columns]
    
    # Tenta achar a coluna de NOME/DESCRIÇÃO onde a OS está escondida
    # Lista de possíveis nomes de coluna baseada nos seus arquivos
    possiveis_nomes = ['NOME', 'OS - NOME', 'OS-NOME', 'HISTORICO', 'DESCRIÇÃO', 'CLIENTE']
    col_nome = next((c for c in df.columns if any(x in c for x in possiveis_nomes)), None)
    
    col_valor = next((c for c in df.columns if 'VALOR' in c), None)
    
    if col_nome and col_valor:
        # Extrai a OS
        df['OS_Caixa'] = df[col_nome].apply(extrair_os_avancado)
        df['Valor_Caixa'] = df[col_valor].apply(limpar_valor)
        df['Arquivo'] = nome_arquivo
        
        # Só mantemos linhas que conseguimos ler uma OS válida
        df = df.dropna(subset=['OS_Caixa'])
        
        # Garante que é string limpa para bater com o extrato
        df['OS_Caixa'] = df['OS_Caixa'].astype(str).str.strip()
        
        return df[['OS_Caixa', 'Valor_Caixa', 'Arquivo', col_nome]]
    
    return pd.DataFrame()

def processar_caixa(uploaded_file):
    """Lê caixa (Excel ou CSV)."""
    try:
        nome_arquivo = uploaded_file.name
        dfs_para_juntar = []

        # >>> EXCEL
        if nome_arquivo.lower().endswith(('.xlsx', '.xls')):
            try:
                dict_sheets = pd.read_excel(uploaded_file, sheet_name=None, header=None)
                for aba, df_bruto in dict_sheets.items():
                    # Procura cabeçalho
                    header_idx = -1
                    for i, row in df_bruto.head(20).iterrows():
                        linha_txt = " ".join([str(x).upper() for x in row.values])
                        if "VALOR" in linha_txt and ("NOME" in linha_txt or "OS" in linha_txt):
                            header_idx = i
                            break
                    
                    if header_idx != -1:
                        df_aba = df_bruto.iloc[header_idx+1:].copy()
                        df_aba.columns = df_bruto.iloc[header_idx]
                        df_limpo = normalizar_df_caixa(df_aba, f"{nome_arquivo} ({aba})")
                        if not df_limpo.empty:
                            dfs_para_juntar.append(df_limpo)
            except Exception as e:
                st.warning(f"Erro ao ler abas do Excel {nome_arquivo}: {e}")

        # >>> CSV
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
            
            if header_idx != -1:
                df = pd.read_csv(io.StringIO("\n".join(linhas[header_idx:])), sep=sep, dtype=str, on_bad_lines='skip')
                df_limpo = normalizar_df_caixa(df, nome_arquivo)
                if not df_limpo.empty:
                    dfs_para_juntar.append(df_limpo)

        if dfs_para_juntar:
            return pd.concat(dfs_para_juntar, ignore_index=True)
        return pd.DataFrame()

    except Exception as e:
        return pd.DataFrame()

# --- INTERFACE ---

st.title("Conferência de Caixa 💰")

with st.expander("ℹ️ Como funciona?"):
    st.write("O sistema usa o código da OS para cruzar os dados. Certifique-se que o código da OS está no início do nome no arquivo do caixa (Ex: '001-12345-66 NOME DO PACIENTE').")

c1, c2 = st.columns(2)
with c1:
    st.subheader("1. Base (Extratos)")
    up_ext = st.file_uploader("CSV dos Convênios", accept_multiple_files=True, key="ext")
with c2:
    st.subheader("2. Caixas")
    up_cx = st.file_uploader("Excel/CSV dos Caixas", accept_multiple_files=True, key="cx")

# Checkbox de Debug
debug_mode = st.checkbox("🕵️‍♂️ Modo Debug (Ver dados brutos para entender erro)")

df_base = pd.DataFrame()
df_caixa = pd.DataFrame()

if up_ext:
    lista = [processar_extrato(f) for f in up_ext]
    lista = [d for d in lista if not d.empty]
    if lista:
        df_base = pd.concat(lista, ignore_index=True)
        st.success(f"Base: {len(df_base)} registros.")
        if debug_mode:
            st.write("--- Amostra da BASE (Extrato) ---")
            st.dataframe(df_base.head())

if up_cx:
    lista = [processar_caixa(f) for f in up_cx]
    lista = [d for d in lista if not d.empty]
    if lista:
        df_caixa = pd.concat(lista, ignore_index=True)
        st.success(f"Caixa: {len(df_caixa)} registros.")
        if debug_mode:
            st.write("--- Amostra do CAIXA (Lido) ---")
            st.dataframe(df_caixa.head())

if not df_base.empty and not df_caixa.empty:
    st.divider()
    
    # Tenta o Merge
    df_final = pd.merge(
        df_caixa,
        df_base,
        left_on='OS_Caixa',
        right_on='OS_Final',
        how='left',
        indicator=True
    )
    
    df_final['Diferenca'] = df_final['Valor_Caixa'] - df_final['Valor_Final']
    
    # Análise de Debug do Merge
    if debug_mode:
        st.write("--- Resultado Bruto do Cruzamento ---")
        st.write(f"Total de linhas cruzadas: {len(df_final)}")
        st.write(df_final[['OS_Caixa', 'OS_Final', 'Valor_Caixa', 'Valor_Final', '_merge']].head(10))

    # Filtros
    ok = df_final[(df_final['_merge'] == 'both') & (abs(df_final['Diferenca']) < 0.05)]
    diff = df_final[(df_final['_merge'] == 'both') & (abs(df_final['Diferenca']) >= 0.05)]
    nao_enc = df_final[df_final['_merge'] == 'left_only']
    
    t1, t2, t3 = st.tabs([f"✅ Bateu ({len(ok)})", f"⚠️ Diferença ({len(diff)})", f"❌ Não Achado ({len(nao_enc)})"])
    
    with t1:
        st.dataframe(ok[['OS_Caixa', 'Valor_Caixa', 'Area']])
    with t2:
        st.dataframe(diff[['OS_Caixa', 'Valor_Caixa', 'Valor_Final', 'Diferenca', 'Area']])
    with t3:
        st.dataframe(nao_enc[['OS_Caixa', 'Valor_Caixa', 'Arquivo']])
        
elif up_cx and up_ext and (df_base.empty or df_caixa.empty):
    st.error("Os arquivos foram lidos, mas não consegui extrair dados válidos. Ative o 'Modo Debug' acima e veja se as tabelas aparecem.")
