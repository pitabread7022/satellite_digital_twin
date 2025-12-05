"""
Load management system for the satellite.
Compliant with loads.md specification:

## Platform base load
15 W continuous (ADCS, OBC, COMMS idle, etc.)

## Payload imaging
+40 W during imaging (imaging only in sunlight)
Nominal: 10 minutes of imaging per orbit, entirely within sunlight

## Downlink (high-rate COMMS)
+30 W during ground contact
One ground pass per orbit, lasting 8 minutes
Assume 50% of passes occur in sunlight, 50% in eclipse

## Special ADCS mode / momentum dump
+10 W for 5 minutes per orbit, in sunlight

## Battery Constraint
Battery SoC shall never drop below 20% during nominal operations
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum

from .state import SatelliteState, SatelliteConfig


class LoadPriority(Enum):
    """Priority levels for load shedding to maintain 20% SoC."""
    CRITICAL = 1     # Base load - cannot be turned off
    HIGH = 2         # ADCS dump - important but can be deferred
    MEDIUM = 3       # Downlink - can be deferred
    LOW = 4          # Imaging - first to be shed


@dataclass
class Load:
    """Definition of a single power load per loads.md."""
    name: str
    power_w: float
    priority: LoadPriority
    is_active: bool = False
    requires_sunlight: bool = False  # Per loads.md: imaging and ADCS only in sunlight
    max_duration_per_orbit_min: float = 0.0  # 0 = unlimited
    description: str = ""
    
    def get_current_power(self) -> float:
        """Get current power consumption."""
        return self.power_w if self.is_active else 0.0


class LoadManager:
    """
    Manages all power loads on the satellite per loads.md specification.
    
    Load Profile:
    - Base: 15W continuous (ADCS, OBC, COMMS idle)
    - Imaging: +40W (sunlight only, 10 min/orbit max)
    - Downlink: +30W (8 min/orbit, 50% sun/50% eclipse)
    - ADCS dump: +10W (sunlight only, 5 min/orbit)
    
    Critical Constraint:
    - Battery SoC shall NEVER drop below 20%
    - Load shedding is automatic when approaching 20% limit
    """
    
    # Loads per loads.md specification
    LOADS_MD_SPEC = [
        Load(
            name="Platform_Base",
            power_w=15.0,
            priority=LoadPriority.CRITICAL,
            is_active=True,  # Always on
            requires_sunlight=False,
            max_duration_per_orbit_min=0,  # Continuous
            description="Platform base load (ADCS, OBC, COMMS idle)"
        ),
        Load(
            name="Payload_Imaging",
            power_w=40.0,
            priority=LoadPriority.LOW,
            is_active=False,
            requires_sunlight=True,  # Imaging only in sunlight
            max_duration_per_orbit_min=10.0,
            description="Payload imaging (+40W, sunlight only, 10 min/orbit)"
        ),
        Load(
            name="Downlink_COMMS",
            power_w=30.0,
            priority=LoadPriority.MEDIUM,
            is_active=False,
            requires_sunlight=False,  # Can operate in eclipse
            max_duration_per_orbit_min=8.0,
            description="High-rate downlink (+30W, 8 min/orbit)"
        ),
        Load(
            name="ADCS_Dump",
            power_w=10.0,
            priority=LoadPriority.HIGH,
            is_active=False,
            requires_sunlight=True,  # Momentum dump in sunlight
            max_duration_per_orbit_min=5.0,
            description="ADCS momentum dump (+10W, sunlight, 5 min/orbit)"
        ),
    ]
    
    def __init__(self, config: SatelliteConfig, 
                 custom_loads: Optional[List[Load]] = None):
        self.config = config
        self.loads: Dict[str, Load] = {}
        
        # Initialize with loads.md specification
        loads_to_add = custom_loads if custom_loads else self.LOADS_MD_SPEC
        for load in loads_to_add:
            self.add_load(load)
        
        # Track time usage per orbit for each load
        self._orbit_time_used: Dict[str, float] = {
            "Payload_Imaging": 0.0,
            "Downlink_COMMS": 0.0,
            "ADCS_Dump": 0.0
        }
        self._current_orbit = 0
    
    def add_load(self, load: Load) -> None:
        """Add a load to the system."""
        self.loads[load.name] = load
    
    def remove_load(self, name: str) -> bool:
        """Remove a load from the system."""
        if name in self.loads and name != "Platform_Base":
            del self.loads[name]
            return True
        return False
    
    def reset_orbit_timers(self) -> None:
        """Reset per-orbit time tracking (call at start of each orbit)."""
        for key in self._orbit_time_used:
            self._orbit_time_used[key] = 0.0
    
    def can_activate_load(self, name: str, state: SatelliteState) -> Tuple[bool, str]:
        """
        Check if a load can be activated given current state.
        
        Returns:
            Tuple of (can_activate, reason_if_not)
        """
        if name not in self.loads:
            return False, "Load not found"
        
        load = self.loads[name]
        
        # Check sunlight requirement
        if load.requires_sunlight and not state.in_sunlight:
            return False, f"{name} requires sunlight"
        
        # Check per-orbit time limit
        if load.max_duration_per_orbit_min > 0:
            time_used = self._orbit_time_used.get(name, 0.0)
            if time_used >= load.max_duration_per_orbit_min:
                return False, f"{name} reached {load.max_duration_per_orbit_min} min limit this orbit"
        
        # Check battery level - prevent activation if it would violate 20% SoC
        if not self._check_battery_safe(state, load.power_w):
            return False, f"Battery too low to activate {name} (20% SoC protection)"
        
        return True, "OK"
    
    def _check_battery_safe(self, state: SatelliteState, additional_load_w: float) -> bool:
        """
        Check if adding load is safe for 20% SoC compliance.
        
        Conservative check: ensure we can survive worst-case eclipse
        with the additional load.
        """
        # If in sunlight with positive net power, generally safe
        current_net = state.solar_generation_w - state.total_load_w
        new_net = current_net - additional_load_w
        
        if state.in_sunlight and new_net >= 0:
            return True
        
        # Calculate energy needed to survive eclipse at new load level
        eclipse_duration_h = self.config.eclipse_duration_min / 60.0
        total_load_in_eclipse = self.config.base_load_w + additional_load_w
        
        # Energy needed for eclipse (with safety margin)
        energy_needed_wh = (total_load_in_eclipse * eclipse_duration_h 
                           / self.config.discharge_efficiency)
        
        # Available energy above 20% minimum
        min_energy_wh = self.config.battery_capacity_wh * (self.config.min_soc_percent / 100.0)
        safety_margin_wh = self.config.battery_capacity_wh * (self.config.soc_safety_margin_percent / 100.0)
        available_energy_wh = state.battery_energy_wh - min_energy_wh - safety_margin_wh
        
        return available_energy_wh >= energy_needed_wh
    
    def activate_load(self, name: str, state: SatelliteState, 
                      force: bool = False) -> Tuple[bool, str]:
        """
        Activate a specific load with safety checks.
        
        Args:
            name: Load name
            state: Current satellite state
            force: Bypass safety checks (not recommended)
            
        Returns:
            Tuple of (success, message)
        """
        if name not in self.loads:
            return False, "Load not found"
        
        if name == "Platform_Base":
            return True, "Base load is always active"
        
        if not force:
            can_activate, reason = self.can_activate_load(name, state)
            if not can_activate:
                return False, reason
        
        self.loads[name].is_active = True
        return True, f"{name} activated"
    
    def deactivate_load(self, name: str) -> bool:
        """Deactivate a specific load."""
        if name in self.loads and name != "Platform_Base":
            self.loads[name].is_active = False
            return True
        return False
    
    def update(self, state: SatelliteState, timestep_min: float = 1.0) -> SatelliteState:
        """
        Update state with current load calculations and enforce constraints.
        
        Args:
            state: Current satellite state
            timestep_min: Timestep in minutes for time tracking
            
        Returns:
            Updated satellite state
        """
        # Check for new orbit - reset timers
        if state.orbit_number > self._current_orbit:
            self.reset_orbit_timers()
            self._current_orbit = state.orbit_number
            state.imaging_time_this_orbit_min = 0.0
            state.downlink_time_this_orbit_min = 0.0
            state.adcs_dump_time_this_orbit_min = 0.0
            state.data_generated_this_orbit_gb = 0.0
        
        # Enforce sunlight constraints
        self._enforce_sunlight_constraints(state)
        
        # Enforce per-orbit time limits
        self._enforce_time_limits(state)
        
        # CRITICAL: Load shedding to protect 20% SoC
        self._enforce_soc_protection(state)
        
        # Update time tracking for active loads
        self._update_time_tracking(state, timestep_min)
        
        # Calculate total load
        state.base_load_w = self.loads["Platform_Base"].power_w
        state.payload_load_w = self.loads["Payload_Imaging"].get_current_power()
        state.comms_load_w = self.loads["Downlink_COMMS"].get_current_power()
        state.adcs_dump_load_w = self.loads["ADCS_Dump"].get_current_power()
        
        state.total_load_w = (
            state.base_load_w + 
            state.payload_load_w + 
            state.comms_load_w + 
            state.adcs_dump_load_w +
            state.heater_load_w
        )
        
        # Update mode flags
        state.is_imaging = self.loads["Payload_Imaging"].is_active
        state.is_downlinking = self.loads["Downlink_COMMS"].is_active
        state.is_adcs_dumping = self.loads["ADCS_Dump"].is_active
        
        return state
    
    def _enforce_sunlight_constraints(self, state: SatelliteState) -> None:
        """Enforce sunlight-only constraints per loads.md."""
        if not state.in_sunlight:
            # Imaging only in sunlight
            if self.loads["Payload_Imaging"].is_active:
                self.loads["Payload_Imaging"].is_active = False
            
            # ADCS dump only in sunlight
            if self.loads["ADCS_Dump"].is_active:
                self.loads["ADCS_Dump"].is_active = False
    
    def _enforce_time_limits(self, state: SatelliteState) -> None:
        """Enforce per-orbit time limits per loads.md."""
        # Imaging: 10 min/orbit max
        if (self._orbit_time_used.get("Payload_Imaging", 0) >= 
            self.config.imaging_duration_min):
            self.loads["Payload_Imaging"].is_active = False
        
        # Downlink: 8 min/orbit max
        if (self._orbit_time_used.get("Downlink_COMMS", 0) >= 
            self.config.downlink_duration_min):
            self.loads["Downlink_COMMS"].is_active = False
        
        # ADCS dump: 5 min/orbit max
        if (self._orbit_time_used.get("ADCS_Dump", 0) >= 
            self.config.adcs_dump_duration_min):
            self.loads["ADCS_Dump"].is_active = False
    
    def _enforce_soc_protection(self, state: SatelliteState) -> None:
        """
        CRITICAL: Automatic load shedding to maintain 20% SoC minimum.
        
        Load shedding priority (lowest priority shed first):
        1. Imaging (LOW) - first to shed
        2. Downlink (MEDIUM) - second to shed  
        3. ADCS dump (HIGH) - third to shed
        4. Base load (CRITICAL) - never shed
        """
        warning_threshold = self.config.min_soc_percent + self.config.soc_safety_margin_percent
        
        if state.battery_level_percent <= warning_threshold:
            state.load_shed_active = True
            
            # Calculate if we're draining battery
            net_power = state.solar_generation_w - state.total_load_w
            
            if net_power < 0:  # Draining battery
                # Shed loads in priority order until positive or base only
                
                # 1. First shed imaging (priority LOW)
                if self.loads["Payload_Imaging"].is_active:
                    self.loads["Payload_Imaging"].is_active = False
                    return
                
                # 2. Then shed downlink (priority MEDIUM)  
                if self.loads["Downlink_COMMS"].is_active:
                    self.loads["Downlink_COMMS"].is_active = False
                    return
                
                # 3. Finally shed ADCS dump (priority HIGH)
                if self.loads["ADCS_Dump"].is_active:
                    self.loads["ADCS_Dump"].is_active = False
                    return
        else:
            state.load_shed_active = False
    
    def _update_time_tracking(self, state: SatelliteState, timestep_min: float) -> None:
        """Update per-orbit time tracking for each load."""
        if self.loads["Payload_Imaging"].is_active:
            self._orbit_time_used["Payload_Imaging"] = (
                self._orbit_time_used.get("Payload_Imaging", 0) + timestep_min
            )
            state.imaging_time_this_orbit_min += timestep_min
        
        if self.loads["Downlink_COMMS"].is_active:
            self._orbit_time_used["Downlink_COMMS"] = (
                self._orbit_time_used.get("Downlink_COMMS", 0) + timestep_min
            )
            state.downlink_time_this_orbit_min += timestep_min
        
        if self.loads["ADCS_Dump"].is_active:
            self._orbit_time_used["ADCS_Dump"] = (
                self._orbit_time_used.get("ADCS_Dump", 0) + timestep_min
            )
            state.adcs_dump_time_this_orbit_min += timestep_min
    
    def get_total_load(self) -> float:
        """Calculate total current power consumption."""
        return sum(load.get_current_power() for load in self.loads.values())
    
    def get_load_breakdown(self) -> Dict[str, float]:
        """Get breakdown of all loads and their current power."""
        return {
            name: load.get_current_power() 
            for name, load in self.loads.items()
        }
    
    def get_orbit_time_remaining(self) -> Dict[str, float]:
        """Get remaining time budget for each load this orbit."""
        return {
            "Payload_Imaging": max(0, self.config.imaging_duration_min - 
                                   self._orbit_time_used.get("Payload_Imaging", 0)),
            "Downlink_COMMS": max(0, self.config.downlink_duration_min - 
                                 self._orbit_time_used.get("Downlink_COMMS", 0)),
            "ADCS_Dump": max(0, self.config.adcs_dump_duration_min - 
                            self._orbit_time_used.get("ADCS_Dump", 0))
        }
    
    def get_status(self) -> dict:
        """Get detailed load status per loads.md compliance."""
        return {
            'total_load_w': self.get_total_load(),
            'load_breakdown': self.get_load_breakdown(),
            'active_loads': [
                name for name, load in self.loads.items() if load.is_active
            ],
            'orbit_time_used': dict(self._orbit_time_used),
            'orbit_time_remaining': self.get_orbit_time_remaining(),
            'base_load_w': self.loads["Platform_Base"].power_w,
            'max_load_w': sum(load.power_w for load in self.loads.values())
        }
    
    def get_power_scenarios(self) -> Dict[str, float]:
        """Get power consumption for different operational scenarios."""
        base = self.loads["Platform_Base"].power_w
        return {
            'base_only': base,  # 15W
            'base_imaging': base + self.loads["Payload_Imaging"].power_w,  # 55W
            'base_downlink': base + self.loads["Downlink_COMMS"].power_w,  # 45W
            'base_adcs_dump': base + self.loads["ADCS_Dump"].power_w,  # 25W
            'base_imaging_adcs': (base + 
                                  self.loads["Payload_Imaging"].power_w +
                                  self.loads["ADCS_Dump"].power_w),  # 65W (peak)
            'max_all_active': sum(load.power_w for load in self.loads.values())  # 95W
        }
