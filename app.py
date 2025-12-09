import streamlit as st
import pandas as pd
import io
import re

# --- Configuração da Página ---
st.set_page_config(page_title="Conferência de Caixa", layout="wide")

# --- Funções Auxiliares ---

def limpar_valor(valor_str):
    """Converte string de dinheiro (R$ 1.250,00 ou 1.250,00) para float (1250.00)"""
    if pd.isna(valor_str): return 0.0
    val = str(valor_str).strip()
    val = val.replace('R$', '').strip()
    # Se tiver ponto como milhar e virgula como decimal
    if ',' in val and '.' in val:
        val = val.replace('.', '').replace(',', '.')
    # Se tiver apenas virgula
    elif ',' in val:
        val = val.replace(',', '.')
    # Se for "1250.00" direto, deixa quieto
    return pd.to_numeric(val, errors='coerce')

def extrair_os_do_nome(texto):
    """
    Tenta extrair o código da OS do começo do nome.
    Ex: '001-67494-55 ANA JULIA...' -> Retorna '001-67494-55'
    Ex: '001-67494-20 - PEDRO...'  -> Retorna '001-67494-20'
    """
    texto = str(texto).strip()
    # Pega a sequência de números e traços no início da string
    match = re.search(r'^([\d-]+)', texto)
    if match:
        return match.group(1).strip() # Retorna só a OS
    return texto # Se não achar padrão, devolve o texto original

def processar_extrato(uploaded_file):
    """Lê arquivos da Quinzena (Fonte de Dados/Convênio)"""
    try:
        # Decodifica para texto
        content = uploaded_file.getvalue().decode("latin1")
        stringio = io.StringIO(content)
        linhas = stringio.readlines()

        area_nome = "Desconhecido"
        # Tenta pegar a área na B9 (linha 8)
        if len(linhas) > 8:
            partes = linhas[8].split(';')
            if len(partes) > 1:
                area_nome = partes[1].strip()

        # Acha onde começa a tabela (procura "Data;Nome" ou "Cod O.S.")
        linha_cabecalho = 0
        for i, linha in enumerate(linhas):
            if "Data;Nome" in linha or "Cod O.S." in linha:
                linha_cabecalho = i
                break
        
        # Volta ao inicio e lê pulando as linhas desnecessárias
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file, sep=';', skiprows=linha_cabecalho, encoding='latin1', dtype=str)

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
    """Lê arquivos do Caixa (Isis, Ivone, etc)"""
    try:
        # 1. Decodificação Robusta (Lê o arquivo como texto primeiro)
        bytes_data = uploaded_file.getvalue()
        try:
            content = bytes_data.decode("utf-8", errors='replace')
        except:
            content = bytes_data.decode("latin1", errors='replace')
            
        stringio = io.StringIO(content)
        linhas = stringio.readlines()
        
        # 2. Encontrar onde começa o cabeçalho (DATA, NOME, VALOR...)
        # Isso evita ler "VALOR DE INICIO" como se fosse coluna
        linha_cabecalho = 0
        sep_detectado = ',' 
        
        for i, linha in enumerate(linhas):
            linha_upper = linha.upper()
            if "DATA" in linha_upper and "VALOR" in linha_upper:
                linha_cabecalho = i
                # Verifica separador nessa linha
                if ';' in linha: sep_detectado = ';'
                break
        
        # 3. Ler o CSV a partir da linha correta
        stringio.seek(0) # Volta pro inicio do texto
        df = pd.read_csv(
            stringio, 
            sep=sep_detectado, 
            skiprows=linha_cabecalho, 
            dtype=str
        )
        
        # 4. Normalizar nomes das colunas (remover espaços extras e maiusculas)
        df.columns = [c.strip().upper() for c in df.columns]

        # 5. Identificar coluna de Nome e Valor dinamicamente
        col_nome = None
        for col in df.columns:
            if 'NOME' in col: # Pega "NOME", "OS - NOME", "OS-NOME"
                col_nome = col
                break
        
        col_valor = None
        for col in df.columns:
            if 'VALOR' in col:
                col_valor = col
                break

        if col_nome and col_valor:
            # Separa a OS do Nome (Ex: "001-67494-55 ANA..." -> "001-67494-55")
            df['OS_Caixa'] = df[col_nome].apply(extrair_os_do_nome)
            df['Valor_Caixa'] = df[col_valor].apply(limpar_valor)
            df['Arquivo_Caixa'] = uploaded_file.name
            
            # Remove linhas vazias (onde não tem valor)
            df = df.dropna(subset=['Valor_Caixa'])
            
            return df[['OS_Caixa', col_nome, 'Valor_Caixa', 'Arquivo_Caixa']]
        else:
            st.warning(f"Não achei colunas NOME/VALOR no arquivo {uploaded_file.name}. Colunas achadas: {df.columns.tolist()}")
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
        lista_ext.append(processar_extrato(f))
    
    if lista_ext:
        df_base = pd.concat(lista_ext, ignore_index=True)
        # Limpar espaços em branco na OS para garantir o match
        df_base['OS'] = df_base['OS'].str.strip()
        
        st.success(f"Base carregada: {len(df_base)} registros de {len(files_extratos)} áreas.")
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

        # --- Lógica de Cruzamento ---
        # Juntamos o Caixa (Left) com a Base (Right) usando a OS
        df_final = pd.merge(
            df_caixa, 
            df_base, 
            left_on='OS_Caixa', 
            right_on='OS', 
            how='left', 
            indicator=True 
        )

        # Filtros de Análise
        
        # 1. Duplicados no Caixa (Mesma OS cobrada 2x?)
        duplicados = df_final[df_final.duplicated(subset=['OS_Caixa', 'Arquivo_Caixa'], keep=False)].sort_values('OS_Caixa')
        
        # 2. Encontrados e Valores Batem (com tolerância de 2 centavos)
        match_ok = df_final[
            (df_final['_merge'] == 'both') & 
            (abs(df_final['Valor_Caixa'] - df_final['Valor_Extrato']) < 0.02)
        ]
        
        # 3. Encontrados mas Valores DIFERENTES
        divergentes = df_final[
            (df_final['_merge'] == 'both') & 
            (abs(df_final['Valor_Caixa'] - df_final['Valor_Extrato']) >= 0.02)
        ]
        
        # 4. Não encontrados na Base
        nao_encontrados = df_final[df_final['_merge'] == 'left_only']

        # --- Exibição ---
        
        tab1, tab2, tab3, tab4 = st.tabs(["✅ Bateu (OK)", "⚠️ Divergência de Valor", "❌ Não Achado na Base", "👀 Duplicados"])
        
        with tab1:
            st.metric("Total OK", len(match_ok))
            st.dataframe(match_ok[['OS_Caixa', 'Nome', 'Area', 'Valor_Caixa']])
            
        with tab2:
            st.error(f"{len(divergentes)} registros com valor diferente!")
            if not divergentes.empty:
                view_div = divergentes[['OS_Caixa', 'Nome', 'Area', 'Valor_Caixa', 'Valor_Extrato', 'Arquivo_Caixa']].copy()
                view_div['Diferença'] = view_div['Valor_Caixa'] - view_div['Valor_Extrato']
                st.dataframe(view_div.style.format({'Valor_Caixa': '{:.2f}', 'Valor_Extrato': '{:.2f}', 'Diferença': '{:.2f}'}))
        
        with tab3:
            st.warning(f"{len(nao_encontrados)} registros no caixa sem correspondência nos extratos.")
            st.dataframe(nao_encontrados[['OS_Caixa', 'Arquivo_Caixa', 'Valor_Caixa']])
            
        with tab4:
            if not duplicados.empty:
                st.write("Atenção: Mesma OS lançada mais de uma vez:")
                st.dataframe(duplicados[['OS_Caixa', 'Arquivo_Caixa', 'Valor_Caixa']])
            else:
                st.success("Sem duplicidades.")

elif files_caixa and df_base.empty:
    st.warning("⚠️ Carregue os Extratos (Passo 1) primeiro!")
