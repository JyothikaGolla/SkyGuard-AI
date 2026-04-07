"""
Training results tracking and persistence.
Saves all training metrics, configurations, and model performance.
"""
import json
import os
from datetime import datetime
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend to prevent threading issues
import matplotlib.pyplot as plt
import seaborn as sns


class TrainingLogger:
    """Logs and saves all training results."""
    
    def __init__(self, results_dir='training_results'):
        """
        Initialize training logger.
        
        Args:
            results_dir: Directory to save results
        """
        self.results_dir = results_dir
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.session_dir = os.path.join(results_dir, f'session_{self.timestamp}')
        os.makedirs(self.session_dir, exist_ok=True)
        
        self.results = {
            'timestamp': self.timestamp,
            'models': {},
            'data_stats': {},
            'preprocessing': {}
        }
    
    def log_data_stats(self, stage, stats):
        """
        Log data statistics at different stages.
        
        Args:
            stage: Stage name (e.g., 'raw', 'cleaned', 'balanced')
            stats: Dictionary of statistics
        """
        self.results['data_stats'][stage] = stats
        print(f"\n=== Data Statistics: {stage} ===")
        for key, value in stats.items():
            print(f"{key}: {value}")
    
    def log_preprocessing(self, step, info):
        """
        Log preprocessing step information.
        
        Args:
            step: Preprocessing step name
            info: Information about the step
        """
        self.results['preprocessing'][step] = info
    
    def log_model_results(self, model_name, metrics, config=None):
        """
        Log model training results.
        
        Args:
            model_name: Name of the model
            metrics: Dictionary of metrics
            config: Model configuration
        """
        self.results['models'][model_name] = {
            'metrics': metrics,
            'config': config or {}
        }
        
        print(f"\n=== {model_name} Results ===")
        for key, value in metrics.items():
            if isinstance(value, float):
                print(f"{key}: {value:.4f}")
            else:
                print(f"{key}:")
                print(value)
    
    def save_results(self):
        """Save all results to JSON file."""
        results_file = os.path.join(self.session_dir, 'training_results.json')
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        print(f"\n✓ Training results saved to {results_file}")
        return results_file
    
    def save_classification_report(self, model_name, report_text):
        """Save classification report as text file."""
        report_file = os.path.join(self.session_dir, f'{model_name}_classification_report.txt')
        with open(report_file, 'w') as f:
            f.write(report_text)
        print(f"✓ Classification report saved to {report_file}")
    
    def save_confusion_matrix(self, model_name, cm, class_names):
        """
        Save confusion matrix as image.
        
        Args:
            model_name: Name of the model
            cm: Confusion matrix array
            class_names: List of class names
        """
        plt.figure(figsize=(8, 6))
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', 
                    xticklabels=class_names, yticklabels=class_names)
        plt.title(f'{model_name} - Confusion Matrix')
        plt.ylabel('True Label')
        plt.xlabel('Predicted Label')
        
        cm_file = os.path.join(self.session_dir, f'{model_name}_confusion_matrix.png')
        plt.savefig(cm_file, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"✓ Confusion matrix saved to {cm_file}")
    
    def save_training_history(self, model_name, history):
        """
        Save training history (for neural networks).
        
        Args:
            model_name: Name of the model
            history: Training history object
        """
        if hasattr(history, 'history'):
            history_dict = history.history
        else:
            history_dict = history
        
        # Save as JSON
        history_file = os.path.join(self.session_dir, f'{model_name}_history.json')
        with open(history_file, 'w') as f:
            json.dump(history_dict, f, indent=2, default=str)
        
        # Create loss plot
        plt.figure(figsize=(12, 4))
        
        # Loss subplot
        plt.subplot(1, 2, 1)
        plt.plot(history_dict.get('loss', []), label='Training Loss')
        if 'val_loss' in history_dict:
            plt.plot(history_dict['val_loss'], label='Validation Loss')
        plt.title(f'{model_name} - Loss')
        plt.xlabel('Epoch')
        plt.ylabel('Loss')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        # Metric subplot (MAE or accuracy)
        plt.subplot(1, 2, 2)
        metric_key = 'mae' if 'mae' in history_dict else 'accuracy'
        if metric_key in history_dict:
            plt.plot(history_dict[metric_key], label=f'Training {metric_key.upper()}')
            if f'val_{metric_key}' in history_dict:
                plt.plot(history_dict[f'val_{metric_key}'], label=f'Validation {metric_key.upper()}')
            plt.title(f'{model_name} - {metric_key.upper()}')
            plt.xlabel('Epoch')
            plt.ylabel(metric_key.upper())
            plt.legend()
            plt.grid(True, alpha=0.3)
        
        plot_file = os.path.join(self.session_dir, f'{model_name}_training_history.png')
        plt.savefig(plot_file, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"✓ Training history saved to {plot_file}")
    
    def save_class_distribution(self, y_original, y_balanced=None):
        """
        Save class distribution visualization.
        
        Args:
            y_original: Original labels
            y_balanced: Balanced labels (optional)
        """
        import numpy as np
        
        plt.figure(figsize=(12, 5))
        
        # Original distribution
        plt.subplot(1, 2, 1)
        unique, counts = np.unique(y_original, return_counts=True)
        class_names = ['LOW', 'MEDIUM', 'HIGH']
        colors = ['#4CAF50', '#FF9800', '#F44336']
        plt.bar([class_names[i] for i in unique], counts, color=[colors[i] for i in unique])
        plt.title('Original Class Distribution')
        plt.ylabel('Count')
        for i, (cls, count) in enumerate(zip(unique, counts)):
            plt.text(i, count + max(counts)*0.02, str(count), ha='center', fontweight='bold')
        
        # Balanced distribution (if provided)
        if y_balanced is not None:
            plt.subplot(1, 2, 2)
            unique, counts = np.unique(y_balanced, return_counts=True)
            plt.bar([class_names[i] for i in unique], counts, color=[colors[i] for i in unique])
            plt.title('Balanced Class Distribution (SMOTE)')
            plt.ylabel('Count')
            for i, (cls, count) in enumerate(zip(unique, counts)):
                plt.text(i, count + max(counts)*0.02, str(count), ha='center', fontweight='bold')
        
        dist_file = os.path.join(self.session_dir, 'class_distribution.png')
        plt.savefig(dist_file, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"✓ Class distribution saved to {dist_file}")
    
    def generate_summary_report(self):
        """Generate a comprehensive summary report."""
        summary_file = os.path.join(self.session_dir, 'SUMMARY_REPORT.md')
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(f"# SkyGuard AI - Training Summary Report\n\n")
            f.write(f"**Training Session:** {self.timestamp}\n\n")
            f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # Data Statistics
            f.write("## Data Statistics\n\n")
            for stage, stats in self.results['data_stats'].items():
                f.write(f"### {stage.capitalize()}\n")
                for key, value in stats.items():
                    f.write(f"- **{key}:** {value}\n")
                f.write("\n")
            
            # Preprocessing Steps
            f.write("## Preprocessing Pipeline\n\n")
            for step, info in self.results['preprocessing'].items():
                f.write(f"### {step}\n")
                f.write(f"{info}\n\n")
            
            # Model Results
            f.write("## Model Performance\n\n")
            for model_name, data in self.results['models'].items():
                f.write(f"### {model_name}\n\n")
                f.write("**Metrics:**\n")
                for metric, value in data['metrics'].items():
                    if isinstance(value, (int, float)):
                        f.write(f"- **{metric}:** {value:.4f}\n")
                f.write("\n")
                
                if data['config']:
                    f.write("**Configuration:**\n")
                    for key, value in data['config'].items():
                        f.write(f"- **{key}:** {value}\n")
                    f.write("\n")
        
        print(f"\n✓ Summary report generated: {summary_file}")
        return summary_file
