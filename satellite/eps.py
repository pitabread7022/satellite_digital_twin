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
        
        Power balance equation:
        - Solar generation + Battery discharge = Total load + Battery charge + Losses
        - Net power = Solar generation - Total load
        - If net > 0: charging (limited by charge rate)
        - If net < 0: discharging (limited by discharge rate and voltage)
        
        Args:
            state: Current satellite state
            timestep_s: Timestep duration in seconds
            
        Returns:
            Updated satellite state
        """
        # Calculate solar generation based on sunlight (independent of battery)
        state.solar_generation_w = self._calculate_solar_generation(state)
        
        # Calculate net power (generation - load)
        # Positive = excess power for charging
        # Negative = deficit requiring battery discharge
        state.net_power_w = state.solar_generation_w - state.total_load_w
        
        # Update battery state (handles charge/discharge with proper physics)
        state = self._update_battery(state, timestep_s)
        
        # Update warnings based on current state
        state.update_warnings(self.config)
        
        return state
    
    def _calculate_solar_generation(self, state: SatelliteState) -> float:
        """Calculate solar power generation based on sunlight state."""
        if not state.in_sunlight:
            return 0.0
        
        # Base power from solar panels
        base_power = self.config.solar_panel_power_w
        
        # Solar panel degradation over time (separate from battery health)
        # For now, assume panels maintain efficiency, but could add degradation
        panel_efficiency = 1.0  # Could be reduced over mission lifetime
        
        # Solar generation is independent of battery state
        # The battery health doesn't affect solar generation - it affects battery capacity
        generated_power = base_power * panel_efficiency
        
        return generated_power
    
    def _update_battery(self, state: SatelliteState, timestep_s: float) -> SatelliteState:
        """
        Update battery state based on net power flow.
        
        Handles charging (positive net power) and discharging (negative net power)
        with efficiency factors and rate limits. Properly accounts for power balance.
        """
        timestep_h = timestep_s / 3600.0  # Convert to hours for Wh calculations
        
        # Get effective battery capacity (reduced by health degradation)
        effective_capacity_wh = self.config.battery_capacity_wh * (state.battery_health_percent / 100.0)
        
        # Calculate energy change with proper power balance
        if state.net_power_w > 0:
            # CHARGING: Solar generation exceeds load
            # Available charge power is net power, but limited by charge rate
            available_charge_power = state.net_power_w
            charge_power = min(available_charge_power, self.config.max_charge_rate_w)
            
            # Calculate energy added to battery (with charge efficiency)
            # Energy stored = power * time * efficiency
            energy_added_wh = charge_power * timestep_h * self.config.charge_efficiency
            
            # Excess solar power (if charge rate limited) is wasted
            excess_solar_w = max(0, available_charge_power - charge_power)
            
            energy_change_wh = energy_added_wh
            
        elif state.net_power_w < 0:
            # DISCHARGING: Load exceeds solar generation
            # Power needed from battery = abs(net_power)
            power_needed_w = abs(state.net_power_w)
            
            # Battery can only discharge at limited rate
            max_discharge_power = self.config.max_discharge_rate_w
            
            # Check if battery voltage allows this discharge rate
            # Lower voltage = lower max discharge capability
            # Use current voltage (from previous timestep) for this calculation
            current_voltage = state.battery_voltage_v if state.battery_voltage_v > 0 else 12.0
            voltage_factor = current_voltage / 12.6  # Normalize to max voltage
            effective_max_discharge = max_discharge_power * voltage_factor
            
            # Actual discharge power is limited by battery capability
            actual_discharge_power = min(power_needed_w, effective_max_discharge)
            
            # Energy removed from battery (accounting for discharge efficiency)
            # Energy delivered = energy_removed * efficiency
            # So: energy_removed = energy_delivered / efficiency
            energy_delivered_wh = actual_discharge_power * timestep_h
            energy_removed_wh = energy_delivered_wh / self.config.discharge_efficiency
            
            energy_change_wh = -energy_removed_wh
            
            # If battery can't supply full load, track power deficit
            power_deficit_w = max(0, power_needed_w - actual_discharge_power)
            if power_deficit_w > 0:
                # Load shedding should have prevented this, but track it
                state.load_shed_active = True
        else:
            # Balanced: generation = load, no battery change
            energy_change_wh = 0.0
        
        # Update battery energy
        new_energy = state.battery_energy_wh + energy_change_wh
        
        # Clamp to effective battery limits (accounting for health)
        min_energy = effective_capacity_wh * (self.config.min_soc_percent / 100.0)
        max_energy = effective_capacity_wh * (self.config.max_soc_percent / 100.0)
        
        # Hard limits to prevent negative or over-capacity
        new_energy = max(0, min(new_energy, effective_capacity_wh))
        
        # If we hit limits, adjust energy change accordingly
        if new_energy <= 0:
            energy_change_wh = -state.battery_energy_wh
            new_energy = 0
        elif new_energy >= effective_capacity_wh:
            energy_change_wh = effective_capacity_wh - state.battery_energy_wh
            new_energy = effective_capacity_wh
        
        state.battery_energy_wh = new_energy
        
        # Calculate SOC based on effective capacity
        if effective_capacity_wh > 0:
            state.battery_level_percent = (new_energy / effective_capacity_wh) * 100.0
        else:
            state.battery_level_percent = 0.0
        
        # Update battery voltage (affects power delivery capability)
        state.battery_voltage_v = self._calculate_voltage(state.battery_level_percent, state.battery_health_percent)
        
        # Track battery cycles for degradation
        self._track_cycles(state)
        
        return state
    
    def _calculate_voltage(self, soc_percent: float, health_percent: float) -> float:
        """
        Calculate battery voltage based on state of charge and health.
        More realistic model for Li-ion battery with health effects.
        """
        # Typical Li-ion: 3.0V (empty) to 4.2V (full) per cell
        # Assuming 3S configuration (3 cells in series) = 9V to 12.6V
        
        # Base voltage curve (non-linear for more realism)
        # Use a curve that's flatter in middle, steeper at ends
        soc_normalized = soc_percent / 100.0
        
        # Non-linear curve: more realistic battery behavior
        # Voltage drops faster at low SOC, flatter in middle
        if soc_normalized < 0.2:
            # Low SOC: steep drop
            voltage_factor = 0.3 + 0.7 * (soc_normalized / 0.2)
        elif soc_normalized < 0.8:
            # Middle SOC: relatively flat
            voltage_factor = 1.0 + 0.1 * ((soc_normalized - 0.2) / 0.6)
        else:
            # High SOC: slight increase
            voltage_factor = 1.1 + 0.1 * ((soc_normalized - 0.8) / 0.2)
        
        # Apply health degradation to voltage range
        # Degraded batteries have lower max voltage and higher min voltage
        health_factor = health_percent / 100.0
        min_voltage = 9.0 + (1.0 - health_factor) * 0.5  # Degraded: higher min
        max_voltage = 12.6 * health_factor  # Degraded: lower max
        
        voltage = min_voltage + (max_voltage - min_voltage) * voltage_factor
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
        """
        Check if the EPS can support additional load without going critical.
        
        Uses effective battery capacity (accounting for health) and proper
        discharge rate limits.
        """
        total_load = state.total_load_w + additional_load_w
        
        # Get effective capacity (reduced by health)
        effective_capacity_wh = self.config.battery_capacity_wh * (state.battery_health_percent / 100.0)
        
        if state.in_sunlight:
            # In sunlight, check if we can at least break even or drain slowly
            # Calculate solar generation for this check
            solar_gen = self._calculate_solar_generation(state)
            net_power = solar_gen - total_load
            
            if net_power < 0:
                # Draining battery - check if we have enough capacity
                power_deficit = abs(net_power)
                
                # Check discharge rate limit
                voltage_factor = state.battery_voltage_v / 12.6 if state.battery_voltage_v > 0 else 0.8
                max_discharge = self.config.max_discharge_rate_w * voltage_factor
                
                if power_deficit > max_discharge:
                    # Can't supply full load due to rate limit
                    return False
                
                # Calculate how long until we hit min SOC
                available_energy_wh = (
                    (state.battery_level_percent - self.config.min_soc_percent) / 100.0 
                    * effective_capacity_wh
                )
                
                # Energy needed accounting for discharge efficiency
                energy_needed_wh = power_deficit * (1.0 / self.config.discharge_efficiency)
                hours_to_min = available_energy_wh / energy_needed_wh if energy_needed_wh > 0 else float('inf')
                
                # Need at least 10 minutes of margin
                return hours_to_min > (10.0 / 60.0)
            return True
        else:
            # In eclipse, ensure we don't drain battery below minimum
            net_power = -total_load  # No solar
            
            # Check discharge rate limit
            voltage_factor = state.battery_voltage_v / 12.6 if state.battery_voltage_v > 0 else 0.8
            max_discharge = self.config.max_discharge_rate_w * voltage_factor
            
            if total_load > max_discharge:
                # Can't supply full load due to rate limit
                return False
            
            hours_remaining = self.config.eclipse_duration_min / 60.0
            energy_needed_wh = total_load * hours_remaining / self.config.discharge_efficiency
            
            # Available energy above minimum (using effective capacity)
            available_energy_wh = (
                (state.battery_level_percent - self.config.min_soc_percent) / 100.0
                * effective_capacity_wh
            )
            
            return available_energy_wh >= energy_needed_wh





