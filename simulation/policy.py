"""
Policy system for satellite operations.
Compliant with loads.md specification and 20% SoC constraint.

Critical Requirement:
- Battery SoC shall NEVER drop below 20% during nominal operations

Load Scheduling per loads.md:
- Imaging: +40W, sunlight only, 10 min/orbit
- Downlink: +30W, 8 min/orbit (50% sun, 50% eclipse)
- ADCS dump: +10W, sunlight only, 5 min/orbit
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from satellite.state import SatelliteState, SatelliteConfig


@dataclass
class PolicyAction:
    """
    Actions that a policy can command.
    
    Per loads.md, actions control:
    - Imaging: +40W, sunlight only, 10 min/orbit max
    - Downlink: +30W, 8 min/orbit max  
    - ADCS dump: +10W, sunlight only, 5 min/orbit max
    """
    # Load control per loads.md
    enable_imaging: Optional[bool] = None  # +40W, sunlight only
    enable_downlink: Optional[bool] = None  # +30W
    enable_adcs_dump: Optional[bool] = None  # +10W, sunlight only
    
    # Emergency mode
    enter_safe_mode: bool = False  # Shed all non-critical loads
    
    # Custom actions
    custom_actions: Dict[str, Any] = field(default_factory=dict)


class Policy(ABC):
    """
    Abstract base class for satellite operation policies.
    
    All policies MUST respect:
    - Battery SoC >= 20% constraint (strict compliance)
    - Sunlight constraints for imaging and ADCS dump
    - Per-orbit time limits from loads.md
    """
    
    def __init__(self, name: str = "CustomPolicy"):
        self.name = name
        self._history: List[Dict[str, Any]] = []
    
    @abstractmethod
    def evaluate(self, state: SatelliteState, 
                 config: SatelliteConfig) -> PolicyAction:
        """
        Evaluate current state and determine actions.
        
        Must ensure 20% SoC compliance at all times.
        
        Args:
            state: Current satellite state
            config: Satellite configuration
            
        Returns:
            PolicyAction with commands for this timestep
        """
        pass
    
    def log_decision(self, state: SatelliteState, action: PolicyAction, 
                     reason: str = "") -> None:
        """Log a policy decision for analysis."""
        self._history.append({
            'time_s': state.simulation_time_s,
            'orbit': state.orbit_number,
            'angle': state.orbit_angle_deg,
            'battery_percent': state.battery_level_percent,
            'action': action,
            'reason': reason
        })
    
    def get_history(self) -> List[Dict[str, Any]]:
        """Get policy decision history."""
        return self._history
    
    def reset(self) -> None:
        """Reset policy state."""
        self._history = []
    
    def _check_soc_safe(self, state: SatelliteState, config: SatelliteConfig) -> bool:
        """Check if battery is safely above 20% minimum."""
        safety_threshold = config.min_soc_percent + config.soc_safety_margin_percent
        return state.battery_level_percent > safety_threshold
    
    def _can_survive_eclipse(self, state: SatelliteState, config: SatelliteConfig,
                             load_w: float) -> bool:
        """
        Check if we can survive worst-case eclipse at given load level.
        
        Critical for 20% SoC compliance.
        """
        eclipse_duration_h = config.eclipse_duration_min / 60.0
        energy_needed_wh = load_w * eclipse_duration_h / config.discharge_efficiency
        
        # Available energy above 20% + safety margin
        min_energy_wh = config.battery_capacity_wh * (config.min_soc_percent / 100.0)
        safety_wh = config.battery_capacity_wh * (config.soc_safety_margin_percent / 100.0)
        available_wh = state.battery_energy_wh - min_energy_wh - safety_wh
        
        return available_wh >= energy_needed_wh


class LoadsMDCompliantPolicy(Policy):
    """
    Policy that strictly follows loads.md specification.
    
    Load Schedule:
    - Platform base: 15W continuous
    - Imaging: +40W during imaging window (sunlight only, 10 min/orbit)
    - Downlink: +30W during ground pass (8 min/orbit)
    - ADCS dump: +10W during dump window (sunlight only, 5 min/orbit)
    
    Critical Constraint:
    - Battery SoC shall NEVER drop below 20%
    """
    
    def __init__(self):
        super().__init__(name="LoadsMDCompliantPolicy")
    
    def evaluate(self, state: SatelliteState, 
                 config: SatelliteConfig) -> PolicyAction:
        action = PolicyAction()
        reason = ""
        
        # CRITICAL: Check 20% SoC constraint first
        if not self._check_soc_safe(state, config):
            # Near or below safety threshold - enter safe mode
            action.enter_safe_mode = True
            action.enable_imaging = False
            action.enable_downlink = False
            action.enable_adcs_dump = False
            reason = f"SOC protection: {state.battery_level_percent:.1f}% near 20% limit"
            self.log_decision(state, action, reason)
            return action
        
        # Check if we can survive eclipse with additional loads
        base_load = config.base_load_w
        
        # === IMAGING CONTROL ===
        # Per loads.md: +40W, sunlight only, 10 min/orbit
        imaging_time_remaining = config.imaging_duration_min - state.imaging_time_this_orbit_min
        
        if (state.in_imaging_window and 
            state.in_sunlight and 
            imaging_time_remaining > 0 and
            not state.data_storage_full):
            
            # Check if we can afford imaging load
            imaging_load = base_load + config.imaging_load_w  # 55W
            if self._can_survive_eclipse(state, config, imaging_load):
                action.enable_imaging = True
                reason = "Imaging window active"
            else:
                action.enable_imaging = False
                reason = "Imaging skipped - insufficient battery for eclipse"
        else:
            action.enable_imaging = False
        
        # === DOWNLINK CONTROL ===
        # Per loads.md: +30W, 8 min/orbit, 50% sun/50% eclipse
        downlink_time_remaining = config.downlink_duration_min - state.downlink_time_this_orbit_min
        
        if (state.in_ground_pass_window and 
            downlink_time_remaining > 0 and
            state.onboard_data_volume_gb > 0):
            
            # Check if we can afford downlink load
            downlink_load = base_load + config.downlink_load_w  # 45W
            
            # More conservative check if in eclipse
            if state.in_sunlight or self._can_survive_eclipse(state, config, downlink_load):
                action.enable_downlink = True
                # Don't image while downlinking
                action.enable_imaging = False
                reason = "Ground pass - downlinking"
            else:
                action.enable_downlink = False
                reason = "Downlink skipped - battery protection in eclipse"
        else:
            action.enable_downlink = False
        
        # === ADCS DUMP CONTROL ===
        # Per loads.md: +10W, sunlight only, 5 min/orbit
        adcs_time_remaining = config.adcs_dump_duration_min - state.adcs_dump_time_this_orbit_min
        
        if (state.in_adcs_dump_window and 
            state.in_sunlight and 
            adcs_time_remaining > 0):
            
            # ADCS dump is low power, usually safe
            current_load = base_load
            if action.enable_imaging:
                current_load += config.imaging_load_w
            
            adcs_load = current_load + config.adcs_dump_load_w
            if self._can_survive_eclipse(state, config, adcs_load):
                action.enable_adcs_dump = True
                if not reason:
                    reason = "ADCS momentum dump"
            else:
                action.enable_adcs_dump = False
        else:
            action.enable_adcs_dump = False
        
        if not reason:
            reason = "Nominal operations"
        
        self.log_decision(state, action, reason)
        return action


class BasicPolicy(Policy):
    """
    Basic policy with simple threshold-based rules.
    Ensures 20% SoC compliance while allowing operations.
    """
    
    def __init__(self, 
                 low_battery_threshold: float = 30.0,
                 high_storage_threshold: float = 70.0):
        super().__init__(name="BasicPolicy")
        self.low_battery_threshold = low_battery_threshold
        self.high_storage_threshold = high_storage_threshold
    
    def evaluate(self, state: SatelliteState, 
                 config: SatelliteConfig) -> PolicyAction:
        action = PolicyAction()
        reason = ""
        
        # CRITICAL: 20% SoC protection
        if state.battery_level_percent < config.min_soc_percent + 5:
            action.enter_safe_mode = True
            reason = "Critical battery - safe mode"
            self.log_decision(state, action, reason)
            return action
        
        # Low battery - conservative operations
        if state.battery_level_percent < self.low_battery_threshold:
            action.enable_imaging = False
            action.enable_downlink = False
            action.enable_adcs_dump = False
            reason = "Low battery - reduced operations"
            self.log_decision(state, action, reason)
            return action
        
        # Normal operations - follow window scheduling
        
        # Imaging: in window, sunlight, has time budget
        if (state.in_imaging_window and 
            state.in_sunlight and 
            state.imaging_time_this_orbit_min < config.imaging_duration_min and
            not state.data_storage_full):
            action.enable_imaging = True
            reason = "Imaging"
        else:
            action.enable_imaging = False
        
        # Downlink: in window, has data, has time budget
        storage_percent = (state.onboard_data_volume_gb / config.max_data_storage_gb * 100)
        if (state.in_ground_pass_window and 
            state.downlink_time_this_orbit_min < config.downlink_duration_min and
            (storage_percent > self.high_storage_threshold or state.onboard_data_volume_gb > 0.1)):
            action.enable_downlink = True
            action.enable_imaging = False  # Don't image during downlink
            reason = "Downlinking"
        else:
            action.enable_downlink = False
        
        # ADCS dump: in window, sunlight, has time budget
        if (state.in_adcs_dump_window and 
            state.in_sunlight and
            state.adcs_dump_time_this_orbit_min < config.adcs_dump_duration_min):
            action.enable_adcs_dump = True
            if not reason:
                reason = "ADCS dump"
        else:
            action.enable_adcs_dump = False
        
        if not reason:
            reason = "Idle"
        
        self.log_decision(state, action, reason)
        return action


class PowerSavePolicy(Policy):
    """
    Power-saving policy that prioritizes battery conservation.
    Very conservative to ensure 20% SoC compliance with margin.
    """
    
    def __init__(self):
        super().__init__(name="PowerSavePolicy")
        self._target_entry_soc = 60.0  # Target SOC before eclipse
    
    def evaluate(self, state: SatelliteState, 
                 config: SatelliteConfig) -> PolicyAction:
        action = PolicyAction()
        reason = ""
        
        # CRITICAL: Aggressive 20% protection
        if state.battery_level_percent < 35.0:
            action.enter_safe_mode = True
            reason = "Power save - early safe mode"
            self.log_decision(state, action, reason)
            return action
        
        # In eclipse - absolute minimum operations
        if not state.in_sunlight:
            action.enable_imaging = False
            action.enable_downlink = False
            action.enable_adcs_dump = False
            reason = "Eclipse - minimum power"
            self.log_decision(state, action, reason)
            return action
        
        # In sunlight - charge first, then operate
        if state.battery_level_percent < self._target_entry_soc:
            # Still charging - minimal operations
            action.enable_imaging = False
            action.enable_downlink = False
            # Allow ADCS dump as it's critical and low power
            if (state.in_adcs_dump_window and 
                state.adcs_dump_time_this_orbit_min < config.adcs_dump_duration_min):
                action.enable_adcs_dump = True
            else:
                action.enable_adcs_dump = False
            reason = f"Charging ({state.battery_level_percent:.1f}% < {self._target_entry_soc}%)"
        else:
            # Battery OK - allow operations
            if (state.in_imaging_window and 
                state.imaging_time_this_orbit_min < config.imaging_duration_min and
                not state.data_storage_full):
                action.enable_imaging = True
                reason = "Battery OK - imaging"
            
            if (state.in_ground_pass_window and 
                state.downlink_time_this_orbit_min < config.downlink_duration_min and
                state.onboard_data_volume_gb > 0):
                action.enable_downlink = True
                action.enable_imaging = False
                reason = "Battery OK - downlink"
            
            if (state.in_adcs_dump_window and 
                state.adcs_dump_time_this_orbit_min < config.adcs_dump_duration_min):
                action.enable_adcs_dump = True
        
        if not reason:
            reason = "Power save idle"
        
        self.log_decision(state, action, reason)
        return action


class HighPerformancePolicy(Policy):
    """
    High-performance policy that maximizes data collection.
    Operates closer to 20% SoC limit but still maintains compliance.
    """
    
    def __init__(self):
        super().__init__(name="HighPerformancePolicy")
    
    def evaluate(self, state: SatelliteState, 
                 config: SatelliteConfig) -> PolicyAction:
        action = PolicyAction()
        reason = ""
        
        # CRITICAL: Still must respect 20% limit
        if state.battery_level_percent < config.min_soc_percent + 3:
            action.enter_safe_mode = True
            reason = "Battery critical"
            self.log_decision(state, action, reason)
            return action
        
        # Aggressive imaging - use full time budget
        if (state.in_sunlight and 
            state.imaging_time_this_orbit_min < config.imaging_duration_min and
            not state.data_storage_full and
            state.battery_level_percent > 25):
            
            # Image even outside designated windows if in sunlight
            if state.in_imaging_window:
                action.enable_imaging = True
                reason = "Max imaging - in window"
            elif state.battery_level_percent > 50:
                # Opportunistic imaging with good battery
                action.enable_imaging = True
                reason = "Opportunistic imaging"
        
        # Aggressive downlink to free storage
        if (state.in_ground_pass_window and 
            state.downlink_time_this_orbit_min < config.downlink_duration_min and
            state.onboard_data_volume_gb > 0.05):
            action.enable_downlink = True
            if action.enable_imaging:
                action.enable_imaging = False
            reason = "Max downlink"
        
        # Always do ADCS dump when possible
        if (state.in_sunlight and 
            state.in_adcs_dump_window and
            state.adcs_dump_time_this_orbit_min < config.adcs_dump_duration_min):
            action.enable_adcs_dump = True
        
        if not reason:
            reason = "High performance idle"
        
        self.log_decision(state, action, reason)
        return action


class CustomizablePolicy(Policy):
    """
    Policy with user-configurable thresholds.
    All thresholds respect 20% SoC minimum constraint.
    """
    
    def __init__(self, 
                 name: str = "CustomizablePolicy",
                 min_battery_imaging: float = 40.0,
                 min_battery_downlink: float = 30.0,
                 min_battery_adcs: float = 25.0,
                 safe_mode_threshold: float = 25.0,
                 enable_opportunistic_imaging: bool = False):
        super().__init__(name=name)
        
        # Enforce minimum thresholds for 20% compliance
        self.min_battery_imaging = max(25.0, min_battery_imaging)
        self.min_battery_downlink = max(22.0, min_battery_downlink)
        self.min_battery_adcs = max(22.0, min_battery_adcs)
        self.safe_mode_threshold = max(22.0, safe_mode_threshold)
        self.enable_opportunistic_imaging = enable_opportunistic_imaging
    
    def evaluate(self, state: SatelliteState, 
                 config: SatelliteConfig) -> PolicyAction:
        action = PolicyAction()
        reason = ""
        
        # Safe mode check (with 20% floor)
        if state.battery_level_percent < self.safe_mode_threshold:
            action.enter_safe_mode = True
            reason = f"Battery < {self.safe_mode_threshold}%"
            self.log_decision(state, action, reason)
            return action
        
        # Imaging
        if state.battery_level_percent >= self.min_battery_imaging:
            if (state.in_sunlight and 
                state.imaging_time_this_orbit_min < config.imaging_duration_min and
                not state.data_storage_full):
                if state.in_imaging_window or self.enable_opportunistic_imaging:
                    action.enable_imaging = True
                    reason = "Imaging"
        
        # Downlink
        if state.battery_level_percent >= self.min_battery_downlink:
            if (state.in_ground_pass_window and 
                state.downlink_time_this_orbit_min < config.downlink_duration_min and
                state.onboard_data_volume_gb > 0):
                action.enable_downlink = True
                action.enable_imaging = False
                reason = "Downlink"
        
        # ADCS dump
        if state.battery_level_percent >= self.min_battery_adcs:
            if (state.in_sunlight and 
                state.in_adcs_dump_window and
                state.adcs_dump_time_this_orbit_min < config.adcs_dump_duration_min):
                action.enable_adcs_dump = True
        
        if not reason:
            reason = "Idle"
        
        self.log_decision(state, action, reason)
        return action
    
    def get_parameters(self) -> Dict[str, Any]:
        """Get current policy parameters."""
        return {
            'min_battery_imaging': self.min_battery_imaging,
            'min_battery_downlink': self.min_battery_downlink,
            'min_battery_adcs': self.min_battery_adcs,
            'safe_mode_threshold': self.safe_mode_threshold,
            'enable_opportunistic_imaging': self.enable_opportunistic_imaging
        }
