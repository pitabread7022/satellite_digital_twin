"""
Time-series data export for simulation results.
Supports CSV and JSON formats.
"""

import json
import csv
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime


class TimeSeriesExporter:
    """
    Export simulation history to various formats.
    
    Supports:
    - CSV export with configurable columns
    - JSON export (full or filtered)
    - Pandas DataFrame conversion
    """
    
    # Default columns for CSV export
    DEFAULT_COLUMNS = [
        'simulation_time_s',
        'orbit_number',
        'orbit_angle_deg',
        'battery_level_percent',
        'battery_voltage_v',
        'solar_generation_w',
        'total_load_w',
        'net_power_w',
        'onboard_data_volume_gb',
        'in_sunlight',
        'in_imaging_window',
        'is_imaging',
        'is_downlinking'
    ]
    
    def __init__(self, history: List[Dict[str, Any]]):
        """
        Initialize exporter with simulation history.
        
        Args:
            history: List of state dictionaries from simulation
        """
        self.history = history
    
    def to_csv(self, 
               filepath: str,
               columns: Optional[List[str]] = None,
               include_header: bool = True) -> str:
        """
        Export history to CSV file.
        
        Args:
            filepath: Output file path
            columns: Columns to include (uses defaults if None)
            include_header: Whether to include header row
            
        Returns:
            Path to created file
        """
        if not self.history:
            raise ValueError("No history data to export")
        
        columns = columns or self.DEFAULT_COLUMNS
        
        # Ensure all columns exist in data
        available_columns = [c for c in columns if c in self.history[0]]
        
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            
            if include_header:
                writer.writerow(available_columns)
            
            for record in self.history:
                row = [record.get(col, '') for col in available_columns]
                writer.writerow(row)
        
        return str(filepath)
    
    def to_json(self,
                filepath: str,
                columns: Optional[List[str]] = None,
                indent: int = 2,
                include_metadata: bool = True) -> str:
        """
        Export history to JSON file.
        
        Args:
            filepath: Output file path
            columns: Columns to include (all if None)
            indent: JSON indentation level
            include_metadata: Include export metadata
            
        Returns:
            Path to created file
        """
        if not self.history:
            raise ValueError("No history data to export")
        
        # Filter columns if specified
        if columns:
            data = [
                {k: v for k, v in record.items() if k in columns}
                for record in self.history
            ]
        else:
            data = self.history
        
        output = {
            'data': data
        }
        
        if include_metadata:
            output['metadata'] = {
                'exported_at': datetime.now().isoformat(),
                'record_count': len(data),
                'columns': list(data[0].keys()) if data else []
            }
        
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w') as f:
            json.dump(output, f, indent=indent, default=str)
        
        return str(filepath)
    
    def to_dataframe(self, columns: Optional[List[str]] = None):
        """
        Convert history to pandas DataFrame.
        
        Args:
            columns: Columns to include (all if None)
            
        Returns:
            pandas DataFrame
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas is required for DataFrame export. "
                            "Install with: pip install pandas")
        
        df = pd.DataFrame(self.history)
        
        if columns:
            available = [c for c in columns if c in df.columns]
            df = df[available]
        
        return df
    
    def get_column_stats(self, column: str) -> Dict[str, float]:
        """
        Get statistics for a specific column.
        
        Args:
            column: Column name
            
        Returns:
            Dictionary with min, max, mean, std
        """
        if not self.history:
            return {}
        
        values = [
            record[column] for record in self.history 
            if column in record and isinstance(record[column], (int, float))
        ]
        
        if not values:
            return {}
        
        n = len(values)
        mean = sum(values) / n
        variance = sum((x - mean) ** 2 for x in values) / n
        
        return {
            'min': min(values),
            'max': max(values),
            'mean': mean,
            'std': variance ** 0.5,
            'count': n
        }
    
    def resample(self, 
                 factor: int,
                 method: str = 'last') -> 'TimeSeriesExporter':
        """
        Resample history to lower resolution.
        
        Args:
            factor: Resampling factor (e.g., 5 = every 5th point)
            method: 'last' (take last value) or 'mean' (average)
            
        Returns:
            New TimeSeriesExporter with resampled data
        """
        if factor <= 1:
            return self
        
        if method == 'last':
            resampled = self.history[::factor]
        elif method == 'mean':
            resampled = []
            for i in range(0, len(self.history), factor):
                chunk = self.history[i:i+factor]
                if chunk:
                    # Average numeric values, take last for others
                    avg_record = {}
                    for key in chunk[0].keys():
                        values = [r[key] for r in chunk]
                        if isinstance(values[0], (int, float)) and not isinstance(values[0], bool):
                            avg_record[key] = sum(values) / len(values)
                        else:
                            avg_record[key] = values[-1]
                    resampled.append(avg_record)
        else:
            raise ValueError(f"Unknown method: {method}")
        
        return TimeSeriesExporter(resampled)
    
    def filter_time_range(self,
                          start_s: Optional[float] = None,
                          end_s: Optional[float] = None) -> 'TimeSeriesExporter':
        """
        Filter history to a specific time range.
        
        Args:
            start_s: Start time in seconds (inclusive)
            end_s: End time in seconds (inclusive)
            
        Returns:
            New TimeSeriesExporter with filtered data
        """
        filtered = [
            record for record in self.history
            if (start_s is None or record['simulation_time_s'] >= start_s) and
               (end_s is None or record['simulation_time_s'] <= end_s)
        ]
        return TimeSeriesExporter(filtered)
    
    def filter_orbits(self,
                      start_orbit: Optional[int] = None,
                      end_orbit: Optional[int] = None) -> 'TimeSeriesExporter':
        """
        Filter history to specific orbit range.
        
        Args:
            start_orbit: Starting orbit number (inclusive)
            end_orbit: Ending orbit number (inclusive)
            
        Returns:
            New TimeSeriesExporter with filtered data
        """
        filtered = [
            record for record in self.history
            if (start_orbit is None or record['orbit_number'] >= start_orbit) and
               (end_orbit is None or record['orbit_number'] <= end_orbit)
        ]
        return TimeSeriesExporter(filtered)


def export_events_to_json(events: List[Any], filepath: str) -> str:
    """
    Export simulation events to JSON file.
    
    Args:
        events: List of SimulationEvent objects
        filepath: Output file path
        
    Returns:
        Path to created file
    """
    event_dicts = [
        {
            'time_s': e.time_s,
            'orbit': e.orbit,
            'event_type': e.event_type,
            'description': e.description
        }
        for e in events
    ]
    
    output = {
        'events': event_dicts,
        'metadata': {
            'exported_at': datetime.now().isoformat(),
            'event_count': len(event_dicts)
        }
    }
    
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    with open(filepath, 'w') as f:
        json.dump(output, f, indent=2)
    
    return str(filepath)





