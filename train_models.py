"""
Model Training Script
Run this script to train all ML models with synthetic or real data.

Usage:
    # Train with synthetic data only (default)
    python train_models.py
    
    # Train with 100% real data (class weight balancing will balance classes)
    python train_models.py --use-real-data
    
    # Train and run ablation study
    python train_models.py --use-real-data --run-ablation
"""
import argparse
from src.utils.train_models import train_all_models

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Train ML models for flight risk prediction')
    parser.add_argument('--use-real-data', action='store_true',
                       help='Use 100% real flight data (class weight balancing will balance classes)')
    parser.add_argument('--run-ablation', action='store_true',
                       help='Run ablation study after training completes')
    
    args = parser.parse_args()
    
    # Train models
    session_dir = train_all_models(use_real_data=args.use_real_data)
    
    # Run ablation study if requested
    if args.run_ablation:
        print("\n" + "="*60)
        print("STARTING ABLATION STUDY")
        print("="*60)
        
        try:
            from ablation_study import run_ablation_on_session
            run_ablation_on_session(session_dir)
        except ImportError as e:
            print(f"ERROR: Could not import ablation study: {e}")
            print("Make sure ablation_study.py is in the root directory")
        except Exception as e:
            print(f"ERROR: Ablation study failed: {e}")
            import traceback
            traceback.print_exc()
