import streamlit as st
import pandas as pd
from io import StringIO
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sistema de Conferência Financeira", layout="wide")
st.title("📊 Sistema Financeiro Integrado")

# --- FUNÇÕES AUXILIARES (COMPARTILHADAS) ---

def clean_currency(value):
    """
    Converte strings de moeda (ex: '1.234,56' ou 'R$ 1.234,56') e floats para float puro.
    Mais robusta para aceitar tanto formato CSV quanto Excel.
    """
    if isinstance(value, (int, float)):
        return float(value)
    
    if isinstance(value, str):
        # Remove R$, espaços e quebras de linha
        clean = value.replace('R$', '').replace(' ', '').strip()
        
        # Lógica para formato brasileiro (milhar com ponto, decimal com vírgula)
        # Ex: 1.000,00 -> remove ponto, troca virgula por ponto
        if ',' in clean and '.' in clean:
             clean = clean.replace('.', '').replace(',', '.')
        elif ',' in clean:
             clean = clean.replace(',', '.')
        
        try:
            return float(clean)
        except ValueError:
            return 0.0
    return 0.0

def extract_os(text):
    """Extrai padrões de OS como 001-67495-42 de um texto."""
    if not isinstance(text, str):
        return None
    # Procura padrão XXX-XXXXX-XX ou similar
    match = re.search(r'(\d{3}-\d{4,6}-\d{1,3})', text)
    if match:
        return match.group(1)
    return None

def find_header_row(df):
    """Tenta encontrar a linha de cabeçalho no Excel procurando por 'NOME' e 'VALOR'."""
    for i in range(min(20, len(df))):  # Procura nas primeiras 20 linhas
        row_values = [str(v).upper() for v in df.iloc[i].values]
        if 'NOME' in row_values and 'VALOR' in row_values:
            return i
    return 0 # Padrão se não achar

# --- CRIAÇÃO DAS ABAS ---
tab1, tab2 = st.tabs(["📂 Consolidação de Extratos (CSV)", "🔍 Conferência de Caixas (Excel vs CSV)"])

# ==============================================================================
# ABA 1: CONSOLIDAÇÃO
# ==============================================================================
with tab1:
    st.header("Consolidação de Extratos")
    st.markdown("Faça o upload dos arquivos para gerar um relatório unificado.")

    col1, col2 = st.columns(2)
    
    with col1:
        st.info("📄 **Extratos Padrão** (Sistema Antigo)")
        uploaded_files = st.file_uploader(
            "Solte os arquivos padrão aqui", 
            accept_multiple_files=True, 
            type="csv",
            key="upload_padrao"
        )

    with col2:
        st.warning("📑 **Extratos Externos** (Novo Modelo)")
        uploaded_files_ext = st.file_uploader(
            "Solte os arquivos 'Externa' aqui (OS na Col B, Valor na Col F)", 
            accept_multiple_files=True, 
            type="csv",
            key="upload_externo"
        )

    if uploaded_files or uploaded_files_ext:
        all_data = []
        
        # 1. PROCESSAR ARQUIVOS PADRÃO
        if uploaded_files:
            for uploaded_file in uploaded_files:
                try:
                    stringio = StringIO(uploaded_file.getvalue().decode("latin1"))
                    lines = stringio.readlines()
                    
                    if len(lines) < 11: continue

                    # Extrair Credencial
                    try:
                        line_b9 = lines[8].strip().split(';')
                        credencial = line_b9[1] if len(line_b9) > 1 else "Desconhecido"
                    except:
                        credencial = "Erro Leitura"

                    # Ler dados
                    data_content = "".join(lines[10:])
                    df = pd.read_csv(StringIO(data_content), sep=';')
                    
                    if df.empty: continue

                    if 'Data' in df.columns: df = df[df['Data'] != 'Sub-total']
                    if 'Cod O.S.' in df.columns: df = df.dropna(subset=['Cod O.S.'])

                    df['Credencial'] = credencial
                    if 'Valor' in df.columns:
                        df['Valor'] = df['Valor'].apply(clean_currency)
                    
                    all_data.append(df[['Credencial', 'Cod O.S.', 'Nome', 'Valor']])
                    
                except Exception as e:
                    st.error(f"Erro no arquivo padrão {uploaded_file.name}: {e}")

        # 2. PROCESSAR ARQUIVOS EXTERNOS (NOVO MODELO)
        if uploaded_files_ext:
            for uploaded_file in uploaded_files_ext:
                try:
                    # Tenta ler com separador ; e encoding comum
                    try:
                        df_ext = pd.read_csv(uploaded_file, sep=';', encoding='latin-1')
                    except:
                        uploaded_file.seek(0)
                        df_ext = pd.read_csv(uploaded_file, sep=';', encoding='utf-8')

                    # Verifica se tem colunas suficientes (B é índice 1, F é índice 5)
                    if df_ext.shape[1] >= 6:
                        df_temp = pd.DataFrame()
                        
                        # Mapeamento Solicitado:
                        # OS -> Coluna B (índice 1)
                        # Valor -> Coluna F (índice 5)
                        # Nome -> Coluna A (índice 0) ex: COLETA EXTERNA
                        
                        df_temp['Cod O.S.'] = df_ext.iloc[:, 1]
                        df_temp['Valor'] = df_ext.iloc[:, 5].apply(clean_currency)
                        df_temp['Nome'] = df_ext.iloc[:, 0]
                        df_temp['Credencial'] = df_ext.iloc[:, 0] # Usa a mesma coluna A para agrupar
                        
                        # Limpeza básica
                        df_temp = df_temp.dropna(subset=['Cod O.S.'])
                        # Remove linhas onde OS não parece OS (opcional, mas bom pra evitar cabeçalhos repetidos)
                        df_temp = df_temp[df_temp['Cod O.S.'].astype(str).str.contains('-', na=False)]
                        
                        all_data.append(df_temp[['Credencial', 'Cod O.S.', 'Nome', 'Valor']])
                    else:
                        st.error(f"Arquivo {uploaded_file.name} não tem colunas suficientes (esperado até coluna F).")

                except Exception as e:
                    st.error(f"Erro no arquivo externo {uploaded_file.name}: {e}")

        # 3. CONSOLIDAÇÃO FINAL
        if all_data:
            df_final = pd.concat(all_data, ignore_index=True)

            # Agrupar e Somar
            df_grouped = df_final.groupby(['Credencial', 'Cod O.S.', 'Nome'])['Valor'].sum().reset_index()

            st.success(f"Processado com sucesso! Total de registros: {len(df_grouped)}")
            
            # Resumo
            st.subheader("Resumo por Área")
            resumo_area = df_grouped.groupby('Credencial')['Valor'].sum().reset_index()
            st.dataframe(resumo_area.style.format({"Valor": "R$ {:,.2f}"}))

            # Detalhado
            st.subheader("Detalhamento por OS")
            st.dataframe(df_grouped.style.format({"Valor": "R$ {:,.2f}"}))
            
            # Download
            csv = df_grouped.to_csv(index=False, sep=';', decimal=',').encode('latin1')
            st.download_button(
                label="📥 Baixar Planilha Consolidada",
                data=csv,
                file_name="extratos_consolidados.csv",
                mime="text/csv",
            )
            
            # Salvar para Aba 2
            st.session_state['df_extratos_consolidado'] = df_grouped
            
        else:
            st.warning("Nenhum dado válido encontrado.")

# ==============================================================================
# ABA 2: CONFERÊNCIA
# ==============================================================================
with tab2:
    st.header("Conferência: Caixas Individuais vs Resumo")
    st.markdown("""
    Compare os **arquivos de Caixa (Excel)** com o **Resumo Consolidado (CSV)**.
    """)
    
    col_up1, col_up2 = st.columns(2)
    
    with col_up1:
        file_csv_conf = st.file_uploader("1. Carregar Resumo (CSV)", type=["csv"], key="upload_csv_tab2")
        
        df_resumo_input = None
        if 'df_extratos_consolidado' in st.session_state and not file_csv_conf:
            st.info("💡 Usando arquivo gerado na Aba 1.")
            if st.checkbox("Confirmar uso da Consolidação da Aba 1", value=True):
                df_resumo_input = st.session_state['df_extratos_consolidado']
        elif file_csv_conf:
            try:
                df_resumo_input = pd.read_csv(file_csv_conf, sep=';', encoding='latin-1')
            except:
                df_resumo_input = pd.read_csv(file_csv_conf, sep=';', encoding='utf-8')

    with col_up2:
        files_excel_conf = st.file_uploader("2. Carregar Caixas (Excel)", type=["xlsx"], accept_multiple_files=True, key="upload_excel_tab2")

    if df_resumo_input is not None and files_excel_conf:
        
        # Preparar Resumo
        df_resumo = df_resumo_input.copy()
        cols_os = [c for c in df_resumo.columns if 'O.S.' in c or 'OS' in c]
        cols_val = [c for c in df_resumo.columns if 'Valor' in c or 'VALOR' in c]

        if not cols_os or not cols_val:
            st.error("Colunas 'OS' ou 'Valor' não identificadas no CSV.")
        else:
            col_os_csv = cols_os[0]
            col_val_csv = cols_val[0]

            df_resumo['OS_Limpa'] = df_resumo[col_os_csv].astype(str).str.strip()
            df_resumo['Valor_Limpo'] = df_resumo[col_val_csv].apply(clean_currency)
            dict_resumo = pd.Series(df_resumo.Valor_Limpo.values, index=df_resumo.OS_Limpa).to_dict()
            
            st.success(f"Referência Carregada: {len(df_resumo)} OSs.")
            st.divider()

            try:
                xls_temp = pd.ExcelFile(files_excel_conf[0])
                sheet_names = xls_temp.sheet_names
                selected_sheet = st.selectbox("📅 Selecione a Aba do Excel:", sheet_names)
                
                if st.button("Iniciar Conferência", type="primary"):
                    st.write(f"### Resultados: {selected_sheet}")
                    all_os_processed_in_excel = set()

                    for uploaded_file in files_excel_conf:
                        try:
                            df_temp = pd.read_excel(uploaded_file, sheet_name=selected_sheet, header=None)
                            header_row_idx = find_header_row(df_temp)
                            df_caixa = pd.read_excel(uploaded_file, sheet_name=selected_sheet, header=header_row_idx)
                            df_caixa.columns = [str(c).upper().strip() for c in df_caixa.columns]
                            
                            if 'NOME' not in df_caixa.columns or 'VALOR' not in df_caixa.columns:
                                st.warning(f"⚠️ {uploaded_file.name}: Colunas não encontradas.")
                                continue

                            divergencias = []
                            conferem = []
                            faltantes_no_csv = []

                            for index, row in df_caixa.iterrows():
                                nome_completo = str(row['NOME'])
                                valor_caixa = clean_currency(row['VALOR'])
                                if valor_caixa == 0: continue

                                os_encontrada = extract_os(nome_completo)
                                if os_encontrada:
                                    all_os_processed_in_excel.add(os_encontrada)
                                    if os_encontrada in dict_resumo:
                                        valor_resumo = dict_resumo[os_encontrada]
                                        diferenca = valor_caixa - valor_resumo
                                        if abs(diferenca) > 0.02:
                                            divergencias.append({"OS": os_encontrada, "Nome": nome_completo, "Valor Caixa": valor_caixa, "Valor Resumo": valor_resumo, "Diferença": diferenca})
                                        else:
                                            conferem.append(os_encontrada)
                                    else:
                                        faltantes_no_csv.append({"OS": os_encontrada, "Nome": nome_completo, "Valor": valor_caixa})

                            with st.expander(f"📁 {uploaded_file.name}", expanded=True):
                                c1, c2, c3 = st.columns(3)
                                c1.metric("Conferem", len(conferem))
                                c2.metric("Divergentes", len(divergencias))
                                c3.metric("Só no Caixa", len(faltantes_no_csv))

                                if divergencias:
                                    st.dataframe(pd.DataFrame(divergencias).style.format({"Valor Caixa": "R$ {:.2f}", "Valor Resumo": "R$ {:.2f}", "Diferença": "R$ {:.2f}"}))
                                if faltantes_no_csv:
                                    st.warning("Só no Caixa (Não está no CSV):")
                                    st.dataframe(pd.DataFrame(faltantes_no_csv))
                        
                        except Exception as e:
                            st.error(f"Erro ao ler {uploaded_file.name}: {e}")

                    st.divider()
                    st.subheader("🔍 Auditoria Inversa (Sobra no CSV)")
                    missing_in_excel = []
                    for os_csv, val_csv in dict_resumo.items():
                        if os_csv not in all_os_processed_in_excel:
                            missing_in_excel.append({"OS": os_csv, "Valor CSV": val_csv})
                    
                    if missing_in_excel:
                        st.dataframe(pd.DataFrame(missing_in_excel))
                    else:
                        st.success("Tudo bateu!")

            except Exception as e:
                st.error(f"Erro geral: {e}")
