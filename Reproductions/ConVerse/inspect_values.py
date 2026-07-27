import pandas as pd
p='reproduction_outputs/unified_baseline_gpt-5.csv'
df=pd.read_csv(p)
for col in ['security_attack_success','security_action_requested','security_action_confirmed','privacy_leaked_information','utility_average_rating']:
    print('\n'+col)
    if col in df.columns:
        print(df[col].value_counts(dropna=False).head(30))
    else:
        print('missing')
print('\ncolumns', df.columns.tolist()[:120])
