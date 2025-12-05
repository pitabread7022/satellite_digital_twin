"""
Spacecraft State Model

Defines the complete state vector and configuration parameters for the
satellite digital twin simulation.

Reference: loads.md specification

Power Budget:
    - Platform base load: 15W continuous
    - Payload imaging: +40W (sunlight only, 10 min/orbit)
    - Downlink: +30W (8 min/orbit, 50% sun/50% eclipse)
    - ADCS momentum dump: +10W (sunlight only, 5 min/orbit)

Data Budget:
    - Generation: 2 Gbit per orbit during imaging
    - Downlink: 50 Mbps for 8 minutes

Constraint:
    - Battery State of Charge >= 20%
"""

from dataclasses import dataclass, field, asdict
from typing import List, Tuple
import copy


@dataclass
class SatelliteConfig:
    """
    Spacecraft configuration parameters.
    
    All parameters are constants that define the physical characteristics
    and operational limits of the spacecraft subsystems.
    """
    
    # Spacecraft physical properties
    mass_kg: float = 50.0
    
    # Orbital parameters
    orbit_altitude_km: float = 500.0
    orbit_period_min: float = 95.0
    sunlight_duration_min: float = 60.0
    eclipse_duration_min: float = 35.0
    
    # Electrical Power System
    solar_panel_power_w: float = 60.0
    battery_capacity_wh: float = 100.0
    min_soc_percent: float = 20.0  # CONSTRAINT: Never below 20%
    max_soc_percent: float = 100.0
    charge_efficiency: float = 0.95
    discharge_efficiency: float = 0.95
    max_charge_rate_w: float = 40.0
    max_discharge_rate_w: float = 60.0
    
    # Power budget [loads.md]
    base_load_w: float = 15.0
    imaging_load_w: float = 40.0
    downlink_load_w: float = 30.0
    adcs_dump_load_w: float = 10.0
    
    # Operations timing [loads.md]
    imaging_duration_min: float = 10.0
    downlink_duration_min: float = 8.0
    adcs_dump_duration_min: float = 5.0
    downlink_sunlight_fraction: float = 0.5
    
    # Data budget [loads.md]
    max_data_storage_gb: float = 100.0
    data_per_orbit_gbit: float = 2.0
    downlink_speed_mbps: float = 50.0
    uplink_speed_mbps: float = 1.0
    
    @property
    def data_generation_rate_gb_per_min(self) -> float:
        """Data generation rate during imaging [GB/min]."""
        return (self.data_per_orbit_gbit / 8.0) / self.imaging_duration_min
    
    @property
    def downlink_speed_gb_per_min(self) -> float:
        """Downlink data rate [GB/min]."""
        return (self.downlink_speed_mbps / 8.0) * 60.0 / 1000.0
    
    @property
    def data_per_downlink_gb(self) -> float:
        """Maximum data volume per ground pass [GB]."""
        return self.downlink_speed_gb_per_min * self.downlink_duration_min
    
    # Operational windows [orbit angle in degrees]
    imaging_windows_theta: List[Tuple[float, float]] = field(
        default_factory=lambda: [[20.0, 40.0]]
    )
    shutter_speed_ms: float = 20.0
    
    ground_pass_window_theta: Tuple[float, float] = field(
        default_factory=lambda: (95.0, 125.0)
    )
    
    adcs_dump_window_theta: Tuple[float, float] = field(
        default_factory=lambda: (50.0, 70.0)
    )
    
    # Simulation parameters
    timestep_min: float = 1.0
    soc_safety_margin_percent: float = 5.0
    
    def to_dict(self) -> dict:
        """Serialize configuration to dictionary."""
        d = asdict(self)
        d['data_generation_rate_gb_per_min'] = self.data_generation_rate_gb_per_min
        d['downlink_speed_gb_per_min'] = self.downlink_speed_gb_per_min
        d['data_per_downlink_gb'] = self.data_per_downlink_gb
        return d
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SatelliteConfig':
        """Deserialize configuration from dictionary."""
        data = {k: v for k, v in data.items() 
                if k not in ['data_generation_rate_gb_per_min', 
                            'downlink_speed_gb_per_min',
                            'data_per_downlink_gb']}
        return cls(**data)


@dataclass
class SatelliteState:
    """
    Complete spacecraft state vector.
    
    Contains all mutable variables that define the instantaneous state
    of the spacecraft during simulation.
    
    Constraint: Battery SoC >= 20% during nominal operations.
    """
    
    # Time
    simulation_time_s: float = 0.0
    orbit_number: int = 0
    orbit_angle_deg: float = 0.0
    orbit_phase_min: float = 0.0
    
    # Electrical Power System
    battery_level_percent: float = 80.0
    battery_voltage_v: float = 12.5
    battery_energy_wh: float = 80.0
    solar_generation_w: float = 0.0
    in_sunlight: bool = True
    net_power_w: float = 0.0
    
    # Load state [loads.md]
    total_load_w: float = 15.0
    base_load_w: float = 15.0
    payload_load_w: float = 0.0
    comms_load_w: float = 0.0
    adcs_dump_load_w: float = 0.0
    heater_load_w: float = 0.0
    
    # Operations mode
    is_imaging: bool = False
    is_downlinking: bool = False
    is_adcs_dumping: bool = False
    
    # Data system [loads.md]
    onboard_data_volume_gb: float = 0.0
    data_generated_gb: float = 0.0
    data_downlinked_gb: float = 0.0
    data_generated_this_orbit_gb: float = 0.0
    
    # Operational windows
    in_imaging_window: bool = False
    in_ground_pass_window: bool = False
    in_adcs_dump_window: bool = False
    
    # Per-orbit timing
    imaging_time_this_orbit_min: float = 0.0
    downlink_time_this_orbit_min: float = 0.0
    adcs_dump_time_this_orbit_min: float = 0.0
    
    # Environment
    temperature_c: float = 287.0
    pressure_pa: float = 0.001
    
    # Health
    battery_health_percent: float = 97.0
    battery_cycles: int = 0
    
    # Status flags
    low_battery_warning: bool = False
    high_battery_warning: bool = False
    data_storage_full: bool = False
    soc_violation: bool = False
    load_shed_active: bool = False
    
    def copy(self) -> 'SatelliteState':
        """Create deep copy of state."""
        return copy.deepcopy(self)
    
    def to_dict(self) -> dict:
        """Serialize state to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SatelliteState':
        """Deserialize state from dictionary."""
        return cls(**data)
    
    def update_warnings(self, config: SatelliteConfig) -> None:
        """Update status flags based on current state."""
        warning_threshold = config.min_soc_percent + config.soc_safety_margin_percent
        self.low_battery_warning = self.battery_level_percent <= warning_threshold
        self.high_battery_warning = self.battery_level_percent >= 95.0
        self.data_storage_full = self.onboard_data_volume_gb >= config.max_data_storage_gb * 0.95
        
        if self.battery_level_percent < config.min_soc_percent:
            self.soc_violation = True
    
    def get_summary(self) -> str:
        """Generate human-readable state summary."""
        mode = []
        if self.is_imaging:
            mode.append("IMG")
        if self.is_downlinking:
            mode.append("DL")
        if self.is_adcs_dumping:
            mode.append("ADCS")
        mode_str = "+".join(mode) if mode else "IDLE"
        
        sun_str = "SUN" if self.in_sunlight else "ECL"
        violation = " [SOC VIOLATION]" if self.soc_violation else ""
        
        return (
            f"T+{self.simulation_time_s/60:.0f}m | "
            f"ORB:{self.orbit_number}@{self.orbit_angle_deg:.0f}deg | "
            f"SOC:{self.battery_level_percent:.1f}% | "
            f"PWR:{self.solar_generation_w:.0f}-{self.total_load_w:.0f}={self.net_power_w:.0f}W | "
            f"DATA:{self.onboard_data_volume_gb:.3f}GB | "
            f"{sun_str} {mode_str}{violation}"
        )
    
    def get_load_breakdown(self) -> dict:
        """Return detailed load breakdown per loads.md categories."""
        return {
            'base_load_w': self.base_load_w,
            'imaging_load_w': self.payload_load_w,
            'downlink_load_w': self.comms_load_w,
            'adcs_dump_load_w': self.adcs_dump_load_w,
            'total_load_w': self.total_load_w
        }
