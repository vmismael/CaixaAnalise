import streamlit as st
import pandas as pd
import io
import re

# --- Configuração da Página ---
st.set_page_config(page_title="Conferência de Caixa", layout="wide")

# --- Funções Auxiliares ---

def limpar_valor(valor_str):
    """Converte string de dinheiro para float."""
    if pd.isna(valor_str): return 0.0
    val = str(valor_str).strip()
    val = val.replace('R$', '').strip()
    # Lógica para converter "1.250,00" ou "1250.00"
    if ',' in val and '.' in val:
        val = val.replace('.', '').replace(',', '.')
    elif ',' in val:
        val = val.replace(',', '.')
    return pd.to_numeric(val, errors='coerce')

def extrair_os_do_nome(texto):
    """Extrai OS do início do nome (ex: '001-67494-55 ANA...' -> '001-67494-55')"""
    texto = str(texto).strip()
    match = re.search(r'^([\d-]+)', texto)
    if match:
        return match.group(1).strip()
    return texto

def ler_arquivo_resiliente(uploaded_file):
    """
    Tenta decodificar o arquivo usando utf-8 ou latin1.
    Retorna uma lista de strings (linhas).
    """
    bytes_data = uploaded_file.getvalue()
    try:
        texto = bytes_data.decode("utf-8")
    except UnicodeDecodeError:
        texto = bytes_data.decode("latin1", errors='replace')
    return texto.splitlines()

def processar_extrato(uploaded_file):
    """Lê arquivos da Quinzena (Fonte de Dados)"""
    try:
        linhas = ler_arquivo_resiliente(uploaded_file)

        area_nome = "Desconhecido"
        # Tenta pegar a área na B9 (linha 8 index 0)
        if len(linhas) > 8:
            partes_b9 = linhas[8].split(';')
            if len(partes_b9) > 1:
                area_nome = partes_b9[1].strip()

        # Encontrar onde começa a tabela
        inicio_dados = 0
        for i, linha in enumerate(linhas):
            # Procura cabeçalho típico
            if "Data;Nome" in linha or "Cod O.S." in linha:
                inicio_dados = i
                break
        
        # Reconstrói o CSV a partir da linha de cabeçalho
        csv_limpo = "\n".join(linhas[inicio_dados:])
        stringio = io.StringIO(csv_limpo)
        
        df = pd.read_csv(stringio, sep=';', dtype=str)

        if 'Data' in df.columns:
            df = df.dropna(subset=['Data'])
            df = df[df['Data'] != 'Sub-total']
            df['Area'] = area_nome
            
            # Normalizar Coluna de OS
            if 'Cod O.S.' in df.columns:
                df['OS'] = df['Cod O.S.']
            else:
                df['OS'] = 'N/A'

            # Normalizar Valor
            if 'Valor' in df.columns:
                df['Valor_Extrato'] = df['Valor'].apply(limpar_valor)
            
            return df[['Data', 'OS', 'Nome', 'Valor_Extrato', 'Area']]
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro no extrato {uploaded_file.name}: {e}")
        return pd.DataFrame()

def processar_caixa(uploaded_file):
    """Lê arquivos do Caixa com cabeçalho sujo (linhas extras no topo)"""
    try:
        linhas = ler_arquivo_resiliente(uploaded_file)
        
        # 1. Encontrar a linha REAL do cabeçalho
        # Procuramos uma linha que tenha "DATA" e "VALOR"
        indice_cabecalho = -1
        sep_detectado = ',' # Padrão
        
        for i, linha in enumerate(linhas):
            linha_upper = linha.upper()
            if "DATA" in linha_upper and "VALOR" in linha_upper:
                indice_cabecalho = i
                # Verifica qual separador tem mais nessa linha
                if linha.count(';') > linha.count(','):
                    sep_detectado = ';'
                else:
                    sep_detectado = ','
                break
        
        if indice_cabecalho == -1:
            st.warning(f"Não encontrei colunas DATA/VALOR no arquivo {uploaded_file.name}")
            return pd.DataFrame()

        # 2. Criar um novo CSV virtual só da linha do cabeçalho para baixo
        conteudo_limpo = "\n".join(linhas[indice_cabecalho:])
        stringio = io.StringIO(conteudo_limpo)
        
        # 3. Ler com Pandas (agora seguro)
        # on_bad_lines='skip' ignora linhas quebradas no final do arquivo
        try:
            df = pd.read_csv(stringio, sep=sep_detectado, dtype=str, on_bad_lines='skip')
        except TypeError:
            # Versões antigas do pandas usam error_bad_lines
            df = pd.read_csv(stringio, sep=sep_detectado, dtype=str, error_bad_lines=False)
        
        # 4. Normalizar nomes das colunas
        df.columns = [str(c).strip().upper() for c in df.columns]

        # 5. Identificar colunas dinamicamente
        col_nome = None
        for col in df.columns:
            if 'NOME' in col: col_nome = col; break
        
        col_valor = None
        for col in df.columns:
            if 'VALOR' in col: col_valor = col; break

        if col_nome and col_valor:
            df['OS_Caixa'] = df[col_nome].apply(extrair_os_do_nome)
            df['Valor_Caixa'] = df[col_valor].apply(limpar_valor)
            df['Arquivo_Caixa'] = uploaded_file.name
            
            # Remove linhas onde Valor é NaN (linhas vazias)
            df = df.dropna(subset=['Valor_Caixa'])
            
            return df[['OS_Caixa', col_nome, 'Valor_Caixa', 'Arquivo_Caixa']]
        else:
            return pd.DataFrame()

    except Exception as e:
        st.error(f"Erro técnico no arquivo {uploaded_file.name}: {e}")
        return pd.DataFrame()

# --- Interface Principal ---

st.title("💰 Conferência de Caixa Inteligente")

# 1. Upload dos Extratos (Base de Dados)
st.header("1. Base de Dados (Extratos da Quinzena)")
files_extratos = st.file_uploader("Upload dos CSVs de Extrato (Áreas)", accept_multiple_files=True, key="extratos")

df_base = pd.DataFrame()

if files_extratos:
    lista_ext = []
    for f in files_extratos:
        df_temp = processar_extrato(f)
        if not df_temp.empty:
            lista_ext.append(df_temp)
    
    if lista_ext:
        df_base = pd.concat(lista_ext, ignore_index=True)
        df_base['OS'] = df_base['OS'].str.strip()
        
        st.success(f"Base carregada: {len(df_base)} registros.")
        with st.expander("Ver Base de Dados Completa"):
            st.dataframe(df_base)

# 2. Upload do Caixa
st.header("2. Arquivos do Caixa (Isis, Nathy, etc.)")
files_caixa = st.file_uploader("Upload dos CSVs de Caixa", accept_multiple_files=True, key="caixa")

if files_caixa and not df_base.empty:
    lista_cx = []
    for f in files_caixa:
        df_proc = processar_caixa(f)
        if not df_proc.empty:
            lista_cx.append(df_proc)
    
    if lista_cx:
        df_caixa = pd.concat(lista_cx, ignore_index=True)
        df_caixa['OS_Caixa'] = df_caixa['OS_Caixa'].str.strip()
        
        st.divider()
        st.subheader("📊 Resultado da Conferência")

        # --- Cruzamento ---
        df_final = pd.merge(
            df_caixa, 
            df_base, 
            left_on='OS_Caixa', 
            right_on='OS', 
            how='left', 
            indicator=True 
        )

        # Filtros
        duplicados = df_final[df_final.duplicated(subset=['OS_Caixa', 'Arquivo_Caixa'], keep=False)].sort_values('OS_Caixa')
        
        match_ok = df_final[
            (df_final['_merge'] == 'both') & 
            (abs(df_final['Valor_Caixa'] - df_final['Valor_Extrato']) < 0.05)
        ]
        
        divergentes = df_final[
            (df_final['_merge'] == 'both') & 
            (abs(df_final['Valor_Caixa'] - df_final['Valor_Extrato']) >= 0.05)
        ]
        
        nao_encontrados = df_final[df_final['_merge'] == 'left_only']

        # --- Abas ---
        tab1, tab2, tab3, tab4 = st.tabs(["✅ Bateu (OK)", "⚠️ Divergência de Valor", "❌ Não Achado na Base", "👀 Duplicados"])
        
        with tab1:
            st.metric("Total OK", len(match_ok))
            st.dataframe(match_ok[['OS_Caixa', 'Nome', 'Area', 'Valor_Caixa']])
            
        with tab2:
            st.error(f"{len(divergentes)} registros com diferença > 5 centavos")
            if not divergentes.empty:
                view_div = divergentes[['OS_Caixa', 'Nome', 'Area', 'Valor_Caixa', 'Valor_Extrato', 'Arquivo_Caixa']].copy()
                view_div['Diferença'] = view_div['Valor_Caixa'] - view_div['Valor_Extrato']
                st.dataframe(view_div.style.format({'Valor_Caixa': '{:.2f}', 'Valor_Extrato': '{:.2f}', 'Diferença': '{:.2f}'}))
        
        with tab3:
            st.warning(f"{len(nao_encontrados)} registros sem correspondência.")
            st.dataframe(nao_encontrados[['OS_Caixa', 'Arquivo_Caixa', 'Valor_Caixa']])
            
        with tab4:
            if not duplicados.empty:
                st.write("Registros duplicados no caixa:")
                st.dataframe(duplicados[['OS_Caixa', 'Arquivo_Caixa', 'Valor_Caixa']])
            else:
                st.success("Sem duplicidades.")

elif files_caixa and df_base.empty:
    st.warning("⚠️ Carregue os Extratos (Passo 1) primeiro!")
