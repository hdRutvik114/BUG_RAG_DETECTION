import pandas as pd
import numpy as np
import os

df = pd.read_csv('dataset_enriched_v3.csv')

print('=== DATASET QUALITY AUDIT ===')
print(f'Total Rows: {len(df)}')
print(f'Total Columns: {len(df.columns)}')

print('\n--- Missing Values ---')
nulls = df.isnull().sum()
print(nulls[nulls > 0] if (nulls > 0).any() else "No missing values!")

print('\n--- Gemini Validation Status ---')
if 'gemini_validation_status' in df:
    print(df['gemini_validation_status'].value_counts())

print('\n--- AST Tier Distribution ---')
if 'ast_tier' in df:
    print(df['ast_tier'].value_counts())

print('\n--- Confidence Scores ---')
if 'confidence_score' in df:
    print(f"Mean: {df['confidence_score'].mean():.3f}")
    print(f"Min:  {df['confidence_score'].min():.3f}")
    print(f"Max:  {df['confidence_score'].max():.3f}")

print('\n--- Gemini Confidence Scores ---')
if 'gemini_confidence' in df:
    print(f"Mean: {df['gemini_confidence'].mean():.3f}")
    print(f"Min:  {df['gemini_confidence'].min():.3f}")
    print(f"Max:  {df['gemini_confidence'].max():.3f}")

print('\n--- Data Integrity Checks ---')
dup_buggy = df['buggy_code'].duplicated().sum()
identical_pairs = (df['buggy_code'] == df['fixed_code']).sum()
print(f"Duplicate buggy code snippets: {dup_buggy}")
print(f"Identical buggy vs fixed code (invalid 0-diff): {identical_pairs}")

print('\n--- Code Length Statistics (Characters) ---')
df['buggy_len'] = df['buggy_code'].astype(str).str.len()
df['fixed_len'] = df['fixed_code'].astype(str).str.len()
print(f"Buggy Code Length  -> Mean: {df['buggy_len'].mean():.0f}, Min: {df['buggy_len'].min()}, Max: {df['buggy_len'].max()}")
print(f"Fixed Code Length  -> Mean: {df['fixed_len'].mean():.0f}, Min: {df['fixed_len'].min()}, Max: {df['fixed_len'].max()}")
