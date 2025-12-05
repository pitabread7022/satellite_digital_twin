"""
Orbital mechanics model for the satellite.
Handles sun/eclipse cycles and imaging window detection.
"""

from typing import List, Tuple
from .state import SatelliteState, SatelliteConfig


class OrbitModel:
    """
    Orbital model for a Sun-Synchronous Orbit (SSO) satellite.
    
    Handles:
    - Orbit position tracking (angle in orbit)
    - Sun/eclipse cycle determination
    - Imaging window detection
    """
    
    def __init__(self, config: SatelliteConfig):
        self.config = config
        
        # Calculate orbital angular velocity (degrees per second)
        self.orbit_period_s = config.orbit_period_min * 60.0
        self.angular_velocity_deg_s = 360.0 / self.orbit_period_s
        
        # Calculate sun/eclipse angles
        # Sunlight for 60 min out of 95 min = 63.16% of orbit = 227.4 degrees
        # Eclipse for 35 min = 36.84% = 132.6 degrees
        self.sunlight_fraction = config.sunlight_duration_min / config.orbit_period_min
        self.sunlight_angle_span = 360.0 * self.sunlight_fraction
        self.eclipse_angle_span = 360.0 - self.sunlight_angle_span
        
        # Define eclipse region (centered at 180 degrees - opposite to sun)
        # Eclipse starts at 180 - eclipse_span/2 and ends at 180 + eclipse_span/2
        self.eclipse_start_deg = 180.0 - (self.eclipse_angle_span / 2.0)
        self.eclipse_end_deg = 180.0 + (self.eclipse_angle_span / 2.0)
    
    def update(self, state: SatelliteState, timestep_s: float) -> SatelliteState:
        """
        Update orbital state for one timestep.
        
        Args:
            state: Current satellite state
            timestep_s: Timestep duration in seconds
            
        Returns:
            Updated satellite state
        """
        # Update simulation time
        state.simulation_time_s += timestep_s
        
        # Update orbit angle
        old_angle = state.orbit_angle_deg
        state.orbit_angle_deg += self.angular_velocity_deg_s * timestep_s
        
        # Handle orbit wrap-around
        if state.orbit_angle_deg >= 360.0:
            state.orbit_angle_deg -= 360.0
            state.orbit_number += 1
        
        # Determine sunlight/eclipse state
        state.in_sunlight = self._is_in_sunlight(state.orbit_angle_deg)
        
        # Check imaging windows
        state.in_imaging_window = self._is_in_imaging_window(state.orbit_angle_deg)
        
        return state
    
    def _is_in_sunlight(self, orbit_angle_deg: float) -> bool:
        """
        Determine if satellite is in sunlight based on orbit angle.
        
        Eclipse region is centered at 180 degrees (opposite to sun direction).
        """
        # Normalize angle to 0-360
        angle = orbit_angle_deg % 360.0
        
        # Check if in eclipse region
        if self.eclipse_start_deg <= angle <= self.eclipse_end_deg:
            return False
        return True
    
    def _is_in_imaging_window(self, orbit_angle_deg: float) -> bool:
        """
        Check if current orbit position is within any imaging window.
        
        Imaging windows are defined as theta ranges from north (0 deg).
        """
        angle = orbit_angle_deg % 360.0
        
        for window in self.config.imaging_windows_theta:
            start, end = window[0], window[1]
            
            # Handle window that wraps around 360->0
            if start > end:
                if angle >= start or angle <= end:
                    return True
            else:
                if start <= angle <= end:
                    return True
        
        return False
    
    def get_time_to_sunlight(self, state: SatelliteState) -> float:
        """
        Calculate time until satellite enters sunlight.
        
        Returns:
            Time in seconds until sunlight (0 if already in sunlight)
        """
        if state.in_sunlight:
            return 0.0
        
        angle = state.orbit_angle_deg % 360.0
        
        # Calculate angle to sunlight region
        if angle < self.eclipse_start_deg:
            # Before eclipse region (shouldn't happen if in eclipse)
            angle_to_sunlight = self.eclipse_start_deg - angle
        else:
            # In eclipse, calculate angle to exit
            angle_to_sunlight = (360.0 - angle) + self.eclipse_start_deg
            if angle <= self.eclipse_end_deg:
                angle_to_sunlight = self.eclipse_end_deg - angle
        
        # Convert angle to time
        return angle_to_sunlight / self.angular_velocity_deg_s
    
    def get_time_to_eclipse(self, state: SatelliteState) -> float:
        """
        Calculate time until satellite enters eclipse.
        
        Returns:
            Time in seconds until eclipse (0 if already in eclipse)
        """
        if not state.in_sunlight:
            return 0.0
        
        angle = state.orbit_angle_deg % 360.0
        
        # Calculate angle to eclipse region
        if angle < self.eclipse_start_deg:
            angle_to_eclipse = self.eclipse_start_deg - angle
        else:
            # Past eclipse region, wrap around
            angle_to_eclipse = (360.0 - angle) + self.eclipse_start_deg
        
        return angle_to_eclipse / self.angular_velocity_deg_s
    
    def get_next_imaging_window(self, state: SatelliteState) -> Tuple[float, float]:
        """
        Get time to next imaging window and its duration.
        
        Returns:
            Tuple of (time_to_window_s, window_duration_s)
        """
        if not self.config.imaging_windows_theta:
            return (float('inf'), 0.0)
        
        angle = state.orbit_angle_deg % 360.0
        min_time = float('inf')
        window_duration = 0.0
        
        for window in self.config.imaging_windows_theta:
            start, end = window[0], window[1]
            
            # Check if currently in this window
            if start <= angle <= end:
                return (0.0, (end - angle) / self.angular_velocity_deg_s)
            
            # Calculate angle to window start
            if angle < start:
                angle_to_window = start - angle
            else:
                angle_to_window = (360.0 - angle) + start
            
            time_to_window = angle_to_window / self.angular_velocity_deg_s
            
            if time_to_window < min_time:
                min_time = time_to_window
                window_span = end - start if end > start else (360.0 - start + end)
                window_duration = window_span / self.angular_velocity_deg_s
        
        return (min_time, window_duration)
    
    def get_orbit_info(self, state: SatelliteState) -> dict:
        """Get detailed orbital information."""
        return {
            'orbit_number': state.orbit_number,
            'orbit_angle_deg': state.orbit_angle_deg,
            'orbit_period_min': self.config.orbit_period_min,
            'in_sunlight': state.in_sunlight,
            'in_imaging_window': state.in_imaging_window,
            'time_to_sunlight_s': self.get_time_to_sunlight(state),
            'time_to_eclipse_s': self.get_time_to_eclipse(state),
            'sunlight_fraction': self.sunlight_fraction,
            'eclipse_start_deg': self.eclipse_start_deg,
            'eclipse_end_deg': self.eclipse_end_deg
        }





