import streamlit as st
import pandas as pd
from io import BytesIO

# Configuração da página
st.set_page_config(page_title="Conferência de Caixas", layout="wide", page_icon="📦")

st.title("📦 Sistema de Conferência de Caixas")
st.markdown("""
Esta ferramenta unifica seus relatórios de faturamento (CSV).
**Instruções:** Arraste todos os arquivos (Medself, Bradesco, Clube, Toxicologico, etc.) para a área abaixo.
""")

# --- FUNÇÕES AUXILIARES ---

def clean_currency(x):
    """Converte valores como '1.234,56' para float 1234.56"""
    if isinstance(x, str):
        # Remove pontos de milhar e troca vírgula decimal por ponto
        return float(x.replace('.', '').replace(',', '.'))
    return x

def load_standard_format(file):
    """Lê o formato padrão (Medself, Bradesco, etc.) que tem cabeçalho na linha 11"""
    try:
        # Pula as 10 primeiras linhas de metadados
        df = pd.read_csv(file, sep=';', skiprows=10, encoding='latin1', on_bad_lines='skip')
        
        # Limpeza básica
        # Remove colunas vazias (muitas vezes geradas por ;; no CSV)
        df = df.dropna(how='all', axis=1)
        
        # Remove linhas de "Sub-total" ou linhas vazias
        if 'Data' in df.columns:
            df = df[df['Data'] != 'Sub-total']
            df = df.dropna(subset=['Data'])
        
        # Converte coluna Valor para números
        if 'Valor' in df.columns:
            df['Valor'] = df['Valor'].apply(clean_currency)
            
        return df
    except Exception as e:
        st.error(f"Erro ao processar {file.name}: {e}")
        return None

def load_external_format(file):
    """Lê o formato 'Externa' que começa na primeira linha"""
    try:
        df = pd.read_csv(file, sep=';', encoding='latin1')
        return df
    except Exception as e:
        return None

# --- INTERFACE PRINCIPAL ---

uploaded_files = st.file_uploader(
    "Arraste seus arquivos CSV aqui", 
    accept_multiple_files=True, 
    type=['csv', 'txt']
)

if uploaded_files:
    st.success(f"{len(uploaded_files)} arquivos recebidos.")
    
    dataframes_padrao = []
    dataframes_externa = []
    
    # Processamento dos arquivos
    progress_bar = st.progress(0)
    
    for i, file in enumerate(uploaded_files):
        # Reinicia o ponteiro do arquivo para leitura
        file.seek(0)
        first_line = file.readline().decode('latin1')
        file.seek(0)
        
        # Identifica o tipo de arquivo pelo cabeçalho
        if "Visualizar por" in first_line:
            # É o arquivo tipo "Externa"
            df = load_external_format(file)
            if df is not None:
                df['Arquivo_Origem'] = file.name
                dataframes_externa.append(df)
        else:
            # É o arquivo tipo "Padrão" (Medself, etc)
            df = load_standard_format(file)
            if df is not None:
                df['Arquivo_Origem'] = file.name
                dataframes_padrao.append(df)
        
        progress_bar.progress((i + 1) / len(uploaded_files))
    
    st.divider()

    # --- ABA 1: TABELA PRINCIPAL (PADRÃO) ---
    if dataframes_padrao:
        df_consolidado = pd.concat(dataframes_padrao, ignore_index=True)
        
        # Conversão de Data
        if 'Data' in df_consolidado.columns:
            df_consolidado['Data'] = pd.to_datetime(df_consolidado['Data'], format='%d/%m/%Y', errors='coerce')
        
        st.subheader("📊 Base Consolidada (Medself, Bradesco, Clube, etc.)")
        
        # Métricas de Resumo
        col1, col2, col3 = st.columns(3)
        total_valor = df_consolidado['Valor'].sum() if 'Valor' in df_consolidado.columns else 0
        col1.metric("Faturamento Total", f"R$ {total_valor:,.2f}")
        col2.metric("Total de Exames", df_consolidado.shape[0])
        col3.metric("Arquivos Processados", len(dataframes_padrao))
        
        # Tabela Interativa
        st.dataframe(df_consolidado, use_container_width=True)
        
        # Botão Download
        csv = df_consolidado.to_csv(index=False, sep=';', decimal=',').encode('latin1')
        st.download_button(
            "📥 Baixar Tabela Consolidada (Excel/CSV)",
            data=csv,
            file_name="conferencia_consolidada.csv",
            mime="text/csv"
        )
    
    # --- ABA 2: ARQUIVOS EXTERNA (SE HOUVER) ---
    if dataframes_externa:
        st.subheader("⚠️ Arquivos de Coleta Externa")
        st.info("Estes arquivos têm um formato diferente e foram separados abaixo.")
        df_ext = pd.concat(dataframes_externa, ignore_index=True)
        st.dataframe(df_ext, use_container_width=True)

else:
    st.info("Aguardando arquivos...")
