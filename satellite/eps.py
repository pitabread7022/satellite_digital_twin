"""
Electrical Power System (EPS) model for the satellite.
Handles solar generation, battery management, and power distribution.
"""

from dataclasses import dataclass
from typing import Tuple

from .state import SatelliteState, SatelliteConfig


class EPS:
    """
    Electrical Power System model.
    
    Manages:
    - Solar panel power generation (dependent on sunlight)
    - Battery state of charge (SOC) with min/max limits
    - Charge/discharge with efficiency factors
    - Battery health degradation over cycles
    """
    
    def __init__(self, config: SatelliteConfig):
        self.config = config
        self._cycle_threshold_percent = 10.0  # SOC change to count as partial cycle
        self._last_soc = None
        self._accumulated_cycle_change = 0.0
    
    def update(self, state: SatelliteState, timestep_s: float) -> SatelliteState:
        """
        Update EPS state for one timestep.
        
        Args:
            state: Current satellite state
            timestep_s: Timestep duration in seconds
            
        Returns:
            Updated satellite state
        """
        # Calculate solar generation based on sunlight
        state.solar_generation_w = self._calculate_solar_generation(state)
        
        # Calculate net power (generation - load)
        state.net_power_w = state.solar_generation_w - state.total_load_w
        
        # Update battery state
        state = self._update_battery(state, timestep_s)
        
        # Update warnings
        state.update_warnings(self.config)
        
        return state
    
    def _calculate_solar_generation(self, state: SatelliteState) -> float:
        """Calculate solar power generation based on sunlight state."""
        if not state.in_sunlight:
            return 0.0
        
        # Full power when in sunlight (could add angle-dependent efficiency)
        base_power = self.config.solar_panel_power_w
        
        # Apply battery health factor (slight degradation effect on charging)
        health_factor = state.battery_health_percent / 100.0
        
        return base_power * health_factor
    
    def _update_battery(self, state: SatelliteState, timestep_s: float) -> SatelliteState:
        """
        Update battery state based on net power flow.
        
        Handles charging (positive net power) and discharging (negative net power)
        with efficiency factors and rate limits.
        """
        timestep_h = timestep_s / 3600.0  # Convert to hours for Wh calculations
        
        # Calculate energy change
        if state.net_power_w > 0:
            # Charging - apply charge efficiency and rate limit
            charge_power = min(state.net_power_w, self.config.max_charge_rate_w)
            energy_change_wh = charge_power * timestep_h * self.config.charge_efficiency
        else:
            # Discharging - apply discharge efficiency and rate limit
            discharge_power = min(abs(state.net_power_w), self.config.max_discharge_rate_w)
            energy_change_wh = -discharge_power * timestep_h / self.config.discharge_efficiency
        
        # Update battery energy
        new_energy = state.battery_energy_wh + energy_change_wh
        
        # Clamp to battery limits
        min_energy = self.config.battery_capacity_wh * (self.config.min_soc_percent / 100.0)
        max_energy = self.config.battery_capacity_wh * (self.config.max_soc_percent / 100.0)
        
        # Allow going slightly beyond limits but track it
        new_energy = max(0, min(new_energy, self.config.battery_capacity_wh))
        
        state.battery_energy_wh = new_energy
        state.battery_level_percent = (new_energy / self.config.battery_capacity_wh) * 100.0
        
        # Update battery voltage (simplified linear model)
        state.battery_voltage_v = self._calculate_voltage(state.battery_level_percent)
        
        # Track battery cycles for degradation
        self._track_cycles(state)
        
        return state
    
    def _calculate_voltage(self, soc_percent: float) -> float:
        """
        Calculate battery voltage based on state of charge.
        Simplified linear model for Li-ion battery.
        """
        # Typical Li-ion: 3.0V (empty) to 4.2V (full) per cell
        # Assuming 3S configuration (3 cells in series) = 9V to 12.6V
        min_voltage = 9.0
        max_voltage = 12.6
        
        voltage = min_voltage + (max_voltage - min_voltage) * (soc_percent / 100.0)
        return round(voltage, 2)
    
    def _track_cycles(self, state: SatelliteState) -> None:
        """Track battery charge/discharge cycles for health degradation."""
        if self._last_soc is None:
            self._last_soc = state.battery_level_percent
            return
        
        # Accumulate SOC change
        soc_change = abs(state.battery_level_percent - self._last_soc)
        self._accumulated_cycle_change += soc_change
        self._last_soc = state.battery_level_percent
        
        # Count full cycle when accumulated change reaches 100%
        if self._accumulated_cycle_change >= 100.0:
            state.battery_cycles += 1
            self._accumulated_cycle_change -= 100.0
            
            # Apply degradation (0.02% per cycle is typical for Li-ion)
            degradation_per_cycle = 0.02
            state.battery_health_percent = max(
                50.0,  # Minimum health floor
                state.battery_health_percent - degradation_per_cycle
            )
    
    def get_power_budget(self, state: SatelliteState) -> dict:
        """Get detailed power budget breakdown."""
        return {
            'solar_generation_w': state.solar_generation_w,
            'total_load_w': state.total_load_w,
            'base_load_w': state.base_load_w,
            'payload_load_w': state.payload_load_w,
            'heater_load_w': state.heater_load_w,
            'comms_load_w': state.comms_load_w,
            'net_power_w': state.net_power_w,
            'battery_level_percent': state.battery_level_percent,
            'battery_energy_wh': state.battery_energy_wh,
            'in_sunlight': state.in_sunlight
        }
    
    def can_support_load(self, state: SatelliteState, additional_load_w: float) -> bool:
        """Check if the EPS can support additional load without going critical."""
        total_load = state.total_load_w + additional_load_w
        
        if state.in_sunlight:
            # In sunlight, check if we can at least break even or drain slowly
            net_power = state.solar_generation_w - total_load
            if net_power < 0:
                # Calculate how long until we hit min SOC
                hours_to_min = (
                    (state.battery_level_percent - self.config.min_soc_percent) / 100.0 
                    * self.config.battery_capacity_wh
                ) / abs(net_power)
                # Need at least 10 minutes of margin
                return hours_to_min > (10.0 / 60.0)
            return True
        else:
            # In eclipse, ensure we don't drain battery below minimum
            net_power = -total_load  # No solar
            hours_remaining = self.config.eclipse_duration_min / 60.0
            energy_needed = total_load * hours_remaining / self.config.discharge_efficiency
            available_energy = (
                (state.battery_level_percent - self.config.min_soc_percent) / 100.0
                * self.config.battery_capacity_wh
            )
            return available_energy >= energy_needed





