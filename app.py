import streamlit as st
import pandas as pd
from io import StringIO
import re

# --- Funções Auxiliares ---

def clean_currency(x):
    """Converte 'R$ 1.234,56', '1234.56' ou '1234,56' para float."""
    if isinstance(x, str):
        clean = x.replace('R$', '').strip()
        # Se tiver apenas '***' ou vazio
        if not any(char.isdigit() for char in clean):
            return 0.0
        try:
            if ',' in clean and '.' in clean:
                 clean = clean.replace('.', '').replace(',', '.')
            elif ',' in clean:
                 clean = clean.replace(',', '.')
            return float(clean)
        except ValueError:
            return 0.0
    try:
        return float(x)
    except (ValueError, TypeError):
        return 0.0

def extract_os(text):
    """Extrai padrão de OS (ex: 001-67495-31) de uma string."""
    if not isinstance(text, str):
        return None
    # Procura blocos de números separados por hífen
    # Ex: 3 digitos - 4 a 6 digitos - 1 a 3 digitos
    match = re.search(r'(\d{3}-\d{4,6}-\d{1,3})', text)
    if match:
        return match.group(1)
    return None

# --- Configuração da Página ---
st.set_page_config(page_title="Conferência de Caixa", layout="wide")
st.title("Conferência de Caixa 💰")

# --- PASSO 1: EXTRATOS ---
st.header("1. Upload dos Extratos (CSV)")
uploaded_extratos = st.file_uploader(
    "Arraste os arquivos de extrato aqui", 
    accept_multiple_files=True, 
    type="csv",
    key="extratos"
)

if uploaded_extratos:
    all_data_extratos = []
    for file in uploaded_extratos:
        try:
            content = file.getvalue().decode("latin1")
            lines = content.splitlines()
            if len(lines) < 11: continue
            
            # Extrair Credencial (B9)
            credencial = "Desconhecido"
            try:
                line_b9 = lines[8].strip().split(';')
                if len(line_b9) > 1: credencial = line_b9[1]
            except: pass

            # Ler dados
            df = pd.read_csv(StringIO("\n".join(lines[10:])), sep=';')
            if 'Data' in df.columns: df = df[df['Data'] != 'Sub-total']
            if 'Cod O.S.' in df.columns: df = df.dropna(subset=['Cod O.S.'])
            
            df['Credencial'] = credencial
            if 'Valor' in df.columns: df['Valor'] = df['Valor'].apply(clean_currency)
            
            all_data_extratos.append(df)
        except Exception as e:
            st.error(f"Erro no extrato {file.name}: {e}")

    if all_data_extratos:
        df_ext_final = pd.concat(all_data_extratos, ignore_index=True)
        # Agrupa Extratos por OS
        df_ext_grouped = df_ext_final.groupby(['Cod O.S.'])['Valor'].sum().reset_index()
        df_ext_grouped.rename(columns={'Valor': 'Valor_Extrato', 'Cod O.S.': 'OS'}, inplace=True)
        
        st.info(f"Extratos processados: {len(df_ext_grouped)} OS únicas identificadas. Total: R$ {df_ext_grouped['Valor_Extrato'].sum():,.2f}")
        st.session_state['df_extratos'] = df_ext_grouped
    else:
        st.warning("Nenhum dado extraído dos extratos.")

st.divider()

# --- PASSO 2: CAIXAS ---
st.header("2. Upload dos Caixas (Excel/CSV)")
st.caption("Suba as planilhas de caixa (Adrielli, Isis, etc.) salvas como CSV.")

uploaded_caixas = st.file_uploader(
    "Arraste os arquivos de caixa aqui", 
    accept_multiple_files=True, 
    type="csv",
    key="caixas"
)

if uploaded_caixas:
    all_data_caixas = []
    
    for file in uploaded_caixas:
        try:
            # Tenta ler com utf-8 ou latin1
            try:
                content = file.getvalue().decode("utf-8")
            except:
                content = file.getvalue().decode("latin1")
                
            lines = content.splitlines()
            
            # Encontrar cabeçalho dinamicamente
            header_idx = -1
            for i, line in enumerate(lines):
                upper_line = line.upper()
                if 'VALOR' in upper_line and ('NOME' in upper_line or 'OS' in upper_line):
                    header_idx = i
                    break
            
            if header_idx == -1:
                st.warning(f"Cabeçalho não encontrado em {file.name}. Pulando.")
                continue
                
            # Ler CSV a partir do cabeçalho
            # Detectar delimitador (vírgula ou ponto e vírgula)
            delim = ';' if ';' in lines[header_idx] else ','
            
            df_cx = pd.read_csv(StringIO("\n".join(lines[header_idx:])), sep=delim)
            
            # Identificar colunas
            col_nome = next((c for c in df_cx.columns if 'NOME' in c.upper() or 'OS' in c.upper()), None)
            col_valor = next((c for c in df_cx.columns if 'VALOR' in c.upper()), None)
            
            if col_nome and col_valor:
                df_cx['OS'] = df_cx[col_nome].apply(extract_os)
                df_cx['Valor_Caixa'] = df_cx[col_valor].apply(clean_currency)
                df_cx['Arquivo_Caixa'] = file.name
                
                # Filtrar apenas linhas onde conseguimos ler uma OS
                df_cx = df_cx.dropna(subset=['OS'])
                
                # Pegar apenas colunas úteis
                all_data_caixas.append(df_cx[['OS', 'Valor_Caixa', 'Arquivo_Caixa']])
            else:
                st.warning(f"Colunas 'Nome/OS' ou 'Valor' não identificadas em {file.name}")

        except Exception as e:
            st.error(f"Erro ao ler caixa {file.name}: {e}")

    if all_data_caixas:
        df_cx_final = pd.concat(all_data_caixas, ignore_index=True)
        # Agrupa Caixas por OS (caso tenha parcelado ou duplicado)
        df_cx_grouped = df_cx_final.groupby('OS')['Valor_Caixa'].sum().reset_index()
        
        st.info(f"Caixas processados: {len(df_cx_grouped)} OS únicas identificadas. Total: R$ {df_cx_grouped['Valor_Caixa'].sum():,.2f}")
        
        # --- PASSO 3: COMPARAÇÃO ---
        st.divider()
        st.header("3. Resultado da Conferência")
        
        if 'df_extratos' in st.session_state:
            df_ext = st.session_state['df_extratos']
            
            # Merge (Outer Join para pegar faltas e sobras)
            df_merged = pd.merge(df_ext, df_cx_grouped, on='OS', how='outer').fillna(0)
            
            df_merged['Diferença'] = df_merged['Valor_Extrato'] - df_merged['Valor_Caixa']
            
            # Status
            def get_status(row):
                if row['Valor_Extrato'] == 0 and row['Valor_Caixa'] > 0:
                    return "No Caixa, sem Extrato"
                elif row['Valor_Caixa'] == 0 and row['Valor_Extrato'] > 0:
                    return "No Extrato, sem Caixa"
                elif abs(row['Diferença']) < 0.01: # Margem de erro para float
                    return "OK"
                else:
                    return "Divergência de Valor"

            df_merged['Status'] = df_merged.apply(get_status, axis=1)
            
            # Exibição
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Extrato", f"R$ {df_merged['Valor_Extrato'].sum():,.2f}")
            col2.metric("Total Caixa", f"R$ {df_merged['Valor_Caixa'].sum():,.2f}")
            col3.metric("Diferença Total", f"R$ {df_merged['Diferença'].sum():,.2f}")
            
            # Filtros visuais
            st.write("### Detalhes")
            filtro = st.radio("Mostrar:", ["Tudo", "Divergências", "OK"], horizontal=True)
            
            if filtro == "Divergências":
                df_show = df_merged[df_merged['Status'] != "OK"]
            elif filtro == "OK":
                df_show = df_merged[df_merged['Status'] == "OK"]
            else:
                df_show = df_merged
            
            # Colorir dataframe
            def color_status(val):
                color = 'white'
                if val == 'OK': color = 'lightgreen'
                elif val == 'Divergência de Valor': color = 'salmon'
                elif val == 'No Extrato, sem Caixa': color = 'lightyellow'
                elif val == 'No Caixa, sem Extrato': color = 'lightblue'
                return f'background-color: {color}; color: black'

            st.dataframe(df_show.style.applymap(color_status, subset=['Status']).format({
                "Valor_Extrato": "R$ {:,.2f}", 
                "Valor_Caixa": "R$ {:,.2f}", 
                "Diferença": "R$ {:,.2f}"
            }))
            
        else:
            st.error("Por favor, faça o upload dos Extratos (Passo 1) antes de comparar.")
