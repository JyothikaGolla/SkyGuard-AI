import joblib

# Check ablation study features
print("=" * 70)
print("ABLATION STUDY - FEATURE COMPARISON")
print("=" * 70)

# Load ablation study (with removed features)
ablation_data = joblib.load('training_results/session_20260223_005834/training_data.pkl')
print("\n📋 Session 20260223_005834 (ABLATION - Reduced Features):")
print(f"Total features: {len(ablation_data['feature_names'])}")
print("\nFeatures used:")
for i, feat in enumerate(ablation_data['feature_names'], 1):
    print(f"  {i}. {feat}")

# Load baseline (with all features)
baseline_data = joblib.load('training_results/session_20260223_001910/training_data.pkl')
print(f"\n📋 Session 20260223_001910 (BASELINE - All Features):")
print(f"Total features: {len(baseline_data['feature_names'])}")
print("\nFeatures used:")
for i, feat in enumerate(baseline_data['feature_names'], 1):
    print(f"  {i}. {feat}")

# Compare
removed_features = set(baseline_data['feature_names']) - set(ablation_data['feature_names'])
print(f"\n🚫 REMOVED FEATURES ({len(removed_features)}):")
for feat in sorted(removed_features):
    print(f"  - {feat}")

print("\n" + "=" * 70)
print("RESULT COMPARISON:")
print("=" * 70)
print(f"Baseline Accuracy:  96.25% (with ALL features)")
print(f"Ablation Accuracy:  70.00% (with REDUCED features)")
print(f"Performance Drop:  -26.25%")
print("\n" + "=" * 70)
print("CONCLUSION:")
print("=" * 70)
print("❌ SIGNIFICANT ACCURACY DROP when removing rule-based features!")
print("   The model WAS learning from the direct rule components.")
print("\n   This indicates:")
print("   • Model memorized/learned rule logic rather than true patterns")
print("   • Risk labels are highly correlated with rule-based features")
print("   • Need expert-labeled data for genuine pattern learning")
