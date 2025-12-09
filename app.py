import streamlit as st
import pandas as pd

# Função para limpar valores monetários (R$ 1.500,00 -> 1500.00)
def clean_currency(x):
    if pd.isna(x): return 0.0
    s = str(x).strip()
    # Remove R$ e espaços
    s = s.replace('R$', '').replace(' ', '')
    # Tenta lidar com formato brasileiro
    try:
        if ',' in s and '.' in s:
            # Assume 1.000,00
            s = s.replace('.', '').replace(',', '.')
        elif ',' in s:
            # Assume 1000,00
            s = s.replace(',', '.')
        return float(s)
    except:
        return 0.0

st.set_page_config(page_title="Conferência de Totais", layout="wide")
st.title("📊 Conferência: Arquivo Convênio vs. Arquivo Caixa")

st.markdown("---")

col_conv, col_caixa = st.columns(2)

# ==========================================
# COLUNA 1: ARQUIVO DO CONVÊNIO
# ==========================================
with col_conv:
    st.header("1. Arquivo do Convênio")
    st.info("Carregue o arquivo exportado do sistema (ex: 6430.1.15.csv)")
    
    file_conv = st.file_uploader("Upload Convênio", type=["csv", "xlsx", "xls"], key="u1")
    
    total_convenio = 0.0
    
    if file_conv:
        # Configuração para arquivos com cabeçalho "sujo"
        pular_linhas = st.number_input("Linhas para pular (Cabeçalho)", min_value=0, value=9, help="Ajuste até o cabeçalho correto aparecer")
        sep_csv = st.selectbox("Separador CSV (Convênio)", [";", ","], index=0, key="sep1")
        
        try:
            if file_conv.name.endswith('.csv'):
                df_conv = pd.read_csv(file_conv, sep=sep_csv, skiprows=pular_linhas, on_bad_lines='skip', encoding='latin1')
            else:
                df_conv = pd.read_excel(file_conv, skiprows=pular_linhas)
            
            # Seleção da Coluna de Valor
            st.write("Pré-visualização:")
            st.dataframe(df_conv.head(3), use_container_width=True)
            
            col_valor_conv = st.selectbox("Selecione a coluna de VALOR:", df_conv.columns, key="c1")
            
            # Limpeza e Filtro Anti-Duplicidade (Sub-total)
            # O arquivo de exemplo tem linhas "Sub-total". Vamos tentar remover linhas onde a primeira coluna está vazia ou tem "Sub-total"
            filtrar_subtotal = st.checkbox("Filtrar linhas de 'Sub-total'? (Recomendado)", value=True)
            
            if filtrar_subtotal:
                # Remove linhas onde a primeira coluna é NaN ou contém 'Sub-total'
                col_ref = df_conv.columns[0] # Pega a primeira coluna (geralmente Data)
                df_conv = df_conv.dropna(subset=[col_ref]) 
                # Converte para string para buscar "Sub-total" com segurança
                df_conv = df_conv[~df_conv[col_ref].astype(str).str.contains("Sub-total", case=False, na=False)]
            
            # Calcular Total
            valores_limpos = df_conv[col_valor_conv].apply(clean_currency)
            total_convenio = valores_limpos.sum()
            
            st.metric("Total Convênio (Sistema)", f"R$ {total_convenio:,.2f}")
            
        except Exception as e:
            st.error(f"Erro ao ler arquivo: {e}")

# ==========================================
# COLUNA 2: ARQUIVO DO CAIXA
# ==========================================
with col_caixa:
    st.header("2. Arquivo do Caixa")
    st.info("Carregue sua planilha de controle (ex: Nathy.xlsx)")
    
    file_cx = st.file_uploader("Upload Caixa", type=["xlsx", "xls", "csv"], key="u2")
    
    total_caixa = 0.0
    
    if file_cx:
        # Configuração para pular linhas (no arquivo Nathy parece ter 3 linhas de lixo)
        pular_linhas_cx = st.number_input("Linhas para pular (Caixa)", min_value=0, value=3, key="p2")
        sep_csv_cx = st.selectbox("Separador CSV (Caixa)", [",", ";"], index=0, key="sep2")

        try:
            if file_cx.name.endswith('.csv'):
                df_cx = pd.read_csv(file_cx, sep=sep_csv_cx, skiprows=pular_linhas_cx, encoding='latin1')
            else:
                df_cx = pd.read_excel(file_cx, skiprows=pular_linhas_cx)

            st.write("Pré-visualização:")
            st.dataframe(df_cx.head(3), use_container_width=True)
            
            col_valor_cx = st.selectbox("Selecione a coluna de VALOR:", df_cx.columns, key="c2")
            
            # Selecionar apenas o que é convênio na planilha da Nathy?
            # Se a planilha da Nathy tem dinheiro, cartão e convênio misturado, precisamos filtrar.
            filtrar_tipo = st.checkbox("Filtrar por Tipo na planilha de Caixa?", value=False)
            
            if filtrar_tipo:
                col_tipo_cx = st.selectbox("Coluna de Tipo/Convênio:", df_cx.columns, key="t2")
                tipos = df_cx[col_tipo_cx].astype(str).unique()
                sel_tipos = st.multiselect("Selecione os convênios para somar:", tipos)
                
                if sel_tipos:
                    df_cx = df_cx[df_cx[col_tipo_cx].isin(sel_tipos)]
            
            # Calcular Total
            valores_limpos_cx = df_cx[col_valor_cx].apply(clean_currency)
            total_caixa = valores_limpos_cx.sum()
            
            st.metric("Total Caixa (Selecionado)", f"R$ {total_caixa:,.2f}")

        except Exception as e:
            st.error(f"Erro ao ler arquivo: {e}")

# ==========================================
# COMPARAÇÃO FINAL
# ==========================================
st.markdown("---")
st.header("🏁 Resultado da Conferência")

if total_convenio > 0 and total_caixa > 0:
    diferenca = total_caixa - total_convenio
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Esperado (Convênio)", f"R$ {total_convenio:,.2f}")
    c2.metric("Realizado (Caixa)", f"R$ {total_caixa:,.2f}")
    c3.metric("Diferença", f"R$ {diferenca:,.2f}", delta=diferenca)
    
    if abs(diferenca) < 1.0:
        st.success("✅ Os valores batem! (Diferença irrelevante)")
    elif diferenca > 0:
        st.warning("⚠️ O Caixa tem MAIS valor que o relatório do convênio. Verifique se somou particulares indevidamente.")
    else:
        st.error("❌ O Caixa tem MENOS valor que o relatório. Falta lançar algo ou glosa?")
else:
    st.write("Aguardando carregamento e processamento de ambos os arquivos...")
