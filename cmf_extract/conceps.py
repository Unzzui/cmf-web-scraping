#%% 

import pandas as pd

# importar csv para ver la data

df = pd.read_csv("./data/out_91041000_202412/concepts_91041000_202412.csv")



# filtrar solo en base a la columna Namespace que contenga https://www.cmfchile.cl/cl/fr/ci/2024-01-02

df_filtered = df[df['Namespace'].str.contains("https://www.cmfchile.cl/cl/fr/ci/2024-01-02", na=False)]

df_filtered.head()

# verificar la Label que tiene Revenue
df = df_filtered[df_filtered['Label'].str.contains("Cost of sales", na=False)]

