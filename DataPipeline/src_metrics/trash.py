import pandas as pd

df = pd.read_parquet('~/Downloads/analytical_layer_metrics_final.parquet')


print(df.isnull().sum())

print(df.shape)