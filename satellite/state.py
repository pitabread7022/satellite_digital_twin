"""
Satellite state model - contains all state variables for the digital twin.

Compliant with loads.md specification:
- Platform base load: 15W continuous
- Payload imaging: +40W (sunlight only, 10 min/orbit)
- Downlink: +30W (8 min/orbit, 50% sun/50% eclipse)
- ADCS momentum dump: +10W (5 min/orbit, sunlight)
- Data: 2 Gbit/orbit generated, 50 Mbps downlink
- Battery SoC shall never drop below 20%
"""

from dataclasses import dataclass, field, asdict
from typing import List, Tuple
import copy


@dataclass
class SatelliteConfig:
    """
    Configuration parameters for the satellite (constants/settings).
    
    Compliant with loads.md specification.
    """
    
    # Satellite physical properties
    mass_kg: float = 50.0  # Satellite mass (1-100 kg typical)
    
    # Orbit parameters
    orbit_altitude_km: float = 500.0
    orbit_period_min: float = 95.0  # Orbital period in minutes
    sunlight_duration_min: float = 60.0  # Sunlight per orbit
    eclipse_duration_min: float = 35.0  # Eclipse per orbit
    
    # EPS parameters
    solar_panel_power_w: float = 60.0  # Max solar panel output
    battery_capacity_wh: float = 100.0  # Battery capacity
    min_soc_percent: float = 20.0  # STRICT: Battery SoC shall never drop below 20%
    max_soc_percent: float = 100.0  # Maximum state of charge (allow full charge)
    charge_efficiency: float = 0.95  # Battery charge efficiency
    discharge_efficiency: float = 0.95  # Battery discharge efficiency
    max_charge_rate_w: float = 40.0  # Max charging power
    max_discharge_rate_w: float = 60.0  # Max discharge power
    
    # Load parameters (from loads.md)
    base_load_w: float = 15.0  # Platform base load (ADCS, OBC, COMMS idle)
    imaging_load_w: float = 40.0  # Additional load during imaging
    downlink_load_w: float = 30.0  # Additional load during ground contact
    adcs_dump_load_w: float = 10.0  # Additional load during momentum dump
    
    # Operational timing (from loads.md)
    imaging_duration_min: float = 10.0  # Imaging duration per orbit
    downlink_duration_min: float = 8.0  # Ground pass duration per orbit
    adcs_dump_duration_min: float = 5.0  # Momentum dump duration per orbit
    downlink_sunlight_fraction: float = 0.5  # 50% of passes in sunlight
    
    # Data system parameters (from loads.md)
    max_data_storage_gb: float = 100.0  # Max onboard storage
    data_per_orbit_gbit: float = 2.0  # 2 Gbit generated per orbit
    downlink_speed_mbps: float = 50.0  # 50 Mbps downlink rate
    uplink_speed_mbps: float = 1.0  # Uplink rate
    
    # Computed data rates
    @property
    def data_generation_rate_gb_per_min(self) -> float:
        """Data generation rate during imaging (GB/min)."""
        # 2 Gbit per orbit over 10 minutes = 0.2 Gbit/min = 0.025 GB/min
        return (self.data_per_orbit_gbit / 8.0) / self.imaging_duration_min
    
    @property
    def downlink_speed_gb_per_min(self) -> float:
        """Downlink speed in GB/min."""
        # 50 Mbps = 50/8 MB/s = 6.25 MB/s = 0.375 GB/min
        return (self.downlink_speed_mbps / 8.0) * 60.0 / 1000.0
    
    @property
    def data_per_downlink_gb(self) -> float:
        """Maximum data that can be downlinked per pass."""
        # 50 Mbps for 8 min = 3 GB
        return self.downlink_speed_gb_per_min * self.downlink_duration_min
    
    # Imaging windows (orbit angle ranges where imaging is allowed)
    imaging_windows_theta: List[Tuple[float, float]] = field(
        default_factory=lambda: [[20.0, 40.0]]  # Single 10-min window in sunlight
    )
    shutter_speed_ms: float = 20.0
    
    # Ground station pass window (orbit angle range for downlink)
    # Positioned so ~50% is in sunlight, ~50% in eclipse
    ground_pass_window_theta: Tuple[float, float] = field(
        default_factory=lambda: (95.0, 125.0)  # Spans sun/eclipse boundary
    )
    
    # ADCS momentum dump window (in sunlight)
    adcs_dump_window_theta: Tuple[float, float] = field(
        default_factory=lambda: (50.0, 70.0)  # ~5 min window in sunlight
    )
    
    # Simulation parameters
    timestep_min: float = 1.0  # Default timestep in minutes
    
    # Safety margins for 20% SoC compliance
    soc_safety_margin_percent: float = 5.0  # Start shedding loads at 25%
    
    def to_dict(self) -> dict:
        """Convert config to dictionary."""
        d = asdict(self)
        # Add computed properties
        d['data_generation_rate_gb_per_min'] = self.data_generation_rate_gb_per_min
        d['downlink_speed_gb_per_min'] = self.downlink_speed_gb_per_min
        d['data_per_downlink_gb'] = self.data_per_downlink_gb
        return d
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SatelliteConfig':
        """Create config from dictionary."""
        # Remove computed properties if present
        data = {k: v for k, v in data.items() 
                if k not in ['data_generation_rate_gb_per_min', 
                            'downlink_speed_gb_per_min',
                            'data_per_downlink_gb']}
        return cls(**data)


@dataclass
class SatelliteState:
    """
    Complete state of the satellite at a given timestep.
    All mutable variables that change during simulation.
    
    Battery SoC constraint: Shall never drop below 20% during nominal operations.
    """
    
    # Time tracking
    simulation_time_s: float = 0.0  # Total simulation time in seconds
    orbit_number: int = 0  # Current orbit number
    orbit_angle_deg: float = 0.0  # Position in orbit (0-360, 0 = ascending node)
    orbit_phase_min: float = 0.0  # Time within current orbit (0 to orbit_period)
    
    # EPS state
    battery_level_percent: float = 80.0  # Current state of charge (%)
    battery_voltage_v: float = 12.5  # Current battery voltage
    battery_energy_wh: float = 80.0  # Current energy stored (Wh)
    solar_generation_w: float = 0.0  # Current solar power generation
    in_sunlight: bool = True  # Whether satellite is in sunlight
    net_power_w: float = 0.0  # Net power (generation - load)
    
    # Load state (per loads.md)
    total_load_w: float = 15.0  # Total current power consumption
    base_load_w: float = 15.0  # Platform base load (always on)
    payload_load_w: float = 0.0  # Imaging payload power (+40W when active)
    comms_load_w: float = 0.0  # Downlink power (+30W when active)
    adcs_dump_load_w: float = 0.0  # ADCS momentum dump (+10W when active)
    heater_load_w: float = 0.0  # Thermal (not in loads.md, kept for compatibility)
    
    # Operational mode flags
    is_imaging: bool = False  # Currently imaging (+40W, sunlight only)
    is_downlinking: bool = False  # Currently in ground pass (+30W)
    is_adcs_dumping: bool = False  # ADCS momentum dump active (+10W, sunlight only)
    
    # Data system state (per loads.md: 2 Gbit/orbit, 50 Mbps downlink)
    onboard_data_volume_gb: float = 0.0  # Current stored data
    data_generated_gb: float = 0.0  # Total data generated this session
    data_downlinked_gb: float = 0.0  # Total data downlinked this session
    data_generated_this_orbit_gb: float = 0.0  # Data generated in current orbit
    
    # Window tracking
    in_imaging_window: bool = False
    in_ground_pass_window: bool = False
    in_adcs_dump_window: bool = False
    
    # Timing within orbit
    imaging_time_this_orbit_min: float = 0.0  # Imaging time used this orbit
    downlink_time_this_orbit_min: float = 0.0  # Downlink time used this orbit
    adcs_dump_time_this_orbit_min: float = 0.0  # ADCS dump time used this orbit
    
    # Environmental state
    temperature_c: float = 287.0  # Component temperature
    pressure_pa: float = 0.001  # Ambient pressure (near vacuum)
    
    # Health/degradation
    battery_health_percent: float = 97.0  # Battery health (degradation)
    battery_cycles: int = 0  # Number of charge/discharge cycles
    
    # Warning and compliance flags
    low_battery_warning: bool = False  # Near 20% limit
    high_battery_warning: bool = False  # Near full charge
    data_storage_full: bool = False  # Storage nearly full
    soc_violation: bool = False  # TRUE if SoC dropped below 20% (compliance failure)
    load_shed_active: bool = False  # Load shedding to protect battery
    
    def copy(self) -> 'SatelliteState':
        """Create a deep copy of the state."""
        return copy.deepcopy(self)
    
    def to_dict(self) -> dict:
        """Convert state to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SatelliteState':
        """Create state from dictionary."""
        return cls(**data)
    
    def update_warnings(self, config: SatelliteConfig) -> None:
        """Update warning flags based on current state."""
        # Low battery warning at safety margin above minimum
        warning_threshold = config.min_soc_percent + config.soc_safety_margin_percent
        self.low_battery_warning = self.battery_level_percent <= warning_threshold
        
        # High battery warning near full
        self.high_battery_warning = self.battery_level_percent >= 95.0
        
        # Storage warning at 95% full
        self.data_storage_full = self.onboard_data_volume_gb >= config.max_data_storage_gb * 0.95
        
        # CRITICAL: Check for 20% SoC violation
        if self.battery_level_percent < config.min_soc_percent:
            self.soc_violation = True
    
    def get_summary(self) -> str:
        """Get a human-readable summary of the current state."""
        mode = []
        if self.is_imaging:
            mode.append("IMG")
        if self.is_downlinking:
            mode.append("DL")
        if self.is_adcs_dumping:
            mode.append("ADCS")
        mode_str = "+".join(mode) if mode else "IDLE"
        
        sun_str = '☀️' if self.in_sunlight else '🌑'
        violation = " ⚠️SOC<20%!" if self.soc_violation else ""
        
        return (
            f"T:{self.simulation_time_s/60:.0f}m | "
            f"Orb:{self.orbit_number}@{self.orbit_angle_deg:.0f}° | "
            f"Bat:{self.battery_level_percent:.1f}% | "
            f"P:{self.solar_generation_w:.0f}-{self.total_load_w:.0f}={self.net_power_w:.0f}W | "
            f"Data:{self.onboard_data_volume_gb:.3f}GB | "
            f"{sun_str} {mode_str}{violation}"
        )
    
    def get_load_breakdown(self) -> dict:
        """Get detailed load breakdown per loads.md categories."""
        return {
            'base_load_w': self.base_load_w,
            'imaging_load_w': self.payload_load_w,
            'downlink_load_w': self.comms_load_w,
            'adcs_dump_load_w': self.adcs_dump_load_w,
            'total_load_w': self.total_load_w
        }
