import streamlit as st
import pandas as pd
import re
from io import StringIO

st.set_page_config(page_title="Conferência Total: Extratos vs Caixa", layout="wide")
st.title("Conferência de Caixa Completa 📊")

# --- FUNÇÕES AUXILIARES ---

def clean_currency(x):
    """
    Tenta converter qualquer formato de moeda (1.000,00 ou 1000.00 ou R$ 1000) para float.
    """
    if isinstance(x, (int, float)):
        return float(x)
    
    if isinstance(x, str):
        clean = x.replace('R$', '').strip()
        # Se for vazio ou apenas caracteres estranhos
        if not any(char.isdigit() for char in clean):
            return 0.0
        
        try:
            # Lógica para detectar se o separador decimal é vírgula ou ponto
            if ',' in clean and '.' in clean:
                # Formato brasileiro com milhar (1.234,56) -> remove ponto, troca vírgula
                clean = clean.replace('.', '').replace(',', '.')
            elif ',' in clean:
                # Apenas vírgula (1234,56) -> troca por ponto
                clean = clean.replace(',', '.')
            # Se tiver só ponto (1234.56), o float() do python já entende
            
            return float(clean)
        except:
            return 0.0
    return 0.0

def extract_os(texto):
    """Extrai o padrão de OS (ex: 001-67495-31) de dentro de um texto."""
    if not isinstance(texto, str):
        return None
    # Regex: 3 digitos - 4 a 6 digitos - 1 a 3 digitos
    match = re.search(r'(\d{3}-\d{4,6}-\d{1,3})', texto)
    if match:
        return match.group(1)
    return None

# ==============================================================================
# ETAPA 1: PROCESSAMENTO DOS EXTRATOS (CONVÊNIOS)
# ==============================================================================
st.header("1. Extratos (Convênios/Áreas)")
st.info("Faça o upload dos arquivos CSV que têm a credencial na célula B9.")

uploaded_extratos = st.file_uploader(
    "Upload dos Extratos (.csv)", 
    accept_multiple_files=True, 
    type=["csv"],
    key="extratos_uploader"
)

df_extratos_final = None

if uploaded_extratos:
    lista_extratos = []
    
    progress_bar = st.progress(0)
    
    for i, file in enumerate(uploaded_extratos):
        try:
            # Ler linhas para pré-processamento
            content = file.getvalue().decode("latin1")
            lines = content.splitlines()
            
            if len(lines) < 11: continue # Arquivo muito pequeno/vazio
            
            # 1. Pega Credencial (B9 -> linha index 8)
            credencial = "Desconhecido"
            try:
                line_b9 = lines[8].strip().split(';')
                if len(line_b9) > 1:
                    credencial = line_b9[1]
            except:
                pass
            
            # 2. Lê os dados (Cabeçalho na linha 11 -> index 10)
            data_io = StringIO("\n".join(lines[10:]))
            df = pd.read_csv(data_io, sep=';')
            
            # 3. Limpeza
            # Remover linhas de sub-total
            if 'Data' in df.columns:
                df = df[df['Data'] != 'Sub-total']
            
            # Remover vazios de OS
            if 'Cod O.S.' in df.columns:
                df = df.dropna(subset=['Cod O.S.'])
                
                # Normaliza colunas
                df['Credencial'] = credencial
                df['Arquivo_Origem'] = file.name
                
                # Limpa Valor
                if 'Valor' in df.columns:
                    df['Valor'] = df['Valor'].apply(clean_currency)
                
                lista_extratos.append(df)
                
        except Exception as e:
            st.error(f"Erro ao ler {file.name}: {e}")
        
        progress_bar.progress((i + 1) / len(uploaded_extratos))
    
    if lista_extratos:
        df_extratos_final = pd.concat(lista_extratos, ignore_index=True)
        
        # Agrupar por OS para comparação futura (somar valores da mesma OS)
        df_ext_grouped = df_extratos_final.groupby(['Cod O.S.', 'Credencial'])['Valor'].sum().reset_index()
        df_ext_grouped.rename(columns={'Cod O.S.': 'OS', 'Valor': 'Valor_Extrato'}, inplace=True)
        
        # MOSTRAR RESUMO
        c1, c2 = st.columns(2)
        c1.success(f"{len(uploaded_extratos)} arquivos processados.")
        c1.write(f"**Total Extratos:** R$ {df_ext_grouped['Valor_Extrato'].sum():,.2f}")
        
        with c2:
            st.write("Resumo por Área:")
            resumo = df_ext_grouped.groupby('Credencial')['Valor_Extrato'].sum().reset_index()
            st.dataframe(resumo.style.format({"Valor_Extrato": "R$ {:,.2f}"}), height=150)

        with st.expander("Ver Tabela Completa dos Extratos"):
            st.dataframe(df_ext_grouped)

st.markdown("---")

# ==============================================================================
# ETAPA 2: PROCESSAMENTO DOS CAIXAS (EXCEL OU CSV)
# ==============================================================================
st.header("2. Caixas (Financeiro)")
st.info("Faça o upload das planilhas de caixa (Excel .xlsx ou CSV).")

# AQUI: Adicionado suporte a xlsx e xls
uploaded_caixas = st.file_uploader(
    "Upload dos Caixas (.csv, .xlsx)", 
    accept_multiple_files=True, 
    type=["csv", "xlsx", "xls"],
    key="caixas_uploader"
)

df_caixa_final = None

if uploaded_caixas:
    lista_caixas = []
    
    for file in uploaded_caixas:
        try:
            df_temp = None
            
            # A. LER ARQUIVO (Excel ou CSV)
            if file.name.endswith('.xlsx') or file.name.endswith('.xls'):
                # Ler Excel
                df_raw = pd.read_excel(file)
                # O Pandas lê o Excel inteiro. Precisamos achar a linha de cabeçalho.
                # Vamos converter para lista de listas para achar o cabeçalho
                valores = df_raw.values.tolist()
                cols = df_raw.columns.tolist()
                todos_dados = [cols] + valores
                
                header_idx = -1
                for i, row in enumerate(todos_dados):
                    row_str = str(row).upper()
                    if 'VALOR' in row_str and ('NOME' in row_str or 'OS' in row_str):
                        header_idx = i
                        break
                
                if header_idx != -1:
                    # Recria o DataFrame usando a linha certa como cabeçalho
                    # Se header_idx for 0, o df_raw já estava certo, mas vamos garantir
                    keys = todos_dados[header_idx]
                    data = todos_dados[header_idx+1:]
                    df_temp = pd.DataFrame(data, columns=keys)

            else:
                # Ler CSV
                try:
                    content = file.getvalue().decode("utf-8")
                except:
                    content = file.getvalue().decode("latin1")
                
                lines = content.splitlines()
                header_idx = -1
                for i, line in enumerate(lines):
                    l_upper = line.upper()
                    if 'VALOR' in l_upper and ('NOME' in l_upper or 'OS' in l_upper):
                        header_idx = i
                        break
                
                if header_idx != -1:
                    sep = ';' if ';' in lines[header_idx] else ','
                    df_temp = pd.read_csv(StringIO("\n".join(lines[header_idx:])), sep=sep)

            # B. EXTRAIR DADOS SE O DATAFRAME FOI CRIADO
            if df_temp is not None:
                # Normalizar nomes de colunas para maiúsculo
                df_temp.columns = [str(c).upper().strip() for c in df_temp.columns]
                
                # Achar coluna de Nome/OS e Valor
                col_nome = next((c for c in df_temp.columns if 'NOME' in c or 'OS' in c), None)
                col_valor = next((c for c in df_temp.columns if 'VALOR' in c), None)
                
                if col_nome and col_valor:
                    # Copia apenas o necessário
                    df_clean = pd.DataFrame()
                    df_clean['OS'] = df_temp[col_nome].apply(extract_os)
                    df_clean['Valor_Caixa'] = df_temp[col_valor].apply(clean_currency)
                    df_clean['Arquivo_Caixa'] = file.name
                    
                    # Remove quem não tem OS
                    df_clean = df_clean.dropna(subset=['OS'])
                    lista_caixas.append(df_clean)
                else:
                    st.warning(f"Não achei colunas NOME/OS e VALOR em {file.name}")
            else:
                st.warning(f"Não achei cabeçalho válido em {file.name}")

        except Exception as e:
            st.error(f"Erro processando {file.name}: {e}")

    if lista_caixas:
        df_caixas_all = pd.concat(lista_caixas, ignore_index=True)
        # Agrupa por OS (pode ter pagamentos parciais)
        df_caixa_final = df_caixas_all.groupby('OS')['Valor_Caixa'].sum().reset_index()
        
        st.success(f"Caixas processados! Total Identificado: R$ {df_caixa_final['Valor_Caixa'].sum():,.2f}")
        with st.expander("Ver dados do Caixa"):
            st.dataframe(df_caixa_final)

# ==============================================================================
# ETAPA 3: COMPARAÇÃO E RESULTADOS
# ==============================================================================

if df_extratos_final is not None and df_caixa_final is not None:
    st.markdown("---")
    st.header("3. Resultado da Conferência")
    
    # Merge
    df_merged = pd.merge(df_ext_grouped, df_caixa_final, on='OS', how='outer').fillna(0)
    
    # Calcular Diferença
    df_merged['Diferenca'] = df_merged['Valor_Extrato'] - df_merged['Valor_Caixa']
    
    # Definir Status
    def get_status(row):
        if abs(row['Diferenca']) < 0.05: # Aceita 5 centavos de erro
            return "OK"
        if row['Valor_Extrato'] > 0 and row['Valor_Caixa'] == 0:
            return "Falta no Caixa"
        if row['Valor_Extrato'] == 0 and row['Valor_Caixa'] > 0:
            return "Sobra no Caixa (Não estava no Extrato)"
        return "Valor Divergente"

    df_merged['Status'] = df_merged.apply(get_status, axis=1)
    
    # Filtros
    filtro_status = st.radio("Filtrar por Status:", ["Divergências", "Tudo", "OK"], horizontal=True)
    
    if filtro_status == "Divergências":
        df_show = df_merged[df_merged['Status'] != "OK"]
    elif filtro_status == "OK":
        df_show = df_merged[df_merged['Status'] == "OK"]
    else:
        df_show = df_merged
        
    # Estilização das Cores
    def colorir(val):
        color = ''
        if val == 'OK': color = '#d1e7dd' # Verde
        elif val == 'Falta no Caixa': color = '#f8d7da' # Vermelho
        elif val == 'Sobra no Caixa (Não estava no Extrato)': color = '#fff3cd' # Amarelo
        elif val == 'Valor Divergente': color = '#cff4fc' # Azul
        return f'background-color: {color}'

    # Exibir Tabela Final
    st.dataframe(
        df_show.style.applymap(colorir, subset=['Status'])
               .format({"Valor_Extrato": "R$ {:,.2f}", "Valor_Caixa": "R$ {:,.2f}", "Diferenca": "R$ {:,.2f}"}),
        use_container_width=True,
        height=600
    )
    
    # Botão de Download
    csv_final = df_merged.to_csv(index=False, sep=';', decimal=',').encode('latin1')
    st.download_button(
        "Baixar Relatório Final de Divergências",
        data=csv_final,
        file_name="relatorio_conferencia.csv",
        mime="text/csv"
    )

elif df_extratos_final is None:
    st.warning("Aguardando upload dos Extratos (Passo 1)...")
elif df_caixa_final is None:
    st.warning("Aguardando upload dos Caixas (Passo 2)...")
