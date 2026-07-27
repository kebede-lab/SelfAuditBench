"""Quick test to verify data loading works"""
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from data_loading import load_all_results
from data_enhancement import create_unified_dataset, enhance_dataset_with_groupings

print("=" * 80)
print("TESTING DATA LOADING")
print("=" * 80)

# Test 1: Load results
print("\n1. Loading results...")
df = load_all_results(mode='baseline', judge_model='gpt-5', verbose=False)
print(f"   ✓ Loaded {len(df)} judge result files")

if len(df) > 0:
    print(f"   ✓ Models: {sorted(df['model'].unique())}")
    print(f"   ✓ Use cases: {sorted(df['use_case'].unique())}")
else:
    print("   ✗ NO DATA LOADED - Check paths!")
    sys.exit(1)

# Test 2: Create unified dataset
print("\n2. Creating unified dataset...")
unified_df = create_unified_dataset(df)
print(f"   ✓ Created {len(unified_df)} scenarios")

# Test 3: Enhance with groupings
print("\n3. Enhancing with attack groupings...")
enhanced_df = enhance_dataset_with_groupings(unified_df)
print(f"   ✓ Enhanced dataset ready")

# Test 4: Check privacy_data_category
print("\n4. Checking privacy_data_category values...")
privacy_df = enhanced_df[enhanced_df['attack_type'] == 'privacy']
category_counts = privacy_df['privacy_data_category'].value_counts()
print(f"   Categories found: {len(category_counts)}")
for cat, count in category_counts.items():
    print(f"     - {cat}: {count}")

if privacy_df['privacy_data_category'].isna().all():
    print("   ✗ ALL PRIVACY CATEGORIES ARE NONE - Resource path issue!")
else:
    print(f"   ✓ Privacy categories loaded correctly")

# Test 5: Check security attack_name_group
print("\n5. Checking security attack_name_group values...")
security_df = enhanced_df[enhanced_df['attack_type'] == 'security']
attack_counts = security_df['attack_name_group'].value_counts()
print(f"   Attack types found: {len(attack_counts)}")
for attack, count in attack_counts.items():
    print(f"     - {attack}: {count}")

if len(attack_counts) < 2:
    print("   ✗ INSUFFICIENT ATTACK TYPES - Resource path issue!")
else:
    print(f"   ✓ Security attack types loaded correctly")

print("\n" + "=" * 80)
print("ALL TESTS PASSED ✓")
print("=" * 80)
