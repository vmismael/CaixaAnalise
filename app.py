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
    if pd.isna(x) or x == '':
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        # Remove R$, espaços e caracteres estranhos
        clean = x.replace('R$', '').replace(' ', '').strip()
        # Se tiver vírgula e ponto, assume padrão brasileiro (1.000,00)
        if ',' in clean and '.' in clean:
            clean = clean.replace('.', '').replace(',', '.')
        # Se só tiver vírgula, troca por ponto
        elif ',' in clean:
            clean = clean.replace(',', '.')
        try:
            return float(clean)
        except:
            return 0.0
    return 0.0

def extract_os_code(text):
    """Extrai código da OS (ex: 001-67358-42)"""
    if not isinstance(text, str):
        return None
    # Regex flexível para capturar 3 digitos - digitos - digitos
    match = re.search(r'(\d{3}\s*-\s*\d+\s*-\s*\d+)', text)
    if match:
        return match.group(1).replace(' ', '').strip() # Remove espaços internos se houver
    return None

def process_base_files(uploaded_files):
    dataframes = []
    
    progress_bar = st.progress(0)
    
    for i, file in enumerate(uploaded_files):
        try:
            # Tenta ler como CSV padrão (pula 10 linhas)
            file.seek(0)
            df = pd.read_csv(file, sep=';', skiprows=10, encoding='latin1', on_bad_lines='skip', engine='python')
            
            # Se falhar ou vier vazio, tenta ler do começo (formato Externa)
            if df.empty or 'Data' not in df.columns:
                file.seek(0)
                df = pd.read_csv(file, sep=';', encoding='latin1', on_bad_lines='skip', engine='python')
            
            # Normalização de Colunas
            df.columns = [c.strip() for c in df.columns]
            
            # Identifica coluna de OS
            col_os = None
            if 'Cod O.S.' in df.columns: col_os = 'Cod O.S.'
            elif 'Detalhado' in df.columns: col_os = 'Detalhado'
            
            # Identifica coluna de Valor
            col_valor = None
            if 'Valor' in df.columns: col_valor = 'Valor'
            elif 'Lqd. Balc.' in df.columns: col_valor = 'Lqd. Balc.'
            
            if col_os and col_valor:
                # Limpeza e Padronização
                df['OS_Formatada'] = df[col_os].astype(str).apply(lambda x: x.strip())
                df['Valor_Base'] = df[col_valor].apply(clean_currency)
                df['Arquivo_Origem'] = file.name
                
                # Filtra apenas linhas válidas
                df_valid = df[df['Valor_Base'] > 0].copy()
                dataframes.append(df_valid[['OS_Formatada', 'Valor_Base', 'Arquivo_Origem']])
                
        except Exception as e:
            st.error(f"Erro ao ler base {file.name}: {e}")
            
        progress_bar.progress((i + 1) / len(uploaded_files))
            
    if dataframes:
        return pd.concat(dataframes, ignore_index=True)
    return None

def process_caixa_files(uploaded_files):
    dataframes = []
    errors = []
    
    progress_bar = st.progress(0)

    for i, file in enumerate(uploaded_files):
        try:
            # 1. Lê o arquivo como texto para achar o cabeçalho
            file.seek(0)
            content_bytes = file.read()
            # Tenta decodificar latin1 (padrão Excel BR)
            try:
                content = content_bytes.decode('latin1')
            except:
                content = content_bytes.decode('utf-8', errors='ignore')
                
            lines = content.splitlines()
            
            header_row = -1
            sep = ',' # Default separator
            
            # 2. Procura a linha de cabeçalho
            for idx, line in enumerate(lines):
                # Procura por palavras chave DATA e VALOR na mesma linha
                line_upper = line.upper()
                if 'DATA' in line_upper and ('VALOR' in line_upper or 'VLR' in line_upper):
                    header_row = idx
                    # Detecta separador contando ocorrências na linha de cabeçalho
                    if line.count(';') > line.count(','):
                        sep = ';'
                    else:
                        sep = ','
                    break
            
            if header_row != -1:
                # 3. Lê o CSV usando o separador detectado
                file.seek(0)
                df = pd.read_csv(file, sep=sep, skiprows=header_row, encoding='latin1', on_bad_lines='skip', engine='python')
                
                # Normaliza colunas (UPPERCASE e remove espaços extras)
                df.columns = [str(c).upper().strip() for c in df.columns]
                
                # Procura colunas chave
                col_nome = next((c for c in df.columns if 'NOME' in c or 'DESCRICAO' in c or 'HISTORICO' in c), None)
                col_valor = next((c for c in df.columns if 'VALOR' in c or 'VLR' in c), None)
                
                if col_nome and col_valor:
                    df['OS_Extraida'] = df[col_nome].astype(str).apply(extract_os_code)
                    df['Valor_Caixa'] = df[col_valor].apply(clean_currency)
                    df['Caixa_Origem'] = file.name
                    df['Nome_Original'] = df[col_nome]
                    
                    # Mantém apenas linhas onde conseguimos extrair uma OS
                    df_validos = df.dropna(subset=['OS_Extraida']).copy()
                    
                    if not df_validos.empty:
                        dataframes.append(df_validos[['OS_Extraida', 'Valor_Caixa', 'Caixa_Origem', 'Nome_Original']])
                    # else:
                    #     errors.append(f"{file.name}: Nenhuma OS encontrada nas linhas.")
                else:
                    errors.append(f"{file.name}: Colunas 'NOME' ou 'VALOR' não identificadas.")
            else:
                errors.append(f"{file.name}: Cabeçalho 'DATA/VALOR' não encontrado.")
                
        except Exception as e:
            errors.append(f"{file.name}: Erro técnico - {str(e)}")
            
        progress_bar.progress((i + 1) / len(uploaded_files))
    
    if errors:
        with st.expander("⚠️ Avisos de Leitura (Arquivos ignorados ou vazios)"):
            for err in errors:
                st.write(err)
            
    if dataframes:
        return pd.concat(dataframes, ignore_index=True)
    return None

# --- INTERFACE ---

st.title("📊 Conferência de Caixas vs Bases")

tab1, tab2, tab3 = st.tabs(["1. Upload das Bases (Convênios)", "2. Upload dos Caixas (Funcionários)", "3. Relatório Final"])

# --- ABA 1 ---
with tab1:
    st.markdown("### Bases de Laboratório (Medself, Bradesco, etc)")
    files_base = st.file_uploader("Arraste os CSVs das BASES aqui", accept_multiple_files=True, key="base")
    
    if st.button("Processar Bases", type="primary"):
        if files_base:
            with st.spinner("Lendo bases..."):
                df_base = process_base_files(files_base)
                if df_base is not None:
                    st.session_state['df_base_unificada'] = df_base
                    st.success(f"✅ Bases processadas! {len(df_base)} registros importados.")
                else:
                    st.error("Nenhum dado válido encontrado nas bases.")
        else:
            st.warning("Selecione arquivos primeiro.")
            
    if st.session_state['df_base_unificada'] is not None:
        st.dataframe(st.session_state['df_base_unificada'].head(5), use_container_width=True)

# --- ABA 2 ---
with tab2:
    st.markdown("### Planilhas de Caixa (Isis, Ivone, etc)")
    files_caixa = st.file_uploader("Arraste os CSVs dos CAIXAS aqui", accept_multiple_files=True, key="caixa")
    
    if st.button("Processar Caixas", type="primary"):
        if files_caixa:
            with st.spinner("Lendo caixas e identificando OS..."):
                df_caixa = process_caixa_files(files_caixa)
                if df_caixa is not None:
                    st.session_state['df_caixa_unificado'] = df_caixa
                    st.success(f"✅ Caixas processados! {len(df_caixa)} lançamentos com OS identificados.")
                else:
                    st.error("Não foi possível ler dados válidos dos caixas. Verifique se são CSVs e se têm colunas DATA e VALOR.")
        else:
            st.warning("Selecione arquivos primeiro.")

    if st.session_state['df_caixa_unificado'] is not None:
        st.dataframe(st.session_state['df_caixa_unificado'].head(5), use_container_width=True)

# --- ABA 3 ---
with tab3:
    st.header("Relatório de Divergências")
    
    if st.session_state['df_base_unificada'] is None or st.session_state['df_caixa_unificado'] is None:
        st.info("👆 Por favor, processe as Bases na Aba 1 e os Caixas na Aba 2 antes de conferir.")
    else:
        df_b = st.session_state['df_base_unificada']
        df_c = st.session_state['df_caixa_unificado']
        
        # Agrupamento (caso haja parcelas ou exames quebrados)
        base_agg = df_b.groupby('OS_Formatada').agg({'Valor_Base': 'sum', 'Arquivo_Origem': 'first'}).reset_index()
        caixa_agg = df_c.groupby('OS_Extraida').agg({'Valor_Caixa': 'sum', 'Caixa_Origem': 'first', 'Nome_Original': 'first'}).reset_index().rename(columns={'OS_Extraida': 'OS_Formatada'})
        
        # Merge (Outer Join)
        merged = pd.merge(base_agg, caixa_agg, on='OS_Formatada', how='outer')
        merged['Valor_Base'] = merged['Valor_Base'].fillna(0)
        merged['Valor_Caixa'] = merged['Valor_Caixa'].fillna(0)
        merged['Diferenca'] = merged['Valor_Caixa'] - merged['Valor_Base']
        
        # Lógica de Status
        def get_status(row):
            diff = round(row['Diferenca'], 2)
            if row['Valor_Base'] == 0: return "SOBRA (Não consta na Base)"
            if row['Valor_Caixa'] == 0: return "FALTA (Não lançado no Caixa)"
            if diff == 0: return "OK"
            if diff > 0: return f"DIVERGÊNCIA: Caixa Maior (+{diff})"
            return f"DIVERGÊNCIA: Caixa Menor ({diff})"

        merged['Status'] = merged.apply(get_status, axis=1)
        
        # Filtros e Métricas
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Conferido (OK)", len(merged[merged['Status'] == 'OK']))
        col2.metric("Total Faltas", len(merged[merged['Status'].str.contains("FALTA")]))
        col3.metric("Total Sobras", len(merged[merged['Status'].str.contains("SOBRA")]))
        
        filtro = st.multiselect("Filtrar Status", options=merged['Status'].unique(), default=[s for s in merged['Status'].unique() if s != 'OK'])
        
        df_show = merged if not filtro else merged[merged['Status'].isin(filtro)]
        
        # Tabela Colorida
        def color_map(val):
            color = ''
            if "FALTA" in str(val) or "Menor" in str(val): color = '#ffcccc' # Vermelho claro
            elif "SOBRA" in str(val): color = '#fff3cd' # Amarelo claro
            elif "OK" in str(val): color = '#ccffcc' # Verde claro
            return f'background-color: {color}'

        st.dataframe(
            df_show.style.applymap(color_map, subset=['Status'])
                   .format("{:.2f}", subset=['Valor_Base', 'Valor_Caixa', 'Diferenca']),
            use_container_width=True
        )
        
        # Download
        csv = merged.to_csv(index=False, sep=';', decimal=',').encode('latin1', errors='replace')
        st.download_button("📥 Baixar Relatório", data=csv, file_name="relatorio_conferencia.csv", mime="text/csv")
