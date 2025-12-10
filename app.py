import streamlit as st
import pandas as pd
from io import StringIO

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Sistema de Gestão Financeira & RH", layout="wide")

# --- ESTILIZAÇÃO CSS ---
st.markdown("""
<style>
    .dataframe {font-size: 13px !important;}
    th, td {text-align: center !important;}
    th {background-color: #f0f2f6;}
    /* Ajuste para as abas */
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #f0f2f6; border-radius: 4px 4px 0px 0px; gap: 1px; padding-top: 10px; padding-bottom: 10px; }
    .stTabs [aria-selected="true"] { background-color: #ffffff; border-bottom: 2px solid #ff4b4b; }
</style>
""", unsafe_allow_html=True)

st.title("📊 Painel de Gestão: Financeiro & RH")

# --- FUNÇÕES UTILITÁRIAS ---
def clean_currency(x):
    """Converte strings de moeda (ex: '1.234,56') para float."""
    if isinstance(x, str):
        # Remove ponto de milhar e substitui vírgula decimal por ponto
        return float(x.replace('.', '').replace(',', '.'))
    return float(x)

# --- CRIAÇÃO DAS ABAS ---
tab_caixa, tab_audit = st.tabs(["💰 Conferência de Caixa", "📋 Auditoria Salarial (RH)"])

# ==============================================================================
# ABA 1: CONFERÊNCIA DE CAIXA
# ==============================================================================
with tab_caixa:
    st.header("Conferência de Caixa - Consolidação de Extratos")
    st.markdown("---")

    uploaded_files_caixa = st.file_uploader(
        "Faça o upload dos arquivos CSV (Extratos)", 
        accept_multiple_files=True, 
        type="csv",
        key="upload_caixa"
    )

    if uploaded_files_caixa:
        all_data = []
        
        for uploaded_file in uploaded_files_caixa:
            try:
                # Ler o conteúdo do arquivo com encoding latin1 (padrão de sistemas antigos)
                stringio = StringIO(uploaded_file.getvalue().decode("latin1"))
                lines = stringio.readlines()
                
                # Pula arquivos que não têm cabeçalho suficiente
                if len(lines) < 11:
                    continue

                # 1. Extrair Credencial (Geralmente na linha 9, coluna B)
                try:
                    line_b9 = lines[8].strip().split(';')
                    if len(line_b9) > 1:
                        credencial = line_b9[1]
                    else:
                        credencial = "Desconhecido"
                except Exception:
                    credencial = "Erro Leitura"

                # 2. Ler os dados (Cabeçalho costuma estar na linha 11)
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
            # Juntar todos os dataframes
            df_final = pd.concat(all_data, ignore_index=True)

            # 4. Agrupar por Credencial e OS (Somar Valor)
            # Agrupa para somar valores de mesma OS na mesma credencial
            df_grouped = df_final.groupby(['Credencial', 'Cod O.S.', 'Nome'])['Valor'].sum().reset_index()

            st.success(f"{len(uploaded_files_caixa)} arquivos processados com sucesso!")
            
            # Layout de colunas para Resumo e Botão de Download
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.subheader("Resumo por Área (Credencial)")
                resumo_area = df_grouped.groupby('Credencial')['Valor'].sum().reset_index()
                st.dataframe(resumo_area.style.format({"Valor": "R$ {:,.2f}"}), use_container_width=True)

            with col2:
                st.subheader("Exportação")
                st.write("Baixe a planilha completa para análise detalhada.")
                csv = df_grouped.to_csv(index=False, sep=';', decimal=',').encode('latin1')
                st.download_button(
                    label="📥 Baixar Planilha Consolidada (CSV)",
                    data=csv,
                    file_name="extratos_consolidados.csv",
                    mime="text/csv",
                )

            st.markdown("### Detalhamento por O.S.")
            st.dataframe(df_grouped.style.format({"Valor": "R$ {:,.2f}"}), use_container_width=True)
            
        else:
            st.warning("Nenhum dado válido foi encontrado nos arquivos enviados.")

# ==============================================================================
# ABA 2: AUDITORIA SALARIAL
# ==============================================================================
with tab_audit:
    st.header("Análise Crítica: Auditoria Trabalhista (2025)")
    st.markdown("---")
    
    # Texto formatado com base na análise do documento
    st.markdown("""
    ### **RELATÓRIO DE AUDITORIA INTERNA TRABALHISTA – AC 970**
    **Referência:** Exercício 2025 (Janeiro a Dezembro)  
    **Data:** 09 de Dezembro de 2025

    #### 1. OBJETIVO
    O presente relatório apresenta os resultados da auditoria sobre a folha de pagamentos, verificando a conformidade dos reajustes salariais (dissídios) e identificando inconsistências financeiras.

    #### 2. CONSTATAÇÕES POR CATEGORIA SINDICAL

    **2.1. Sindicato da Saúde de Rio Claro**
    * **Ausência de Aplicação do Reajuste (Competência 10/2025):** Identificada em 11 colaboradores (incluindo *Aline Moraes, Caroline Alves, Elaine Cristina*), que não receberam o dissídio devido.
    * **Pagamentos Realizados a Maior (Competência 08/2025):** Diversos colaboradores (ex: *Flavia Furlan, Denise Gemina*) receberam diferenças de dissídio acima do cálculo correto, gerando um crédito indevido (passivo para o colaborador).
    * **Pagamento Indevido:** *Vanessa Alves de Souza* teve dissídio aplicado incorretamente, pois sua promoção ocorreu após a data-base.

    **2.2. Enfermagem (SEESP)**
    * **Situação Crítica:** Categoria sem reajuste desde 2023 devido a falhas no acompanhamento sindical.
    * **Passivo Acumulado a Regularizar:**
        * **Suelen:** R$ 7.853,31
        * **Elvira:** R$ 7.288,70

    **2.3. Farmacêuticos (SINFAR)**
    * **Vanusa:** Pendente reajuste de 10/2024 a 02/2025 (Total: R$ 709,35).
    * **Juliana Brito:** Pendente diferença residual de 09/2025 (Total: R$ 141,87).

    **2.4. Biomédicos (SINBIESP)**
    * Ausência de reajuste em 10/2025 para **Lucas** (R$ 212,96) e **Rodrigo** (R$ 349,08).

    ---

    #### 3. RESUMO FINANCEIRO
    | Categoria | Valor (R$) | Descrição |
    | :--- | :--- | :--- |
    | **A Regularizar (Pagar)** | **R$ 18.323,90** | Valor total devido aos funcionários em Dez/2025. |
    | **Pago Indevidamente** | **R$ 1.429,51** | Valor pago a maior (erro de cálculo anterior). |

    #### 4. CAUSA RAIZ E PLANO DE AÇÃO
    **Causas:** Descontinuidade no monitoramento das convenções coletivas (falha de comunicação com contabilidade externa e controle interno).
    
    **Ações Imediatas:**
    1.  **Monitoramento:** Implementar alertas automáticos no sistema *Sysquali* (30 dias antes da data-base).
    2.  **Regularização:** Processar os pagamentos pendentes na folha de Dezembro/2025.
    3.  **Gestão de Passivo:** Analisar juridicamente a viabilidade de estorno ou absorção dos valores pagos a maior.
    """)
