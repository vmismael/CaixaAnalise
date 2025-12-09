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
    # Regex para capturar 3 digitos - digitos - digitos (ex: 001-67540-24)
    # O replace remove espaços dentro do código se houver
    match = re.search(r'(\d{3}\s*-\s*\d+\s*-\s*\d+)', text)
    if match:
        return match.group(1).replace(' ', '').strip()
    return None

# --- PROCESSAMENTO INTELIGENTE DE ARQUIVOS ---

def find_header_row(file, content_lines):
    """Encontra em qual linha está o cabeçalho DATA e VALOR"""
    for i, line in enumerate(content_lines[:200]): # Olha apenas as primeiras 200 linhas
        line_upper = line.upper()
        # Regra: Tem que ter DATA e (VALOR ou VLR ou PAGTO) na mesma linha
        if 'DATA' in line_upper and ('VALOR' in line_upper or 'VLR' in line_upper or 'PAGTO' in line_upper):
            return i
    return -1

def detect_separator(header_line):
    """Conta se tem mais vírgulas ou ponto-e-vírgulas"""
    if header_line.count(';') > header_line.count(','):
        return ';'
    return ','

def process_base_files(uploaded_files):
    dataframes = []
    
    for file in uploaded_files:
        try:
            # Tenta ler com separador ; pulando 10 linhas (Padrão Medself/Bradesco)
            file.seek(0)
            df = pd.read_csv(file, sep=';', skiprows=10, encoding='latin1', on_bad_lines='skip', engine='python')
            
            # Se a coluna Data não existir, pode ser o arquivo "Externa" que começa na linha 0
            if 'Data' not in df.columns:
                file.seek(0)
                df = pd.read_csv(file, sep=';', encoding='latin1', on_bad_lines='skip', engine='python')

            # Normalizar nomes das colunas
            df.columns = [c.strip() for c in df.columns]
            
            col_os = None
            col_valor = None
            
            # Mapeamento de colunas da Base
            if 'Cod O.S.' in df.columns: col_os = 'Cod O.S.'
            elif 'Detalhado' in df.columns: col_os = 'Detalhado' # Arquivo Externa
            
            if 'Valor' in df.columns: col_valor = 'Valor'
            elif 'Lqd. Balc.' in df.columns: col_valor = 'Lqd. Balc.' # Arquivo Externa
            
            if col_os and col_valor:
                df['OS_Formatada'] = df[col_os].astype(str).apply(lambda x: x.strip())
                df['Valor_Base'] = df[col_valor].apply(clean_currency)
                df['Arquivo_Origem'] = file.name
                
                # Filtrar linhas válidas
                df_valid = df[df['Valor_Base'] > 0].copy()
                dataframes.append(df_valid[['OS_Formatada', 'Valor_Base', 'Arquivo_Origem']])
                
        except Exception as e:
            st.error(f"Erro Base {file.name}: {e}")
            
    if dataframes:
        return pd.concat(dataframes, ignore_index=True)
    return None

def process_caixa_files(uploaded_files):
    dataframes = []
    errors = []
    
    for file in uploaded_files:
        try:
            # 1. Ler o arquivo como texto puro primeiro
            file.seek(0)
            try:
                content = file.read().decode('latin1')
            except:
                file.seek(0)
                content = file.read().decode('utf-8', errors='ignore')
                
            lines = content.splitlines()
            
            # 2. Achar onde começa a tabela
            header_idx = find_header_row(file, lines)
            
            if header_idx != -1:
                # Detectar separador
                sep = detect_separator(lines[header_idx])
                
                # 3. Ler o CSV a partir da linha correta
                file.seek(0)
                df = pd.read_csv(file, sep=sep, skiprows=header_idx, encoding='latin1', on_bad_lines='skip', engine='python')
                
                # Limpar nomes das colunas (remover espaços e deixar maiúsculo)
                df.columns = [str(c).upper().strip() for c in df.columns]
                
                # 4. Identificar Colunas Chave
                col_nome = next((c for c in df.columns if 'NOME' in c or 'DESCRICAO' in c or 'HISTORICO' in c), None)
                col_valor = next((c for c in df.columns if 'VALOR' in c or 'VLR' in c), None)
                
                if col_nome and col_valor:
                    # Remove linhas de "TOTAL" ou linhas vazias
                    df = df.dropna(subset=[col_nome])
                    df = df[~df[col_nome].astype(str).str.upper().str.contains("TOTAL", na=False)]
                    
                    df['OS_Extraida'] = df[col_nome].astype(str).apply(extract_os_code)
                    df['Valor_Caixa'] = df[col_valor].apply(clean_currency)
                    df['Caixa_Origem'] = file.name
                    df['Nome_Original'] = df[col_nome]
                    
                    # Salva apenas linhas que têm código de OS
                    df_validos = df.dropna(subset=['OS_Extraida']).copy()
                    
                    if not df_validos.empty:
                        dataframes.append(df_validos[['OS_Extraida', 'Valor_Caixa', 'Caixa_Origem', 'Nome_Original']])
                else:
                    errors.append(f"{file.name}: Colunas NOME/VALOR não encontradas na linha {header_idx}.")
            else:
                errors.append(f"{file.name}: Não encontrei cabeçalho (DATA...VALOR).")
                
        except Exception as e:
            errors.append(f"{file.name}: Erro técnico - {str(e)}")
    
    if errors:
        with st.expander("⚠️ Arquivos ignorados (Ver detalhes)", expanded=False):
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
    st.info("Carregue aqui os relatórios do Medself, Bradesco, Externa, etc.")
    files_base = st.file_uploader("Arquivos Base", accept_multiple_files=True, key="base", type=['csv','txt'])
    
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
    st.info("Carregue aqui os arquivos: Caixa Adrielli, Isis, Ivone, Nathy, Rebeca, etc.")
    files_caixa = st.file_uploader("Arquivos de Caixa", accept_multiple_files=True, key="caixa", type=['csv','txt'])
    
    if st.button("Processar Caixas"):
        if files_caixa:
            with st.spinner("Processando caixas (Isso pode levar alguns segundos)..."):
                df_caixa = process_caixa_files(files_caixa)
                if df_caixa is not None:
                    st.session_state['df_caixa_unificado'] = df_caixa
                    st.success(f"✅ {len(df_caixa)} lançamentos com OS identificados nos Caixas.")
                else:
                    st.error("Não consegui ler os caixas. Verifique se são CSVs.")
    
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
        
        # Agrupa Bases (Soma valor por OS)
        base_agg = df_b.groupby('OS_Formatada').agg({
            'Valor_Base': 'sum', 
            'Arquivo_Origem': 'first'
        }).reset_index()
        
        # Agrupa Caixas (Soma valor por OS)
        caixa_agg = df_c.groupby('OS_Extraida').agg({
            'Valor_Caixa': 'sum', 
            'Caixa_Origem': 'first', 
            'Nome_Original': 'first'
        }).reset_index().rename(columns={'OS_Extraida': 'OS_Formatada'})
        
        # Junta tudo
        merged = pd.merge(base_agg, caixa_agg, on='OS_Formatada', how='outer')
        merged.fillna({'Valor_Base': 0, 'Valor_Caixa': 0}, inplace=True)
        merged['Diferenca'] = merged['Valor_Caixa'] - merged['Valor_Base']
        
        # Define Status
        def get_status(row):
            diff = round(row['Diferenca'], 2)
            if row['Valor_Base'] == 0: return "SOBRA (Extra no Caixa)"
            if row['Valor_Caixa'] == 0: return "FALTA (Não lançado no Caixa)"
            if diff == 0: return "OK"
            if diff > 0: return f"DIVERGÊNCIA: Caixa Maior (+{diff})"
            return f"DIVERGÊNCIA: Caixa Menor ({diff})"

        merged['Status'] = merged.apply(get_status, axis=1)
        
        # Layout de Métricas
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("✅ Tudo Certo", len(merged[merged['Status']=='OK']))
        col2.metric("❌ Faltas (Esqueceram)", len(merged[merged['Status'].str.contains('FALTA')]))
        col3.metric("⚠️ Sobras (Erro Digitação?)", len(merged[merged['Status'].str.contains('SOBRA')]))
        col4.metric("📉 Divergência Valor", len(merged[merged['Status'].str.contains('DIVERGÊNCIA')]))
        
        st.divider()
        
        # Filtros
        opcoes = list(merged['Status'].unique())
        if 'OK' in opcoes: opcoes.remove('OK') # Remove OK do padrão para focar no erro
        
        filtro = st.multiselect("Filtrar Erros:", options=merged['Status'].unique(), default=opcoes)
        
        df_final = merged if not filtro else merged[merged['Status'].isin(filtro)]
        
        # Cores para a tabela
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
