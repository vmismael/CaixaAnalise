import streamlit as st
import pandas as pd
import re
from io import StringIO

# --- Configuração da Página ---
st.set_page_config(page_title="Conferência de Caixa", layout="wide")
st.title("Conferência de Caixa 💰")
st.markdown("---")

# --- FUNÇÕES DE LIMPEZA E EXTRAÇÃO ---

def limpar_valor_extrato(x):
    """
    Limpa valor do Extrato Consolidado (formato brasileiro: 1.000,00).
    Ex: '229,06' vira 229.06
    """
    if isinstance(x, (int, float)): return float(x)
    if isinstance(x, str):
        # Remove pontos de milhar e troca vírgula decimal por ponto
        clean = x.replace('.', '').replace(',', '.')
        try:
            return float(clean)
        except:
            return 0.0
    return 0.0

def limpar_valor_caixa(x):
    """
    Limpa valor dos Caixas (formato misto, geralmente ponto flutuante ou texto).
    Remove 'R$', espaços e converte para float.
    """
    if isinstance(x, (int, float)): return float(x)
    if isinstance(x, str):
        clean = x.replace('R$', '').strip()
        # Se tiver vírgula e ponto, assume que ponto é milhar e vírgula é decimal
        if ',' in clean and '.' in clean:
            clean = clean.replace('.', '').replace(',', '.')
        # Se tiver só vírgula, troca por ponto
        elif ',' in clean:
            clean = clean.replace(',', '.')
        
        try:
            return float(clean)
        except:
            return 0.0
    return 0.0

def extrair_os(texto):
    """
    Procura o padrão de OS (ex: 001-67495-31) dentro de um texto.
    """
    if not isinstance(texto, str):
        return None
    # Regex para capturar: 3 dígitos - 4 a 6 dígitos - 1 a 3 dígitos
    match = re.search(r'(\d{3}-\d{4,6}-\d{1,3})', texto)
    if match:
        return match.group(1)
    return None

# --- INTERFACE E PROCESSAMENTO ---

col_upload1, col_upload2 = st.columns(2)

with col_upload1:
    st.header("1. Extrato Consolidado")
    file_extrato = st.file_uploader("Upload 'extratos_consolidados.csv'", type=["csv"], key="extrato")

with col_upload2:
    st.header("2. Arquivos de Caixa")
    files_caixa = st.file_uploader("Upload dos arquivos de Caixa", accept_multiple_files=True, type=["csv"], key="caixa")

if file_extrato and files_caixa:
    st.markdown("---")
    st.info("Processando arquivos...")

    # ---------------------------------------------------------
    # 1. PROCESSAR EXTRATO
    # ---------------------------------------------------------
    try:
        # Lê o consolidado. Assume separador ';' e decimal ',' (padrão do arquivo que você enviou)
        df_ext = pd.read_csv(file_extrato, sep=';')
        
        # Garante que as colunas certas existem
        if 'Cod O.S.' in df_ext.columns and 'Valor' in df_ext.columns:
            # Renomeia para padronizar
            df_ext = df_ext.rename(columns={'Cod O.S.': 'OS', 'Valor': 'Valor_Extrato'})
            
            # Limpa valores
            df_ext['Valor_Extrato'] = df_ext['Valor_Extrato'].apply(limpar_valor_extrato)
            
            # Agrupa por OS (soma valores se houver mesma OS repetida)
            df_ext_agrupado = df_ext.groupby('OS')['Valor_Extrato'].sum().reset_index()
            
        else:
            st.error("O arquivo de extrato não tem as colunas 'Cod O.S.' e 'Valor'. Verifique o arquivo.")
            st.stop()
            
    except Exception as e:
        st.error(f"Erro ao ler extrato: {e}")
        st.stop()

    # ---------------------------------------------------------
    # 2. PROCESSAR CAIXAS
    # ---------------------------------------------------------
    dados_caixa = []
    
    for file in files_caixa:
        try:
            # Lê o conteúdo do arquivo
            # Tenta decodificar utf-8, se falhar tenta latin1
            try:
                conteudo = file.getvalue().decode('utf-8')
            except:
                conteudo = file.getvalue().decode('latin1')
            
            linhas = conteudo.splitlines()
            
            # Procura a linha de cabeçalho dinamicamente
            indice_cabecalho = -1
            for i, linha in enumerate(linhas):
                linha_upper = linha.upper()
                # O cabeçalho deve ter 'VALOR' e ('NOME' ou 'OS')
                if 'VALOR' in linha_upper and ('NOME' in linha_upper or 'OS' in linha_upper):
                    indice_cabecalho = i
                    break
            
            if indice_cabecalho == -1:
                st.warning(f"Arquivo '{file.name}' pulado: Cabeçalho não encontrado.")
                continue
                
            # Determina o separador (vírgula ou ponto e vírgula)
            sep = ';' if ';' in linhas[indice_cabecalho] else ','
            
            # Cria DataFrame a partir do cabeçalho encontrado
            df_temp = pd.read_csv(StringIO("\n".join(linhas[indice_cabecalho:])), sep=sep)
            
            # Identifica colunas de interesse
            col_nome = None
            col_valor = None
            
            for col in df_temp.columns:
                if 'NOME' in col.upper() or 'OS' in col.upper():
                    col_nome = col
                if 'VALOR' in col.upper():
                    col_valor = col
            
            if col_nome and col_valor:
                # Extrai OS e Limpa Valor
                df_temp['OS'] = df_temp[col_nome].apply(extrair_os)
                df_temp['Valor_Caixa'] = df_temp[col_valor].apply(limpar_valor_caixa)
                
                # Remove linhas sem OS válida
                df_temp = df_temp.dropna(subset=['OS'])
                
                # Guarda os dados
                dados_caixa.append(df_temp[['OS', 'Valor_Caixa']])
                
        except Exception as e:
            st.error(f"Erro ao processar caixa '{file.name}': {e}")

    if not dados_caixa:
        st.error("Nenhum dado válido encontrado nos arquivos de caixa.")
        st.stop()

    # Junta todos os caixas e soma por OS
    df_caixa_total = pd.concat(dados_caixa, ignore_index=True)
    df_caixa_agrupado = df_caixa_total.groupby('OS')['Valor_Caixa'].sum().reset_index()

    # ---------------------------------------------------------
    # 3. COMPARAÇÃO (CRUZAMENTO)
    # ---------------------------------------------------------
    
    # Junta Extrato e Caixa usando a coluna OS
    # how='outer' garante que mostramos OS que estão em um mas não no outro
    df_final = pd.merge(df_ext_agrupado, df_caixa_agrupado, on='OS', how='outer').fillna(0)
    
    # Calcula diferença
    df_final['Diferenca'] = df_final['Valor_Extrato'] - df_final['Valor_Caixa']
    
    # Define Status
    def definir_status(row):
        # Margem pequena para erro de arredondamento (0.01 centavo)
        if abs(row['Diferenca']) < 0.02:
            return "OK"
        elif row['Valor_Extrato'] > 0 and row['Valor_Caixa'] == 0:
            return "Falta no Caixa"
        elif row['Valor_Extrato'] == 0 and row['Valor_Caixa'] > 0:
            return "Sobra no Caixa (Não está no Extrato)"
        else:
            return "Valor Divergente"

    df_final['Status'] = df_final.apply(definir_status, axis=1)

    # ---------------------------------------------------------
    # 4. EXIBIÇÃO DOS RESULTADOS
    # ---------------------------------------------------------
    
    st.subheader("Resultados da Conferência")
    
    # Métricas
    total_ext = df_final['Valor_Extrato'].sum()
    total_cx = df_final['Valor_Caixa'].sum()
    total_diff = total_ext - total_cx
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Extratos", f"R$ {total_ext:,.2f}")
    m2.metric("Total Caixas", f"R$ {total_cx:,.2f}")
    m3.metric("Diferença Global", f"R$ {total_diff:,.2f}", delta_color="inverse")

    # Filtros de Visualização
    filtro = st.radio("Filtrar visualização:", ["Divergências", "Tudo", "Apenas OK"], horizontal=True)
    
    if filtro == "Divergências":
        df_show = df_final[df_final['Status'] != "OK"]
    elif filtro == "Apenas OK":
        df_show = df_final[df_final['Status'] == "OK"]
    else:
        df_show = df_final

    # Formatação de cores
    def colorir_tabela(val):
        color = ''
        if val == 'OK': color = '#d4edda' # Verde claro
        elif val == 'Valor Divergente': color = '#f8d7da' # Vermelho claro
        elif val == 'Falta no Caixa': color = '#fff3cd' # Amarelo claro
        elif val == 'Sobra no Caixa (Não está no Extrato)': color = '#cce5ff' # Azul claro
        return f'background-color: {color}'

    # Exibe Tabela
    st.dataframe(
        df_show.style.applymap(colorir_tabela, subset=['Status'])
               .format({"Valor_Extrato": "R$ {:,.2f}", "Valor_Caixa": "R$ {:,.2f}", "Diferenca": "R$ {:,.2f}"}),
        use_container_width=True
    )
