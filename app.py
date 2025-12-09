import streamlit as st
import pandas as pd
import io
import re

# --- Configuração da Página ---
st.set_page_config(page_title="Conferência de Caixa", layout="wide")

# --- Funções Auxiliares ---

def limpar_valor(valor_str):
    """
    Transforma string de dinheiro em float.
    Aceita: "1250,00", "R$ 1.250,00", "1.250.00", etc.
    """
    if pd.isna(valor_str): return 0.0
    val = str(valor_str).strip()
    val = val.replace('R$', '').strip()
    
    # Se valor for vazio ou traço
    if not val or val == '-': return 0.0
    
    try:
        # Tenta converter direto (formato internacional)
        return float(val)
    except ValueError:
        pass

    # Lógica para formato brasileiro (inverte ponto e vírgula)
    # Remove ponto de milhar se existir
    if '.' in val and ',' in val:
        val = val.replace('.', '').replace(',', '.')
    elif ',' in val:
        val = val.replace(',', '.')
    
    return pd.to_numeric(val, errors='coerce')

def extrair_os_do_nome(texto):
    """
    Pega a OS do começo do nome.
    Ex: "001-67494-55 ANA JULIA..." -> "001-67494-55"
    """
    texto = str(texto).strip()
    # Regex: Procura padrão de numeros e traços no inicio
    match = re.search(r'^([\d-]+)', texto)
    if match:
        return match.group(1).strip()
    return texto

def ler_arquivo_resiliente(uploaded_file):
    """Lê o arquivo tentando diferentes codificações e retorna as linhas."""
    bytes_data = uploaded_file.getvalue()
    encodings = ['utf-8', 'latin1', 'cp1252']
    
    for enc in encodings:
        try:
            texto = bytes_data.decode(enc)
            return texto.splitlines()
        except UnicodeDecodeError:
            continue
    
    # Se falhar tudo, tenta decodificar ignorando erros
    return bytes_data.decode('utf-8', errors='ignore').splitlines()

def processar_extrato(uploaded_file):
    """Lê os arquivos de Extrato/Convênio (Quinzena)"""
    try:
        linhas = ler_arquivo_resiliente(uploaded_file)
        
        # 1. Tenta extrair a área da linha 8 (índice 8 = linha B9 do Excel)
        area_nome = "Desconhecido"
        if len(linhas) > 8:
            partes = linhas[8].split(';')
            if len(partes) > 1:
                area_nome = partes[1].strip()

        # 2. Acha onde começa a tabela de dados
        inicio_dados = 0
        for i, linha in enumerate(linhas):
            if "Data;Nome" in linha or "Cod O.S." in linha:
                inicio_dados = i
                break
        
        # 3. Lê o CSV da memória
        csv_io = io.StringIO("\n".join(linhas[inicio_dados:]))
        df = pd.read_csv(csv_io, sep=';', dtype=str)

        # 4. Limpeza
        if 'Data' in df.columns:
            df = df.dropna(subset=['Data']) # Remove linhas vazias
            df = df[df['Data'] != 'Sub-total'] # Remove sub-total
            df['Area'] = area_nome
            
            # Padronizar coluna de OS
            col_os = 'Cod O.S.' if 'Cod O.S.' in df.columns else 'OS'
            if col_os in df.columns:
                df['OS'] = df[col_os]
            else:
                df['OS'] = 'N/A'

            # Padronizar Valor
            if 'Valor' in df.columns:
                df['Valor_Extrato'] = df['Valor'].apply(limpar_valor)
            else:
                df['Valor_Extrato'] = 0.0
            
            return df[['Data', 'OS', 'Nome', 'Valor_Extrato', 'Area']]
        return pd.DataFrame()

    except Exception as e:
        st.error(f"Erro ao processar extrato {uploaded_file.name}: {e}")
        return pd.DataFrame()

def processar_caixa(uploaded_file):
    """
    Lê os arquivos de Caixa (Isis, Nathy, etc.)
    Lógica 'blindada' para encontrar cabeçalho e separador.
    """
    try:
        linhas = ler_arquivo_resiliente(uploaded_file)
        
        # 1. Encontrar a linha de cabeçalho
        indice_cabecalho = -1
        sep_usado = ','
        
        for i, linha in enumerate(linhas):
            # Normaliza a linha para maiúsculo para buscar palavras chave
            linha_upper = linha.upper()
            
            # Verifica se tem palavras chaves de cabeçalho
            if "DATA" in linha_upper and ("VALOR" in linha_upper or "NOME" in linha_upper):
                # Achamos! Agora vamos descobrir o separador desta linha específica
                if linha.count(';') > linha.count(','):
                    sep_usado = ';'
                else:
                    sep_usado = ','
                
                indice_cabecalho = i
                break
        
        if indice_cabecalho == -1:
            st.warning(f"⚠️ Cabeçalho (DATA/VALOR) não encontrado em {uploaded_file.name}. Verifique se o arquivo está correto.")
            return pd.DataFrame()

        # 2. Isolar os dados do cabeçalho para baixo
        conteudo_csv = "\n".join(linhas[indice_cabecalho:])
        csv_io = io.StringIO(conteudo_csv)
        
        # 3. Ler com Pandas
        # on_bad_lines='skip' ignora linhas que tenham colunas a mais (rodapés, anotações)
        try:
            df = pd.read_csv(csv_io, sep=sep_usado, dtype=str, on_bad_lines='skip')
        except:
            # Fallback para versões antigas do pandas
            csv_io.seek(0)
            df = pd.read_csv(csv_io, sep=sep_usado, dtype=str, error_bad_lines=False)

        # 4. Normalizar nomes das colunas (remove espaços, acentos e põe maiúsculo)
        # Ex: " VALOR " vira "VALOR", "CONVÊNIO" vira "CONVENIO"
        df.columns = [
            c.strip().upper().replace('Ê', 'E').replace('Ç', 'C').replace('Ã', 'A') 
            for c in df.columns
        ]

        # 5. Identificar Colunas Dinamicamente
        # Procura qual coluna corresponde ao Nome e ao Valor
        col_nome = next((c for c in df.columns if 'NOME' in c), None)
        col_valor = next((c for c in df.columns if 'VALOR' in c), None)

        if col_nome and col_valor:
            # Processar OS e Valor
            df['OS_Caixa'] = df[col_nome].apply(extrair_os_do_nome)
            df['Valor_Caixa'] = df[col_valor].apply(limpar_valor)
            df['Arquivo_Caixa'] = uploaded_file.name
            
            # Remove linhas que não são dados reais (ex: linha vazia "validando" formatação)
            # Removemos se 'Valor' for 0 ou NaN E 'Nome' estiver vazio
            df = df.dropna(subset=[col_nome]) 
            df = df[df['Valor_Caixa'].notna()]
            
            return df[['OS_Caixa', col_nome, 'Valor_Caixa', 'Arquivo_Caixa']]
        else:
            st.error(f"Colunas NOME ou VALOR não identificadas em {uploaded_file.name}. Colunas achadas: {df.columns.tolist()}")
            return pd.DataFrame()

    except Exception as e:
        st.error(f"Erro técnico ao ler {uploaded_file.name}: {str(e)}")
        return pd.DataFrame()

# --- Interface Principal ---

st.title("💰 Conferência de Caixa - Versão Final")

# SEÇÃO 1: EXTRATOS
st.header("1. Importar Extratos (Base de Dados)")
files_extratos = st.file_uploader("Upload dos arquivos de Extrato", accept_multiple_files=True, key="extratos")

df_base = pd.DataFrame()

if files_extratos:
    lista_dfs = []
    for f in files_extratos:
        df_temp = processar_extrato(f)
        if not df_temp.empty:
            lista_dfs.append(df_temp)
    
    if lista_dfs:
        df_base = pd.concat(lista_dfs, ignore_index=True)
        # Garante que a OS está limpa (sem espaços nas pontas)
        df_base['OS'] = df_base['OS'].str.strip()
        st.success(f"Base de Dados carregada com {len(df_base)} registros.")
        with st.expander("Ver Base Carregada"):
            st.dataframe(df_base.head())

# SEÇÃO 2: CAIXAS
st.header("2. Importar Caixas (Isis, Ivone, etc.)")
files_caixa = st.file_uploader("Upload dos arquivos de Caixa", accept_multiple_files=True, key="caixa")

if files_caixa and not df_base.empty:
    lista_caixas = []
    for f in files_caixa:
        df_cx = processar_caixa(f)
        if not df_cx.empty:
            lista_caixas.append(df_cx)
    
    if lista_caixas:
        df_caixa_total = pd.concat(lista_caixas, ignore_index=True)
        df_caixa_total['OS_Caixa'] = df_caixa_total['OS_Caixa'].str.strip()
        
        st.divider()
        st.subheader("📊 Relatório de Conferência")
        
        # --- CRUZAMENTO DE DADOS ---
        # Faz o merge (join) entre Caixa e Base
        df_final = pd.merge(
            df_caixa_total,
            df_base,
            left_on='OS_Caixa',
            right_on='OS',
            how='left',
            indicator=True
        )
        
        # Filtros de Resultado
        
        # 1. OK (Encontrado e Valor Igual - tolerância de 5 centavos)
        ok_mask = (df_final['_merge'] == 'both') & (abs(df_final['Valor_Caixa'] - df_final['Valor_Extrato']) <= 0.05)
        df_ok = df_final[ok_mask]
        
        # 2. DIVERGENTE (Encontrado mas valor diferente)
        div_mask = (df_final['_merge'] == 'both') & (abs(df_final['Valor_Caixa'] - df_final['Valor_Extrato']) > 0.05)
        df_divergente = df_final[div_mask].copy()
        if not df_divergente.empty:
            df_divergente['Diferença'] = df_divergente['Valor_Caixa'] - df_divergente['Valor_Extrato']
        
        # 3. NÃO ENCONTRADO (Está no caixa mas não na base)
        df_nao_enc = df_final[df_final['_merge'] == 'left_only']
        
        # 4. DUPLICADOS (Mesma OS duas vezes no caixa)
        duplicados = df_caixa_total[df_caixa_total.duplicated(subset=['OS_Caixa'], keep=False)]

        # --- EXIBIÇÃO ---
        tab1, tab2, tab3, tab4 = st.tabs(["✅ Validados", "⚠️ Diferença de Valor", "❌ Não Encontrados", "👀 Duplicidade"])
        
        with tab1:
            st.metric("Total Validados", len(df_ok))
            st.dataframe(df_ok[['OS_Caixa', 'Nome', 'Area', 'Valor_Caixa']])
        
        with tab2:
            st.metric("Com Diferença", len(df_divergente))
            if not df_divergente.empty:
                st.dataframe(df_divergente[['OS_Caixa', 'Nome', 'Area', 'Valor_Caixa', 'Valor_Extrato', 'Diferença']])
            else:
                st.success("Nenhuma divergência de valor encontrada.")
                
        with tab3:
            st.metric("Não Encontrados na Base", len(df_nao_enc))
            st.write("Estes itens constam no caixa mas não achamos o extrato correspondente:")
            st.dataframe(df_nao_enc[['OS_Caixa', 'Arquivo_Caixa', 'Valor_Caixa']])
            
        with tab4:
            if not duplicados.empty:
                st.warning("As seguintes OS aparecem mais de uma vez nos arquivos de caixa:")
                st.dataframe(duplicados.sort_values('OS_Caixa'))
            else:
                st.success("Nenhuma OS duplicada nos caixas.")

elif files_caixa and df_base.empty:
    st.warning("⚠️ Por favor, faça o upload dos EXTRATOS (Passo 1) primeiro.")
