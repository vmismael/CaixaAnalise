import streamlit as st
import pandas as pd
import re
from io import BytesIO

# Configuração da página
st.set_page_config(page_title="Conferência Financeira", layout="wide", page_icon="💰")

# --- CSS ---
st.markdown("""
<style>
    .metric-card {background-color: #f0f2f6; padding: 15px; border-radius: 10px; border-left: 5px solid #4CAF50;}
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #f0f2f6; border-radius: 4px; color: #31333F; }
    .stTabs [aria-selected="true"] { background-color: #e6ffe6; border-bottom: 2px solid #4CAF50; }
</style>
""", unsafe_allow_html=True)

# --- SESSION STATE ---
if 'df_base_unificada' not in st.session_state:
    st.session_state['df_base_unificada'] = None
if 'df_caixa_unificado' not in st.session_state:
    st.session_state['df_caixa_unificado'] = None

# --- FUNÇÕES AUXILIARES ---

def clean_currency(x):
    """Limpa valores monetários de R$ 1.234,56 ou 1,234.56 para float"""
    if pd.isna(x) or str(x).strip() == '':
        return 0.0
    
    clean = str(x).replace('R$', '').replace(' ', '').strip()
    
    try:
        # Se for um número que já parece float (ex: 125.50)
        if clean.replace('.', '', 1).isdigit():
            return float(clean)
            
        # Padrão brasileiro (ponto milhar, virgula decimal)
        if ',' in clean and '.' in clean:
            clean = clean.replace('.', '').replace(',', '.')
        # Apenas vírgula (comum no excel BR)
        elif ',' in clean:
            clean = clean.replace(',', '.')
            
        return float(clean)
    except:
        return 0.0

def extract_os_code(text):
    """Extrai código da OS (ex: 001-67358-42)"""
    if not isinstance(text, str):
        return None
    match = re.search(r'(\d{3}\s*-\s*\d+\s*-\s*\d+)', text)
    if match:
        return match.group(1).replace(' ', '').strip()
    return None

# --- LÓGICA DE LEITURA (CSV e EXCEL) ---

def read_file_content(file):
    """Lê o arquivo e retorna um DataFrame bruto, seja Excel ou CSV"""
    file.seek(0)
    if file.name.endswith(('.xls', '.xlsx')):
        try:
            # Lê Excel sem cabeçalho para podermos procurar a linha certa depois
            return pd.read_excel(file, header=None)
        except Exception as e:
            st.error(f"Erro ao ler Excel {file.name}: {e}")
            return None
    else:
        # Lógica para CSV (detecta separador e ignora linhas ruins)
        try:
            content = file.read()
            try:
                text = content.decode('latin1')
            except:
                text = content.decode('utf-8', errors='ignore')
            
            file.seek(0)
            # Detecta separador grosseiro
            sep = ';' if text.count(';') > text.count(',') else ','
            
            # Lê CSV genérico sem cabeçalho
            return pd.read_csv(file, sep=sep, header=None, on_bad_lines='skip', engine='python')
        except Exception as e:
            st.error(f"Erro ao ler CSV {file.name}: {e}")
            return None

def find_header_and_data(df_raw):
    """Recebe um DF bruto e procura onde começam os dados reais"""
    if df_raw is None or df_raw.empty:
        return None

    header_idx = -1
    
    # Procura linha que tenha DATA e VALOR
    for i, row in df_raw.head(50).iterrows():
        # Converte linha para string única maiúscula para busca
        row_str = " ".join(row.astype(str)).upper()
        if 'DATA' in row_str and ('VALOR' in row_str or 'VLR' in row_str or 'PAGTO' in row_str):
            header_idx = i
            break
    
    if header_idx != -1:
        # Define a linha encontrada como cabeçalho
        df_raw.columns = df_raw.iloc[header_idx].astype(str).str.upper().str.strip()
        # Pega os dados dali pra baixo
        df_clean = df_raw.iloc[header_idx+1:].copy()
        return df_clean
    
    return None

# --- PROCESSADORES ---

def process_base_files(uploaded_files):
    dataframes = []
    
    for file in uploaded_files:
        # 1. Lê arquivo bruto
        df_raw = read_file_content(file)
        
        # 2. Tenta achar cabeçalho automaticamente
        df = find_header_and_data(df_raw)
        
        # Fallback: Se não achou (alguns arquivos base não tem cabeçalho na linha certa ou é Externa)
        if df is None:
            # Assume que é arquivo tipo "Externa" ou padrão CSV se falhar a busca
            file.seek(0)
            if file.name.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(file)
            else:
                df = pd.read_csv(file, sep=';', encoding='latin1', on_bad_lines='skip')
                
        # Normaliza nomes de coluna
        df.columns = [str(c).strip() for c in df.columns]
        
        # 3. Mapeia Colunas
        col_os = None
        col_valor = None
        
        if 'Cod O.S.' in df.columns: col_os = 'Cod O.S.'
        elif 'Detalhado' in df.columns: col_os = 'Detalhado' # Externa
        elif 'OS' in df.columns: col_os = 'OS'
        
        if 'Valor' in df.columns: col_valor = 'Valor'
        elif 'Lqd. Balc.' in df.columns: col_valor = 'Lqd. Balc.' # Externa
        
        if col_os and col_valor:
            df['OS_Formatada'] = df[col_os].astype(str).apply(lambda x: x.strip())
            df['Valor_Base'] = df[col_valor].apply(clean_currency)
            df['Arquivo_Origem'] = file.name
            
            df_valid = df[df['Valor_Base'] > 0].copy()
            dataframes.append(df_valid[['OS_Formatada', 'Valor_Base', 'Arquivo_Origem']])
            
    if dataframes:
        return pd.concat(dataframes, ignore_index=True)
    return None

def process_caixa_files(uploaded_files):
    dataframes = []
    errors = []
    
    for file in uploaded_files:
        # 1. Lê arquivo bruto
        df_raw = read_file_content(file)
        
        # 2. Acha onde começa a tabela
        df = find_header_and_data(df_raw)
        
        if df is not None:
            # 3. Identifica Colunas
            col_nome = next((c for c in df.columns if 'NOME' in c or 'DESCRICAO' in c or 'HISTORICO' in c), None)
            col_valor = next((c for c in df.columns if 'VALOR' in c or 'VLR' in c), None)
            
            if col_nome and col_valor:
                # Remove linhas de totais
                df = df.dropna(subset=[col_nome])
                df = df[~df[col_nome].astype(str).str.upper().str.contains("TOTAL", na=False)]
                
                df['OS_Extraida'] = df[col_nome].astype(str).apply(extract_os_code)
                df['Valor_Caixa'] = df[col_valor].apply(clean_currency)
                df['Caixa_Origem'] = file.name
                df['Nome_Original'] = df[col_nome]
                
                # Salva apenas linhas com OS válida
                df_validos = df.dropna(subset=['OS_Extraida']).copy()
                
                if not df_validos.empty:
                    dataframes.append(df_validos[['OS_Extraida', 'Valor_Caixa', 'Caixa_Origem', 'Nome_Original']])
            else:
                errors.append(f"{file.name}: Colunas NOME/VALOR não encontradas.")
        else:
            errors.append(f"{file.name}: Não achei cabeçalho (DATA...VALOR).")
            
    if errors:
        with st.expander("⚠️ Arquivos ignorados", expanded=False):
            for e in errors:
                st.write(e)
            
    if dataframes:
        return pd.concat(dataframes, ignore_index=True)
    return None

# --- INTERFACE ---

st.title("📊 Conferência de Caixas Automática")

tab1, tab2, tab3 = st.tabs(["📂 1. Bases (Convênios)", "📂 2. Caixas (Funcionários)", "📝 3. Resultado"])

# --- ABA 1: BASES ---
with tab1:
    st.info("Carregue aqui os relatórios do Medself, Bradesco, Externa, etc. (CSV ou Excel)")
    # AQUI ESTAVA O ERRO: Adicionei 'xlsx' e 'xls' na lista
    files_base = st.file_uploader("Arquivos Base", accept_multiple_files=True, key="base", type=['csv','txt','xlsx','xls'])
    
    if st.button("Processar Bases"):
        if files_base:
            with st.spinner("Lendo bases..."):
                df_base = process_base_files(files_base)
                if df_base is not None:
                    st.session_state['df_base_unificada'] = df_base
                    st.success(f"✅ {len(df_base)} exames carregados da Base.")
                else:
                    st.error("Nenhum dado encontrado.")
    
    if st.session_state['df_base_unificada'] is not None:
        st.dataframe(st.session_state['df_base_unificada'].head(), use_container_width=True)

# --- ABA 2: CAIXAS ---
with tab2:
    st.info("Carregue aqui os arquivos: Caixa Adrielli, Isis, Ivone, etc. (CSV ou Excel)")
    # AQUI TAMBÉM: Adicionei 'xlsx' e 'xls'
    files_caixa = st.file_uploader("Arquivos de Caixa", accept_multiple_files=True, key="caixa", type=['csv','txt','xlsx','xls'])
    
    if st.button("Processar Caixas"):
        if files_caixa:
            with st.spinner("Processando caixas..."):
                df_caixa = process_caixa_files(files_caixa)
                if df_caixa is not None:
                    st.session_state['df_caixa_unificado'] = df_caixa
                    st.success(f"✅ {len(df_caixa)} lançamentos com OS identificados nos Caixas.")
                else:
                    st.error("Não consegui ler os caixas.")
    
    if st.session_state['df_caixa_unificado'] is not None:
        st.dataframe(st.session_state['df_caixa_unificado'].head(), use_container_width=True)

# --- ABA 3: CONFERÊNCIA ---
with tab3:
    st.header("Relatório de Divergências")
    
    if st.session_state['df_base_unificada'] is None or st.session_state['df_caixa_unificado'] is None:
        st.warning("⚠️ Carregue as BASES e os CAIXAS antes de ver o resultado.")
    else:
        df_b = st.session_state['df_base_unificada']
        df_c = st.session_state['df_caixa_unificado']
        
        # Agrupa Bases
        base_agg = df_b.groupby('OS_Formatada').agg({
            'Valor_Base': 'sum', 
            'Arquivo_Origem': 'first'
        }).reset_index()
        
        # Agrupa Caixas
        caixa_agg = df_c.groupby('OS_Extraida').agg({
            'Valor_Caixa': 'sum', 
            'Caixa_Origem': 'first', 
            'Nome_Original': 'first'
        }).reset_index().rename(columns={'OS_Extraida': 'OS_Formatada'})
        
        # Merge
        merged = pd.merge(base_agg, caixa_agg, on='OS_Formatada', how='outer')
        merged.fillna({'Valor_Base': 0, 'Valor_Caixa': 0}, inplace=True)
        merged['Diferenca'] = merged['Valor_Caixa'] - merged['Valor_Base']
        
        def get_status(row):
            diff = round(row['Diferenca'], 2)
            if row['Valor_Base'] == 0: return "SOBRA (Extra no Caixa)"
            if row['Valor_Caixa'] == 0: return "FALTA (Não lançado no Caixa)"
            if diff == 0: return "OK"
            if diff > 0: return f"DIVERGÊNCIA: Caixa Maior (+{diff})"
            return f"DIVERGÊNCIA: Caixa Menor ({diff})"

        merged['Status'] = merged.apply(get_status, axis=1)
        
        # Métricas
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("✅ Tudo Certo", len(merged[merged['Status']=='OK']))
        col2.metric("❌ Faltas", len(merged[merged['Status'].str.contains('FALTA')]))
        col3.metric("⚠️ Sobras", len(merged[merged['Status'].str.contains('SOBRA')]))
        col4.metric("📉 Divergências", len(merged[merged['Status'].str.contains('DIVERGÊNCIA')]))
        
        st.divider()
        
        opcoes = list(merged['Status'].unique())
        if 'OK' in opcoes: opcoes.remove('OK')
        filtro = st.multiselect("Filtrar Erros:", options=merged['Status'].unique(), default=opcoes)
        
        df_final = merged if not filtro else merged[merged['Status'].isin(filtro)]
        
        def highlight_vals(val):
            color = ''
            if 'FALTA' in str(val) or 'Menor' in str(val): color = '#ffcccc'
            elif 'SOBRA' in str(val): color = '#fff3cd'
            elif 'OK' in str(val): color = '#ccffcc'
            return f'background-color: {color}'

        st.dataframe(
            df_final.style.applymap(highlight_vals, subset=['Status'])
                    .format("{:.2f}", subset=['Valor_Base', 'Valor_Caixa', 'Diferenca']),
            use_container_width=True,
            height=600
        )
