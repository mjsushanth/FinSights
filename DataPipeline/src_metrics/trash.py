import pandas as pd

df = pd.read_parquet('~/Downloads/analytical_layer_metrics_final_test.parquet')


print(df.isnull().sum())