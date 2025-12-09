import streamlit as st
import pandas as pd
import re
from io import BytesIO

# Configuração da página
st.set_page_config(page_title="Conferência Financeira", layout="wide", page_icon="💰")

# --- CSS para melhorar a visualização ---
st.markdown("""
<style>
    .metric-card {background-color: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #4CAF50;}
    .warning-card {background-color: #fff3cd; padding: 15px; border-radius: 10px; border-left: 5px solid #ffc107;}
    .error-card {background-color: #f8d7da; padding: 15px; border-radius: 10px; border-left: 5px solid #dc3545;}
</style>
""", unsafe_allow_html=True)

# --- INICIALIZAÇÃO DO SESSION STATE ---
# Isso garante que os dados fiquem salvos ao trocar de aba
if 'df_base_unificada' not in st.session_state:
    st.session_state['df_base_unificada'] = None
if 'df_caixa_unificado' not in st.session_state:
    st.session_state['df_caixa_unificado'] = None

# --- FUNÇÕES AUXILIARES ---

def clean_currency(x):
    """Converte '1.234,56' para float 1234.56"""
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        clean = x.replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
        try:
            return float(clean)
        except:
            return 0.0
    return 0.0

def extract_os_code(text):
    """Procura padrões como 001-67358-42 dentro de um texto"""
    if not isinstance(text, str):
        return None
    # Regex para capturar padrões comuns de OS (ex: 001-12345-12 ou 005-...)
    match = re.search(r'(\d{3}-\d+-\d+)', text)
    if match:
        return match.group(1).strip()
    return None

def process_base_files(uploaded_files):
    dataframes = []
    for file in uploaded_files:
        try:
            # Tenta ler pulando 10 linhas (padrão)
            file.seek(0)
            df = pd.read_csv(file, sep=';', skiprows=10, encoding='latin1', on_bad_lines='skip')
            
            # Se não tiver coluna 'Data', tenta ler sem pular (Formato Externa)
            if 'Data' not in df.columns:
                file.seek(0)
                df = pd.read_csv(file, sep=';', encoding='latin1', on_bad_lines='skip')
            
            # Padronização básica
            if 'Cod O.S.' in df.columns: # Arquivos padrão
                df['OS_Formatada'] = df['Cod O.S.'].astype(str).str.strip()
            elif 'Detalhado' in df.columns: # Arquivo Externa
                df['OS_Formatada'] = df['Detalhado'].astype(str).str.strip()
                df['Valor'] = df['Lqd. Balc.'] # Ajuste para pegar valor correto
            
            if 'Valor' in df.columns:
                df['Valor'] = df['Valor'].apply(clean_currency)
                df = df[df['Valor'] > 0] # Remove zerados
                
            df['Arquivo_Origem'] = file.name
            dataframes.append(df)
        except Exception as e:
            st.error(f"Erro no arquivo {file.name}: {e}")
            
    if dataframes:
        return pd.concat(dataframes, ignore_index=True)
    return None

def process_caixa_files(uploaded_files):
    dataframes = []
    for file in uploaded_files:
        try:
            # Estratégia: Ler o arquivo e procurar onde começa o cabeçalho "DATA"
            file.seek(0)
            content = file.read().decode('latin1', errors='ignore')
            lines = content.splitlines()
            
            header_row = 0
            found_header = False
            for i, line in enumerate(lines):
                if 'DATA' in line.upper() and ('VALOR' in line.upper() or 'VLR' in line.upper()):
                    header_row = i
                    found_header = True
                    break
            
            if found_header:
                file.seek(0)
                # Lê usando o delimitador detectado (usualmente vírgula ou ponto e vírgula)
                sep = ';' if ';' in lines[header_row] else ','
                df = pd.read_csv(file, sep=sep, skiprows=header_row, encoding='latin1', on_bad_lines='skip')
                
                # Normalizar nomes das colunas (remover espaços, maiusculas)
                df.columns = [c.upper().strip() for c in df.columns]
                
                # Procura coluna de descrição/nome
                col_nome = next((c for c in df.columns if 'NOME' in c or 'DESCRICAO' in c), None)
                col_valor = next((c for c in df.columns if 'VALOR' in c), None)
                
                if col_nome and col_valor:
                    # Extrai a OS do texto
                    df['OS_Extraida'] = df[col_nome].apply(extract_os_code)
                    df['Valor_Caixa'] = df[col_valor].apply(clean_currency)
                    df['Caixa_Origem'] = file.name
                    
                    # Filtra apenas linhas que conseguimos identificar uma OS (para comparar com exames)
                    # O resto é despesa ou receita diversa
                    df_validos = df.dropna(subset=['OS_Extraida']).copy()
                    dataframes.append(df_validos)
        except Exception as e:
            st.error(f"Erro ao ler caixa {file.name}: {e}")
            
    if dataframes:
        return pd.concat(dataframes, ignore_index=True)
    return None

# --- INTERFACE ---

st.title("📊 Sistema Integrado de Conferência")

tab1, tab2, tab3 = st.tabs(["1. Upload das Bases", "2. Upload dos Caixas", "3. Relatório de Conferência"])

# --- ABA 1: BASES ---
with tab1:
    st.header("Passo 1: Carregar Bases (Medself, Bradesco, etc)")
    files_base = st.file_uploader("Arraste os arquivos das BASES aqui", accept_multiple_files=True, key="base_uploader")
    
    if files_base:
        if st.button("Processar Bases"):
            with st.spinner("Unificando bases..."):
                df_base = process_base_files(files_base)
                if df_base is not None:
                    st.session_state['df_base_unificada'] = df_base
                    st.success(f"Base unificada com sucesso! {len(df_base)} registros encontrados.")
                else:
                    st.error("Não foi possível processar as bases.")

    # Mostra preview se existir dados na memória
    if st.session_state['df_base_unificada'] is not None:
        st.dataframe(st.session_state['df_base_unificada'].head(), use_container_width=True)
        st.info("Bases carregadas. Pode ir para a próxima aba.")

# --- ABA 2: CAIXAS ---
with tab2:
    st.header("Passo 2: Carregar Caixas (Isis, Ivone, etc)")
    files_caixa = st.file_uploader("Arraste os arquivos dos CAIXAS aqui", accept_multiple_files=True, key="caixa_uploader")
    
    if files_caixa:
        if st.button("Processar Caixas"):
            with st.spinner("Lendo caixas e extraindo códigos de O.S..."):
                df_caixa = process_caixa_files(files_caixa)
                if df_caixa is not None:
                    st.session_state['df_caixa_unificado'] = df_caixa
                    st.success(f"Caixas processados! {len(df_caixa)} exames identificados nos caixas.")
                else:
                    st.error("Não foi possível ler os caixas.")
    
    if st.session_state['df_caixa_unificado'] is not None:
        st.dataframe(st.session_state['df_caixa_unificado'].head(), use_container_width=True)

# --- ABA 3: CONFERÊNCIA ---
with tab3:
    st.header("Passo 3: Cruzamento de Dados")
    
    if st.session_state['df_base_unificada'] is None or st.session_state['df_caixa_unificado'] is None:
        st.warning("⚠️ Você precisa carregar as BASES na Aba 1 e os CAIXAS na Aba 2 primeiro.")
    else:
        # Preparação para o Merge
        df_b = st.session_state['df_base_unificada'].copy()
        df_c = st.session_state['df_caixa_unificado'].copy()
        
        # Agrupar Bases por OS (caso tenha exames quebrados na mesma OS, somamos o valor)
        # Ajuste: Garantir que 'OS_Formatada' e 'Valor' existam
        if 'OS_Formatada' in df_b.columns and 'Valor' in df_b.columns:
            base_agg = df_b.groupby('OS_Formatada').agg({
                'Valor': 'sum',
                'Nome': 'first',
                'Arquivo_Origem': 'first',
                'Data': 'first'
            }).reset_index().rename(columns={'Valor': 'Valor_Base'})
        
        # Agrupar Caixas por OS
        caixa_agg = df_c.groupby('OS_Extraida').agg({
            'Valor_Caixa': 'sum',
            'Caixa_Origem': 'first'
        }).reset_index().rename(columns={'OS_Extraida': 'OS_Formatada'})
        
        # CRUZAMENTO (Full Outer Join para pegar tudo de ambos)
        conferencia = pd.merge(base_agg, caixa_agg, on='OS_Formatada', how='outer')
        
        # Preencher vazios com 0
        conferencia['Valor_Base'] = conferencia['Valor_Base'].fillna(0)
        conferencia['Valor_Caixa'] = conferencia['Valor_Caixa'].fillna(0)
        
        # Cálculo da Diferença
        conferencia['Diferenca'] = conferencia['Valor_Caixa'] - conferencia['Valor_Base']
        
        # Definir Status
        def definir_status(row):
            diff = round(row['Diferenca'], 2)
            if row['Valor_Base'] == 0:
                return "SOBRA NO CAIXA (Não está na Base)"
            elif row['Valor_Caixa'] == 0:
                return "FALTA NO CAIXA (Está na Base mas não no Caixa)"
            elif diff == 0:
                return "OK"
            elif diff > 0:
                return f"DIVERGÊNCIA: Caixa Maior (+{diff})"
            else:
                return f"DIVERGÊNCIA: Caixa Menor ({diff})"

        conferencia['Status'] = conferencia.apply(definir_status, axis=1)
        
        # --- EXIBIÇÃO DOS RESULTADOS ---
        
        # Métricas
        col1, col2, col3, col4 = st.columns(4)
        total_ok = len(conferencia[conferencia['Status'] == 'OK'])
        total_falta = len(conferencia[conferencia['Status'].str.contains("FALTA")])
        total_sobra = len(conferencia[conferencia['Status'].str.contains("SOBRA")])
        total_div = len(conferencia[conferencia['Status'].str.contains("DIVERGÊNCIA")])
        
        col1.metric("✅ Conferidos (OK)", total_ok)
        col2.metric("❌ Faltam no Caixa", total_falta)
        col3.metric("⚠️ Sobras no Caixa", total_sobra)
        col4.metric("📉 Valores Diferentes", total_div)
        
        st.divider()
        
        # Filtros
        filtro_status = st.multiselect(
            "Filtrar por Status:", 
            options=conferencia['Status'].unique(),
            default=[s for s in conferencia['Status'].unique() if s != "OK"]
        )
        
        if filtro_status:
            df_view = conferencia[conferencia['Status'].isin(filtro_status)]
        else:
            df_view = conferencia
            
        st.dataframe(
            df_view.style.format({"Valor_Base": "R$ {:.2f}", "Valor_Caixa": "R$ {:.2f}", "Diferenca": "R$ {:.2f}"})
                   .applymap(lambda x: "background-color: #ffcccc" if "FALTA" in str(x) or "Menor" in str(x) else ("background-color: #ccffcc" if "OK" in str(x) else ""), subset=['Status']),
            use_container_width=True
        )
        
        # Download
        csv = conferencia.to_csv(index=False, sep=';', decimal=',').encode('latin1')
        st.download_button(
            "📥 Baixar Relatório Completo",
            data=csv,
            file_name="relatorio_conferencia_caixas.csv",
            mime="text/csv"
        )
