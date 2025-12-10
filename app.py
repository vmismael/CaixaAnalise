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
# ABA 1: CONSOLIDAÇÃO (Seu código original)
# ==============================================================================
with tab1:
    st.header("Consolidação de Extratos")
    st.markdown("Faça o upload de múltiplos arquivos CSV de extrato para gerar um relatório unificado.")

    uploaded_files = st.file_uploader(
        "Faça o upload dos arquivos CSV (Extratos)", 
        accept_multiple_files=True, 
        type="csv",
        key="upload_tab1"
    )

    if uploaded_files:
        all_data = []
        
        for uploaded_file in uploaded_files:
            try:
                # Ler o conteúdo do arquivo com encoding 'latin1'
                stringio = StringIO(uploaded_file.getvalue().decode("latin1"))
                lines = stringio.readlines()
                
                if len(lines) < 11:
                    continue

                # 1. Extrair Credencial
                try:
                    line_b9 = lines[8].strip().split(';')
                    if len(line_b9) > 1:
                        credencial = line_b9[1]
                    else:
                        credencial = "Desconhecido"
                except Exception:
                    credencial = "Erro Leitura"

                # 2. Ler os dados
                data_content = "".join(lines[10:])
                df = pd.read_csv(StringIO(data_content), sep=';')
                
                if df.empty:
                    continue

                # 3. Limpeza de Dados
                if 'Data' in df.columns:
                    df = df[df['Data'] != 'Sub-total']
                
                if 'Cod O.S.' in df.columns:
                    df = df.dropna(subset=['Cod O.S.'])

                df['Credencial'] = credencial
                
                if 'Valor' in df.columns:
                    df['Valor'] = df['Valor'].apply(clean_currency)
                
                all_data.append(df)
                
            except Exception as e:
                st.error(f"Erro ao processar arquivo {uploaded_file.name}: {e}")

        if all_data:
            df_final = pd.concat(all_data, ignore_index=True)

            # Agrupar
            df_grouped = df_final.groupby(['Credencial', 'Cod O.S.', 'Nome'])['Valor'].sum().reset_index()

            st.success(f"{len(uploaded_files)} arquivos processados com sucesso!")
            
            # Resumo por Área
            st.subheader("Resumo por Área (Credencial)")
            resumo_area = df_grouped.groupby('Credencial')['Valor'].sum().reset_index()
            st.dataframe(resumo_area.style.format({"Valor": "R$ {:,.2f}"}))

            # Detalhado
            st.subheader("Detalhamento por OS")
            st.dataframe(df_grouped.style.format({"Valor": "R$ {:,.2f}"}))
            
            # Download
            csv = df_grouped.to_csv(index=False, sep=';', decimal=',').encode('latin1')
            st.download_button(
                label="Baixar Planilha Consolidada",
                data=csv,
                file_name="extratos_consolidados.csv",
                mime="text/csv",
            )
            
            # Salvar no session_state para uso opcional na outra aba
            st.session_state['df_extratos_consolidado'] = df_grouped
            
        else:
            st.warning("Nenhum dado válido foi encontrado nos arquivos enviados.")

# ==============================================================================
# ABA 2: CONFERÊNCIA (O novo código)
# ==============================================================================
with tab2:
    st.header("Conferência: Caixas Individuais vs Resumo")
    st.markdown("""
    Compare os **arquivos de Caixa (Excel)** com o **Resumo Consolidado (CSV)**.
    O sistema extrai a OS do nome no Excel e compara os valores.
    """)
    
    col_up1, col_up2 = st.columns(2)
    
    with col_up1:
        file_csv_conf = st.file_uploader("1. Carregar Resumo (CSV)", type=["csv"], key="upload_csv_tab2")
        # Opção de usar o arquivo gerado na Aba 1
        if 'df_extratos_consolidado' in st.session_state and not file_csv_conf:
            st.info("💡 Você pode usar o arquivo gerado na Aba 1 ou fazer upload de um novo.")
            if st.checkbox("Usar Consolidação gerada na Aba 1"):
                df_resumo_input = st.session_state['df_extratos_consolidado']
            else:
                df_resumo_input = None
        elif file_csv_conf:
            try:
                df_resumo_input = pd.read_csv(file_csv_conf, sep=';', encoding='latin-1')
            except:
                df_resumo_input = pd.read_csv(file_csv_conf, sep=';', encoding='utf-8')
        else:
            df_resumo_input = None

    with col_up2:
        files_excel_conf = st.file_uploader("2. Carregar Caixas (Excel)", type=["xlsx"], accept_multiple_files=True, key="upload_excel_tab2")

    # Processamento da Conferência
    if df_resumo_input is not None and files_excel_conf:
        
        # Preparar dados do CSV (Resumo)
        df_resumo = df_resumo_input.copy()
        
        # Tentar identificar colunas automaticamente
        cols_os = [c for c in df_resumo.columns if 'O.S.' in c or 'OS' in c]
        cols_val = [c for c in df_resumo.columns if 'Valor' in c or 'VALOR' in c]

        if not cols_os or not cols_val:
            st.error("Não foi possível identificar as colunas 'OS' e 'Valor' no CSV.")
        else:
            col_os_csv = cols_os[0]
            col_val_csv = cols_val[0]

            df_resumo['OS_Limpa'] = df_resumo[col_os_csv].astype(str).str.strip()
            df_resumo['Valor_Limpo'] = df_resumo[col_val_csv].apply(clean_currency)
            
            # Dicionário de referência {OS: Valor}
            dict_resumo = pd.Series(df_resumo.Valor_Limpo.values, index=df_resumo.OS_Limpa).to_dict()
            
            st.success(f"CSV de Referência carregado: {len(df_resumo)} linhas.")
            st.divider()

            # Seleção da Aba do Excel
            try:
                xls_temp = pd.ExcelFile(files_excel_conf[0])
                sheet_names = xls_temp.sheet_names
                selected_sheet = st.selectbox("📅 Selecione a Aba do Excel (ex: OUTUBRO 2):", sheet_names)
                
                if st.button("Iniciar Conferência", type="primary"):
                    
                    st.write(f"### Resultados da Análise: {selected_sheet}")
                    
                    all_missing_in_csv = [] 
                    all_os_processed_in_excel = set()

                    for uploaded_file in files_excel_conf:
                        try:
                            # Ler a aba e encontrar cabeçalho
                            df_temp = pd.read_excel(uploaded_file, sheet_name=selected_sheet, header=None)
                            header_row_idx = find_header_row(df_temp)
                            
                            df_caixa = pd.read_excel(uploaded_file, sheet_name=selected_sheet, header=header_row_idx)
                            df_caixa.columns = [str(c).upper().strip() for c in df_caixa.columns]
                            
                            if 'NOME' not in df_caixa.columns or 'VALOR' not in df_caixa.columns:
                                st.warning(f"⚠️ {uploaded_file.name}: Colunas 'NOME' ou 'VALOR' não encontradas.")
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
                                            divergencias.append({
                                                "OS": os_encontrada,
                                                "Nome": nome_completo,
                                                "Valor Caixa": valor_caixa,
                                                "Valor Resumo": valor_resumo,
                                                "Diferença": diferenca
                                            })
                                        else:
                                            conferem.append(os_encontrada)
                                    else:
                                        # No Excel, mas não no CSV
                                        faltantes_no_csv.append({
                                            "OS": os_encontrada,
                                            "Nome": nome_completo,
                                            "Valor": valor_caixa
                                        })

                            # Exibição por arquivo
                            with st.expander(f"📁 {uploaded_file.name}", expanded=True):
                                c1, c2, c3 = st.columns(3)
                                c1.metric("Conferem", len(conferem))
                                c2.metric("Divergentes", len(divergencias))
                                c3.metric("Só no Caixa (Faltam no CSV)", len(faltantes_no_csv))

                                if divergencias:
                                    st.error("🚨 **Divergências de Valor:**")
                                    st.dataframe(pd.DataFrame(divergencias).style.format({
                                        "Valor Caixa": "R$ {:,.2f}", "Valor Resumo": "R$ {:,.2f}", "Diferença": "R$ {:,.2f}"
                                    }))
                                
                                if faltantes_no_csv:
                                    st.warning("❌ **Constam no Caixa, mas NÃO no Resumo:**")
                                    st.dataframe(pd.DataFrame(faltantes_no_csv))
                        
                        except Exception as e:
                            st.error(f"Erro ao ler {uploaded_file.name}: verifique se a aba '{selected_sheet}' existe neste arquivo.")

                    # Análise Inversa (O que tem no CSV e ninguém lançou no Excel)
                    st.divider()
                    st.subheader("🔍 Auditoria Inversa")
                    st.markdown("OS que constam no **CSV Resumo** mas **não apareceram** em nenhum Excel selecionado.")
                    
                    missing_in_excel = []
                    for os_csv, val_csv in dict_resumo.items():
                        if os_csv not in all_os_processed_in_excel:
                            missing_in_excel.append({"OS": os_csv, "Valor CSV": val_csv})
                    
                    if missing_in_excel:
                        st.dataframe(pd.DataFrame(missing_in_excel))
                    else:
                        st.success("Tudo certo! Todas as OS do CSV foram encontradas nos caixas.")

            except Exception as e:
                st.error(f"Erro ao ler arquivo Excel inicial: {e}")
