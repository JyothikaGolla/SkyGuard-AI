# SkyGuard AI - Training Summary Report

**Training Session:** 20260312_212943

**Date:** 2026-03-12 21:39:52

## Data Statistics

### Raw
- **total_records:** 33568
- **flights:** 17037
- **features:** 38

### Cleaned
- **total_records:** 32687
- **removed_records:** 881
- **removal_percentage:** 2.62%

### Original_distribution
- **LOW_risk:** 21862
- **MEDIUM_risk:** 8340
- **HIGH_risk:** 2485

### Balanced_distribution
- **LOW_risk:** 15303
- **MEDIUM_risk:** 5838
- **HIGH_risk:** 1739

## Preprocessing Pipeline

### data_cleaning
Removed invalid altitudes, velocities, coordinates, and duplicates

### class_balancing
Class weight balancing will be applied during training (no SMOTE - using real data only)

## Model Performance

### Risk_Predictor_XGBoost

**Metrics:**
- **train_accuracy:** 0.9550
- **val_accuracy:** 0.9533
- **test_accuracy:** 0.9519
- **training_samples:** 22880.0000
- **features:** 21.0000

**Configuration:**
- **n_estimators:** 150
- **max_depth:** 3
- **learning_rate:** 0.01
- **smote:** train set only

### Isolation_Forest

**Metrics:**
- **contamination:** 0.1000
- **training_samples:** 32687.0000

**Configuration:**
- **n_estimators:** 100
- **contamination:** 0.1

### LSTM_Autoencoder

**Metrics:**
- **epochs_trained:** 63.0000
- **final_loss:** 0.9084
- **final_val_loss:** 0.5119
- **sequences:** 32678.0000

**Configuration:**
- **sequence_length:** 10
- **n_features:** 8
- **architecture:** 64→32→64 LSTM

### Flight_Clusterer

**Metrics:**
- **n_clusters:** 5.0000
- **training_samples:** 32687.0000
- **pca_components:** 10.0000

**Configuration:**
- **method:** kmeans
- **n_clusters:** 5
- **pca:** True

### Trajectory_Predictor

**Metrics:**
- **epochs_trained:** 91.0000
- **final_loss:** 0.6651
- **final_val_loss:** 1.1626
- **sequences:** 4439.0000

**Configuration:**
- **sequence_length:** 3
- **forecast_steps:** 2
- **architecture:** 128→64 LSTM

