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
    """Tenta extrair o código da OS do começo do nome (ex: '001-67494-55 ANA...')"""
    texto = str(texto).strip()
    # Pega a primeira 'palavra' que parece um código (números e traços)
    match = re.search(r'^([\d-]+)', texto)
    if match:
        return match.group(1)
    return texto # Se não achar padrão, devolve o texto original para conferência manual

def processar_extrato(uploaded_file):
    """Lê arquivos da Quinzena (Fonte de Dados/Convênio)"""
    try:
        content = uploaded_file.getvalue().decode("latin1")
        stringio = io.StringIO(content)
        linhas = stringio.readlines()

        area_nome = "Desconhecido"
        if len(linhas) > 8:
            partes = linhas[8].split(';')
            if len(partes) > 1:
                area_nome = partes[1].strip()

        # Acha cabeçalho
        linha_cabecalho = 10
        for i, linha in enumerate(linhas):
            if linha.startswith("Data;Nome") or "Cod O.S." in linha:
                linha_cabecalho = i
                break
        
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file, sep=';', skiprows=linha_cabecalho, encoding='latin1', dtype=str)

        # Limpeza
        if 'Data' in df.columns:
            df = df.dropna(subset=['Data'])
            df = df[df['Data'] != 'Sub-total']
            df['Area'] = area_nome
            
            # Normalizar Coluna de OS
            # O arquivo tem 'Cod O.S.', vamos padronizar para 'OS'
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
        # Detectar separador (alguns csvs usam , outros ;)
        content = uploaded_file.getvalue().decode("utf-8", errors='replace') # Tenta utf-8, fallback replace
        sep = ',' if ',' in content.split('\n')[0] else ';'
        
        uploaded_file.seek(0)
        df = pd.read_csv(uploaded_file, sep=sep, encoding='utf-8', errors='replace', dtype=str)
        
        # Identificar coluna de Nome/OS
        # Variações: "NOME", "OS - NOME", "OS-NOME"
        col_nome = None
        for col in df.columns:
            if 'NOME' in col.upper():
                col_nome = col
                break
        
        # Identificar coluna Valor
        col_valor = None
        for col in df.columns:
            if 'VALOR' in col.upper():
                col_valor = col
                break

        if col_nome and col_valor:
            df['OS_Caixa'] = df[col_nome].apply(extrair_os_do_nome)
            df['Valor_Caixa'] = df[col_valor].apply(limpar_valor)
            df['Arquivo_Caixa'] = uploaded_file.name
            
            # Remove linhas sem valor (ex: cabeçalhos intermediários)
            df = df.dropna(subset=['Valor_Caixa'])
            
            return df[['OS_Caixa', col_nome, 'Valor_Caixa', 'Arquivo_Caixa']]
        else:
            st.warning(f"Colunas não identificadas no arquivo {uploaded_file.name}")
            return pd.DataFrame()

    except Exception as e:
        st.error(f"Erro no caixa {uploaded_file.name}: {e}")
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
        
        st.info(f"Base carregada: {len(df_base)} registros encontrados em {len(files_extratos)} arquivos.")
        with st.expander("Ver Base de Dados Completa"):
            st.dataframe(df_base)

# 2. Upload do Caixa
st.header("2. Arquivos do Caixa (Isis, Nathy, etc.)")
files_caixa = st.file_uploader("Upload dos CSVs de Caixa", accept_multiple_files=True, key="caixa")

if files_caixa and not df_base.empty:
    lista_cx = []
    for f in files_caixa:
        lista_cx.append(processar_caixa(f))
    
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
            indicator=True # Cria coluna '_merge' para saber se achou ou não
        )

        # Análises
        
        # 1. Duplicados no Caixa (Mesma OS cobrada 2x?)
        duplicados = df_final[df_final.duplicated(subset=['OS_Caixa'], keep=False)].sort_values('OS_Caixa')
        
        # 2. Encontrados e Valores Batem
        # Tolerância pequena para erros de arredondamento (0.01 centavo)
        match_ok = df_final[
            (df_final['_merge'] == 'both') & 
            (abs(df_final['Valor_Caixa'] - df_final['Valor_Extrato']) < 0.02)
        ]
        
        # 3. Encontrados mas Valores DIFERENTES
        divergentes = df_final[
            (df_final['_merge'] == 'both') & 
            (abs(df_final['Valor_Caixa'] - df_final['Valor_Extrato']) >= 0.02)
        ]
        
        # 4. Não encontrados na Base (OS existe no caixa, mas não nos extratos)
        nao_encontrados = df_final[df_final['_merge'] == 'left_only']

        # --- Exibição dos Resultados ---
        
        tab1, tab2, tab3, tab4 = st.tabs(["✅ Bateu (OK)", "⚠️ Valores Diferentes", "❌ Não encontrado na Base", "👀 Duplicados"])
        
        with tab1:
            st.metric("Quantidade OK", len(match_ok))
            st.dataframe(match_ok[['OS_Caixa', 'Nome', 'Area', 'Valor_Caixa']])
            
        with tab2:
            st.error(f"Atenção: {len(divergentes)} registros com diferença de valor!")
            if not divergentes.empty:
                # Mostrar comparativo
                view_div = divergentes[['OS_Caixa', 'Nome', 'Area', 'Valor_Caixa', 'Valor_Extrato']]
                view_div['Diferença'] = view_div['Valor_Caixa'] - view_div['Valor_Extrato']
                st.dataframe(view_div.style.format({'Valor_Caixa': '{:.2f}', 'Valor_Extrato': '{:.2f}', 'Diferença': '{:.2f}'}))
        
        with tab3:
            st.warning(f"{len(nao_encontrados)} registros não achados nos extratos importados.")
            st.write("Verifique se o paciente é particular ou de convênio não importado.")
            st.dataframe(nao_encontrados[['OS_Caixa', 'Arquivo_Caixa', 'Valor_Caixa']])
            
        with tab4:
            if not duplicados.empty:
                st.write("Estas OS aparecem mais de uma vez no caixa:")
                st.dataframe(duplicados)
            else:
                st.success("Nenhuma duplicidade encontrada no caixa.")

elif files_caixa and df_base.empty:
    st.warning("Por favor, faça o upload dos Extratos (Passo 1) antes de conferir o caixa.")
