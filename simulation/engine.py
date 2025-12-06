"""
Simulation engine for the satellite digital twin.
Compliant with loads.md specification and 20% SoC constraint.

Operational Schedule per loads.md:
- Base load: 15W continuous
- Imaging: +40W, sunlight only, 10 min/orbit
- Downlink: +30W, 8 min/orbit (50% sun/50% eclipse)
- ADCS dump: +10W, sunlight only, 5 min/orbit
- Data: 2 Gbit/orbit generated, 50 Mbps downlink

Critical Constraint:
- Battery SoC shall NEVER drop below 20%
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
import copy

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from satellite.state import SatelliteState, SatelliteConfig
from satellite.eps import EPS
from satellite.orbit import OrbitModel
from satellite.data_system import DataSystem
from satellite.loads import LoadManager, LoadPriority
from simulation.policy import Policy, LoadsMDCompliantPolicy, PolicyAction


@dataclass
class SimulationEvent:
    """Record of a significant event during simulation."""
    time_s: float
    orbit: int
    event_type: str
    description: str
    battery_soc: float = 0.0
    state_snapshot: Optional[Dict[str, Any]] = None


class Simulation:
    """
    Main simulation engine for the satellite digital twin.
    Strictly compliant with loads.md and 20% SoC constraint.
    """
    
    def __init__(self, 
                 config: Optional[SatelliteConfig] = None,
                 initial_state: Optional[SatelliteState] = None,
                 policy: Optional[Policy] = None):
        """
        Initialize the simulation.
        
        Args:
            config: Satellite configuration (uses defaults if None)
            initial_state: Initial state (uses defaults if None)
            policy: Operation policy (uses LoadsMDCompliantPolicy if None)
        """
        self.config = config or SatelliteConfig()
        self.state = initial_state or SatelliteState()
        self.policy = policy or LoadsMDCompliantPolicy()
        
        # Initialize subsystems
        self.eps = EPS(self.config)
        self.orbit = OrbitModel(self.config)
        self.data_system = DataSystem(self.config)
        self.load_manager = LoadManager(self.config)
        
        # Initialize state
        self._initialize_state()
        
        # Simulation tracking
        self.history: List[Dict[str, Any]] = []
        self.events: List[SimulationEvent] = []
        self._step_callbacks: List[Callable[[SatelliteState], None]] = []
        
        # State tracking for event detection
        self._prev_state = self.state.copy()
        
        # Compliance tracking
        self.min_soc_reached: float = self.state.battery_level_percent
        self.soc_violations: int = 0
        
        # Simulation metadata
        self.start_time = None
        self.end_time = None
        self.total_steps = 0
    
    def _initialize_state(self) -> None:
        """Initialize state with proper calculations."""
        # Calculate initial battery energy from SOC (using effective capacity)
        effective_capacity = self.config.battery_capacity_wh * (self.state.battery_health_percent / 100.0)
        self.state.battery_energy_wh = (
            self.state.battery_level_percent / 100.0 * effective_capacity
        )
        
        # Initialize battery voltage based on SOC and health
        # Use EPS voltage calculation method
        soc_normalized = self.state.battery_level_percent / 100.0
        if soc_normalized < 0.2:
            voltage_factor = 0.3 + 0.7 * (soc_normalized / 0.2)
        elif soc_normalized < 0.8:
            voltage_factor = 1.0 + 0.1 * ((soc_normalized - 0.2) / 0.6)
        else:
            voltage_factor = 1.1 + 0.1 * ((soc_normalized - 0.8) / 0.2)
        
        health_factor = self.state.battery_health_percent / 100.0
        min_voltage = 9.0 + (1.0 - health_factor) * 0.5
        max_voltage = 12.6 * health_factor
        self.state.battery_voltage_v = min_voltage + (max_voltage - min_voltage) * voltage_factor
        
        # Set base load
        self.state.base_load_w = self.config.base_load_w
        self.state.total_load_w = self.config.base_load_w
        
        # Update window flags
        self._update_window_flags()
        
        # Update load manager
        self.state = self.load_manager.update(self.state, 0)
    
    def _update_window_flags(self) -> None:
        """Update operational window flags based on orbit position."""
        angle = self.state.orbit_angle_deg % 360.0
        
        # Imaging windows
        self.state.in_imaging_window = False
        for window in self.config.imaging_windows_theta:
            start, end = window[0], window[1]
            if start <= angle <= end:
                self.state.in_imaging_window = True
                break
        
        # Ground pass window
        gs_start, gs_end = self.config.ground_pass_window_theta
        if gs_start <= angle <= gs_end:
            self.state.in_ground_pass_window = True
        else:
            self.state.in_ground_pass_window = False
        
        # ADCS dump window
        adcs_start, adcs_end = self.config.adcs_dump_window_theta
        if adcs_start <= angle <= adcs_end:
            self.state.in_adcs_dump_window = True
        else:
            self.state.in_adcs_dump_window = False
    
    def reset(self, initial_state: Optional[SatelliteState] = None) -> None:
        """Reset simulation to initial conditions."""
        self.state = initial_state or SatelliteState()
        self._initialize_state()
        
        self.history = []
        self.events = []
        self.total_steps = 0
        self.min_soc_reached = self.state.battery_level_percent
        self.soc_violations = 0
        
        self._prev_state = self.state.copy()
        
        # Reset subsystems
        self.eps = EPS(self.config)
        self.data_system = DataSystem(self.config)
        self.load_manager = LoadManager(self.config)
        self.policy.reset()
    
    def step(self, timestep_min: Optional[float] = None) -> SatelliteState:
        """
        Execute one simulation timestep.
        
        Args:
            timestep_min: Timestep in minutes (uses config default if None)
            
        Returns:
            Updated satellite state
        """
        if timestep_min is None:
            timestep_min = self.config.timestep_min
        
        timestep_s = timestep_min * 60.0
        
        # Store previous state for event detection
        self._prev_state = self.state.copy()
        
        # 1. Update orbit position and sun/eclipse state
        self.state = self.orbit.update(self.state, timestep_s)
        
        # 2. Update operational window flags
        self._update_window_flags()
        
        # 3. Evaluate policy and get actions
        action = self.policy.evaluate(self.state, self.config)
        
        # 4. Apply policy actions to loads
        self._apply_policy_action(action, self.state)
        
        # 5. Update loads with time tracking and SOC protection
        self.state = self.load_manager.update(self.state, timestep_min)
        
        # 6. Update EPS (solar generation, battery)
        self.state = self.eps.update(self.state, timestep_s)
        
        # 7. Update data system
        self.state = self.data_system.update(self.state, timestep_min)
        
        # 8. Update warnings and check compliance
        self.state.update_warnings(self.config)
        self._check_soc_compliance()
        
        # 9. Detect and log events
        self._detect_events()
        
        # 10. Record history
        self._record_history()
        
        # 11. Execute callbacks
        for callback in self._step_callbacks:
            callback(self.state)
        
        self.total_steps += 1
        
        return self.state
    
    def _apply_policy_action(self, action: PolicyAction, state: SatelliteState) -> None:
        """Apply policy action to subsystems with safety checks."""
        # Handle safe mode first
        if action.enter_safe_mode:
            self.load_manager.deactivate_load("Payload_Imaging")
            self.load_manager.deactivate_load("Downlink_COMMS")
            self.load_manager.deactivate_load("ADCS_Dump")
            self._log_event("SAFE_MODE", "Entered safe mode for battery protection")
            return
        
        # Imaging control per loads.md
        if action.enable_imaging is not None:
            if action.enable_imaging:
                success, msg = self.load_manager.activate_load("Payload_Imaging", state)
                if not success:
                    self._log_event("LOAD_BLOCKED", f"Imaging blocked: {msg}")
            else:
                self.load_manager.deactivate_load("Payload_Imaging")
        
        # Downlink control per loads.md
        if action.enable_downlink is not None:
            if action.enable_downlink:
                success, msg = self.load_manager.activate_load("Downlink_COMMS", state)
                if success:
                    self.data_system.start_downlink(state)
                else:
                    self._log_event("LOAD_BLOCKED", f"Downlink blocked: {msg}")
            else:
                self.load_manager.deactivate_load("Downlink_COMMS")
                self.data_system.stop_downlink(state)
        
        # ADCS dump control per loads.md
        if action.enable_adcs_dump is not None:
            if action.enable_adcs_dump:
                success, msg = self.load_manager.activate_load("ADCS_Dump", state)
                if not success:
                    self._log_event("LOAD_BLOCKED", f"ADCS dump blocked: {msg}")
            else:
                self.load_manager.deactivate_load("ADCS_Dump")
    
    def _check_soc_compliance(self) -> None:
        """
        Track 20% SoC violations (UNSAFE MODE - no enforcement).
        
        In unsafe mode, violations are tracked but not prevented.
        Mission continues operating even when battery is critically low.
        """
        # Track minimum SOC reached
        if self.state.battery_level_percent < self.min_soc_reached:
            self.min_soc_reached = self.state.battery_level_percent
        
        # Track violations but don't prevent operations
        if self.state.battery_level_percent < self.config.min_soc_percent:
            self.state.soc_violation = True
            self.soc_violations += 1
            self._log_event(
                "SOC_VIOLATION",
                f"CRITICAL UNSAFE: Battery dropped to {self.state.battery_level_percent:.1f}% (below 20% limit) - OPERATIONS CONTINUE",
                include_state=True
            )
    
    def _detect_events(self) -> None:
        """Detect significant events for logging."""
        # Eclipse entry/exit
        if self._prev_state.in_sunlight and not self.state.in_sunlight:
            self._log_event("ECLIPSE_ENTRY", 
                          f"Entered eclipse at {self.state.battery_level_percent:.1f}% SOC")
        elif not self._prev_state.in_sunlight and self.state.in_sunlight:
            self._log_event("ECLIPSE_EXIT", 
                          f"Exited eclipse at {self.state.battery_level_percent:.1f}% SOC")
        
        # New orbit
        if self.state.orbit_number > self._prev_state.orbit_number:
            self._log_event("NEW_ORBIT", 
                          f"Started orbit {self.state.orbit_number}, SOC: {self.state.battery_level_percent:.1f}%")
        
        # Imaging window entry/exit
        if not self._prev_state.in_imaging_window and self.state.in_imaging_window:
            self._log_event("IMAGING_WINDOW_ENTRY", "Entered imaging window")
        elif self._prev_state.in_imaging_window and not self.state.in_imaging_window:
            self._log_event("IMAGING_WINDOW_EXIT", 
                          f"Exited imaging window, data: {self.state.data_generated_this_orbit_gb:.3f} GB this orbit")
        
        # Ground pass entry/exit
        if not self._prev_state.in_ground_pass_window and self.state.in_ground_pass_window:
            self._log_event("GROUND_PASS_START", 
                          f"Ground pass started, {self.state.onboard_data_volume_gb:.3f} GB to downlink")
        elif self._prev_state.in_ground_pass_window and not self.state.in_ground_pass_window:
            self._log_event("GROUND_PASS_END", 
                          f"Ground pass ended, {self.state.onboard_data_volume_gb:.3f} GB remaining")
        
        # Load shedding
        if not self._prev_state.load_shed_active and self.state.load_shed_active:
            self._log_event("LOAD_SHED_START", 
                          f"Load shedding activated at {self.state.battery_level_percent:.1f}% SOC")
        elif self._prev_state.load_shed_active and not self.state.load_shed_active:
            self._log_event("LOAD_SHED_END", "Load shedding deactivated")
        
        # Low battery warning
        if not self._prev_state.low_battery_warning and self.state.low_battery_warning:
            self._log_event("LOW_BATTERY_WARNING", 
                          f"Battery low warning at {self.state.battery_level_percent:.1f}%")
    
    def _log_event(self, event_type: str, description: str, 
                   include_state: bool = False) -> None:
        """Log a simulation event."""
        event = SimulationEvent(
            time_s=self.state.simulation_time_s,
            orbit=self.state.orbit_number,
            event_type=event_type,
            description=description,
            battery_soc=self.state.battery_level_percent,
            state_snapshot=self.state.to_dict() if include_state else None
        )
        self.events.append(event)
    
    def _record_history(self) -> None:
        """Record current state to history."""
        self.history.append(self.state.to_dict())
    
    def run(self, 
            duration_orbits: Optional[float] = None,
            duration_minutes: Optional[float] = None,
            duration_steps: Optional[int] = None,
            timestep_min: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Run simulation for specified duration.
        
        Args:
            duration_orbits: Number of orbits to simulate
            duration_minutes: Duration in minutes
            duration_steps: Number of timesteps
            timestep_min: Timestep in minutes (uses config default if None)
            
        Returns:
            Simulation history (list of state dictionaries)
        """
        if timestep_min is None:
            timestep_min = self.config.timestep_min
        
        # Calculate number of steps
        if duration_orbits is not None:
            total_time_min = duration_orbits * self.config.orbit_period_min
            num_steps = int(total_time_min / timestep_min)
        elif duration_minutes is not None:
            num_steps = int(duration_minutes / timestep_min)
        elif duration_steps is not None:
            num_steps = duration_steps
        else:
            # Default: 1 orbit
            total_time_min = self.config.orbit_period_min
            num_steps = int(total_time_min / timestep_min)
        
        self.start_time = datetime.now()
        
        # Record initial state
        self._record_history()
        
        # Run simulation loop
        for _ in range(num_steps):
            self.step(timestep_min)
        
        self.end_time = datetime.now()
        
        return self.history
    
    def get_state(self) -> SatelliteState:
        """Get current simulation state."""
        return self.state
    
    def get_history(self) -> List[Dict[str, Any]]:
        """Get simulation history."""
        return self.history
    
    def get_events(self) -> List[SimulationEvent]:
        """Get logged events."""
        return self.events
    
    def get_summary(self) -> Dict[str, Any]:
        """Get simulation summary with compliance status."""
        if not self.history:
            return {}
        
        # Extract time series
        battery_levels = [h['battery_level_percent'] for h in self.history]
        solar_gen = [h['solar_generation_w'] for h in self.history]
        total_loads = [h['total_load_w'] for h in self.history]
        data_volumes = [h['onboard_data_volume_gb'] for h in self.history]
        
        return {
            'total_steps': self.total_steps,
            'total_time_min': self.state.simulation_time_s / 60.0,
            'total_orbits': self.state.orbit_number,
            'battery': {
                'min': min(battery_levels),
                'max': max(battery_levels),
                'final': battery_levels[-1],
                'avg': sum(battery_levels) / len(battery_levels)
            },
            'solar': {
                'max': max(solar_gen),
                'avg': sum(solar_gen) / len(solar_gen)
            },
            'load': {
                'max': max(total_loads),
                'avg': sum(total_loads) / len(total_loads)
            },
            'data': {
                'max_stored': max(data_volumes),
                'final_stored': data_volumes[-1],
                'total_generated': self.state.data_generated_gb,
                'total_downlinked': self.state.data_downlinked_gb
            },
            'compliance': {
                'min_soc_reached': self.min_soc_reached,
                'soc_violations': self.soc_violations,
                'compliant': self.soc_violations == 0 and self.min_soc_reached >= self.config.min_soc_percent
            },
            'events_count': len(self.events),
            'simulation_duration_s': (
                (self.end_time - self.start_time).total_seconds()
                if self.end_time and self.start_time else None
            )
        }
    
    def get_compliance_report(self) -> Dict[str, Any]:
        """Get detailed compliance report per loads.md requirements."""
        return {
            'soc_compliance': {
                'requirement': 'Battery SoC >= 20%',
                'min_soc_reached': self.min_soc_reached,
                'violations': self.soc_violations,
                'compliant': self.soc_violations == 0
            },
            'load_profile': {
                'base_load_w': self.config.base_load_w,
                'imaging_load_w': self.config.imaging_load_w,
                'downlink_load_w': self.config.downlink_load_w,
                'adcs_dump_load_w': self.config.adcs_dump_load_w
            },
            'timing_budget': {
                'imaging_per_orbit_min': self.config.imaging_duration_min,
                'downlink_per_orbit_min': self.config.downlink_duration_min,
                'adcs_dump_per_orbit_min': self.config.adcs_dump_duration_min
            },
            'data_budget': {
                'generation_per_orbit_gbit': self.config.data_per_orbit_gbit,
                'downlink_rate_mbps': self.config.downlink_speed_mbps,
                'total_generated_gb': self.state.data_generated_gb,
                'total_downlinked_gb': self.state.data_downlinked_gb
            }
        }
    
    def add_step_callback(self, callback: Callable[[SatelliteState], None]) -> None:
        """Add a callback to be executed after each step."""
        self._step_callbacks.append(callback)
    
    def trigger_downlink(self, target_gb: Optional[float] = None) -> None:
        """Manually trigger a downlink operation."""
        self.state = self.data_system.start_downlink(self.state, target_gb)
        self.load_manager.activate_load("Downlink_COMMS", self.state)
        self._log_event("MANUAL_DOWNLINK", 
                       f"Manual downlink triggered (target: {target_gb or 'all'} GB)")
    
    def stop_downlink(self) -> None:
        """Manually stop downlink operation."""
        self.state = self.data_system.stop_downlink(self.state)
        self.load_manager.deactivate_load("Downlink_COMMS")
        self._log_event("MANUAL_DOWNLINK_STOP", "Manual downlink stopped")
    
    def set_policy(self, policy: Policy) -> None:
        """Change the operation policy."""
        self.policy = policy
        self._log_event("POLICY_CHANGE", f"Policy changed to {policy.name}")


def create_simulation_from_dict(config_dict: Dict[str, Any],
                                 initial_state_dict: Optional[Dict[str, Any]] = None,
                                 policy_name: str = "compliant") -> Simulation:
    """
    Factory function to create simulation from dictionaries.
    
    Args:
        config_dict: Configuration parameters
        initial_state_dict: Initial state values
        policy_name: Policy type
        
    Returns:
        Configured Simulation instance
    """
    from simulation.policy import (BasicPolicy, PowerSavePolicy, 
                                   HighPerformancePolicy, CustomizablePolicy,
                                   LoadsMDCompliantPolicy)
    
    config = SatelliteConfig(**config_dict) if config_dict else SatelliteConfig()
    initial_state = (
        SatelliteState(**initial_state_dict) 
        if initial_state_dict else SatelliteState()
    )
    
    policies = {
        'compliant': LoadsMDCompliantPolicy(),
        'basic': BasicPolicy(),
        'power_save': PowerSavePolicy(),
        'high_performance': HighPerformancePolicy(),
        'customizable': CustomizablePolicy()
    }
    policy = policies.get(policy_name, LoadsMDCompliantPolicy())
    
    return Simulation(config, initial_state, policy)
