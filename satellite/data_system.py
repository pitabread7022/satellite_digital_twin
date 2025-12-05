"""
Data system model for the satellite.
Compliant with loads.md data budget:

## Baseline Data Budget
- Data generation: 2 Gbit per orbit (during 10 minutes imaging)
- Downlink: 50 Mbps for 8 minutes per orbit
- Downlink capacity: ~3 GB per pass (more than enough for 0.25 GB generated)
"""

from typing import Optional, Tuple
from .state import SatelliteState, SatelliteConfig


class DataSystem:
    """
    Data system model compliant with loads.md specification.
    
    Data Flow:
    - Generation: 2 Gbit (0.25 GB) per orbit during imaging (10 min)
    - Rate: 0.025 GB/min during imaging
    - Downlink: 50 Mbps = 0.375 GB/min for 8 minutes
    - Capacity per pass: ~3 GB (excess capacity)
    """
    
    def __init__(self, config: SatelliteConfig):
        self.config = config
        self._downlink_active = False
        self._downlink_target_gb = 0.0
        self._data_generated_this_orbit = 0.0
        self._current_orbit = 0
    
    def update(self, state: SatelliteState, timestep_min: float) -> SatelliteState:
        """
        Update data system state for one timestep.
        
        Args:
            state: Current satellite state
            timestep_min: Timestep duration in minutes
            
        Returns:
            Updated satellite state
        """
        # Reset orbit tracking
        if state.orbit_number > self._current_orbit:
            self._data_generated_this_orbit = 0.0
            self._current_orbit = state.orbit_number
        
        # Handle data generation during imaging
        # Per loads.md: 2 Gbit (0.25 GB) per orbit over 10 minutes
        if state.is_imaging:
            state = self._generate_data(state, timestep_min)
        
        # Handle downlink if active
        # Per loads.md: 50 Mbps for 8 minutes
        if state.is_downlinking:
            state = self._process_downlink(state, timestep_min)
        
        # Update storage status
        state.data_storage_full = (
            state.onboard_data_volume_gb >= self.config.max_data_storage_gb * 0.95
        )
        
        return state
    
    def _generate_data(self, state: SatelliteState, timestep_min: float) -> SatelliteState:
        """
        Generate data during imaging operations.
        
        Per loads.md: 2 Gbit (0.25 GB) generated per orbit over 10 minutes imaging.
        Rate: 0.025 GB/min
        """
        # Check if we've hit the per-orbit data limit
        max_data_per_orbit_gb = self.config.data_per_orbit_gbit / 8.0  # 0.25 GB
        
        if self._data_generated_this_orbit >= max_data_per_orbit_gb:
            # Already generated max data for this orbit
            return state
        
        # Calculate data generated this timestep
        # Rate: 2 Gbit / 10 min = 0.2 Gbit/min = 0.025 GB/min
        data_rate_gb_per_min = self.config.data_generation_rate_gb_per_min
        data_generated = data_rate_gb_per_min * timestep_min
        
        # Cap at per-orbit maximum
        remaining_this_orbit = max_data_per_orbit_gb - self._data_generated_this_orbit
        data_generated = min(data_generated, remaining_this_orbit)
        
        # Add to onboard storage (capped at max)
        new_volume = state.onboard_data_volume_gb + data_generated
        state.onboard_data_volume_gb = min(new_volume, self.config.max_data_storage_gb)
        
        # Track totals
        state.data_generated_gb += data_generated
        state.data_generated_this_orbit_gb += data_generated
        self._data_generated_this_orbit += data_generated
        
        return state
    
    def _process_downlink(self, state: SatelliteState, timestep_min: float) -> SatelliteState:
        """
        Process data downlink.
        
        Per loads.md: 50 Mbps for 8 minutes per orbit.
        Rate: 50 Mbps = 6.25 MB/s = 375 MB/min = 0.375 GB/min
        Capacity: 0.375 * 8 = 3 GB per pass (excess capacity for 0.25 GB/orbit)
        """
        if state.onboard_data_volume_gb <= 0:
            state.is_downlinking = False
            self._downlink_active = False
            return state
        
        # Calculate data transmitted this timestep
        # Rate: 50 Mbps = 0.375 GB/min
        data_rate_gb_per_min = self.config.downlink_speed_gb_per_min
        data_transmitted = data_rate_gb_per_min * timestep_min
        
        # Remove from onboard storage
        actual_transmitted = min(data_transmitted, state.onboard_data_volume_gb)
        state.onboard_data_volume_gb = max(0.0, state.onboard_data_volume_gb - actual_transmitted)
        
        # Track total downlinked
        state.data_downlinked_gb += actual_transmitted
        
        # Check if downlink target reached (if set)
        if self._downlink_target_gb > 0:
            self._downlink_target_gb -= actual_transmitted
            if self._downlink_target_gb <= 0 or state.onboard_data_volume_gb <= 0:
                state.is_downlinking = False
                self._downlink_active = False
                self._downlink_target_gb = 0.0
        
        return state
    
    def start_downlink(self, state: SatelliteState, 
                       target_gb: Optional[float] = None) -> SatelliteState:
        """
        Start a downlink operation.
        
        Args:
            state: Current satellite state
            target_gb: Optional target amount to downlink (None = all data)
            
        Returns:
            Updated satellite state
        """
        if state.onboard_data_volume_gb <= 0:
            return state
        
        state.is_downlinking = True
        self._downlink_active = True
        
        if target_gb is not None:
            self._downlink_target_gb = min(target_gb, state.onboard_data_volume_gb)
        else:
            self._downlink_target_gb = 0.0  # 0 means download all
        
        return state
    
    def stop_downlink(self, state: SatelliteState) -> SatelliteState:
        """Stop an active downlink operation."""
        state.is_downlinking = False
        self._downlink_active = False
        self._downlink_target_gb = 0.0
        return state
    
    def get_storage_status(self, state: SatelliteState) -> dict:
        """Get detailed storage status per loads.md data budget."""
        max_per_orbit_gb = self.config.data_per_orbit_gbit / 8.0
        
        return {
            'onboard_data_volume_gb': state.onboard_data_volume_gb,
            'max_storage_gb': self.config.max_data_storage_gb,
            'storage_used_percent': (
                state.onboard_data_volume_gb / self.config.max_data_storage_gb * 100
            ),
            'data_generated_total_gb': state.data_generated_gb,
            'data_generated_this_orbit_gb': self._data_generated_this_orbit,
            'max_data_per_orbit_gb': max_per_orbit_gb,
            'data_downlinked_total_gb': state.data_downlinked_gb,
            'is_downlinking': state.is_downlinking,
            'storage_full': state.data_storage_full,
            # Data rates per loads.md
            'generation_rate_gb_per_min': self.config.data_generation_rate_gb_per_min,
            'downlink_rate_gb_per_min': self.config.downlink_speed_gb_per_min,
            'downlink_capacity_per_pass_gb': self.config.data_per_downlink_gb
        }
    
    def get_downlink_time_estimate(self, state: SatelliteState, 
                                    target_gb: Optional[float] = None) -> float:
        """
        Estimate time to downlink data.
        
        Args:
            state: Current satellite state
            target_gb: Amount to downlink (None = all onboard data)
            
        Returns:
            Estimated time in minutes
        """
        data_to_download = target_gb or state.onboard_data_volume_gb
        if data_to_download <= 0:
            return 0.0
        
        # Time = data / rate
        # Rate: 0.375 GB/min
        return data_to_download / self.config.downlink_speed_gb_per_min
    
    def can_store_data(self, state: SatelliteState, data_gb: float) -> bool:
        """Check if there's enough storage for additional data."""
        return (state.onboard_data_volume_gb + data_gb) <= self.config.max_data_storage_gb
    
    def get_data_budget_status(self) -> dict:
        """Get data budget compliance status per loads.md."""
        max_per_orbit_gb = self.config.data_per_orbit_gbit / 8.0
        remaining = max_per_orbit_gb - self._data_generated_this_orbit
        
        return {
            'data_budget_per_orbit_gbit': self.config.data_per_orbit_gbit,
            'data_budget_per_orbit_gb': max_per_orbit_gb,
            'generated_this_orbit_gb': self._data_generated_this_orbit,
            'remaining_this_orbit_gb': max(0, remaining),
            'downlink_rate_mbps': self.config.downlink_speed_mbps,
            'downlink_window_min': self.config.downlink_duration_min,
            'downlink_capacity_gb': self.config.data_per_downlink_gb
        }
