# Satellite Digital Twin

A high-fidelity simulation framework for spacecraft power and data management in low Earth orbit. Designed for mission planning, power budget analysis, and operational constraint verification.

## Mission Profile

- **Orbit**: 500 km Sun-Synchronous Orbit (SSO)
- **Period**: 95 minutes
- **Sunlight**: 60 minutes per orbit
- **Eclipse**: 35 minutes per orbit

## Reference Specification

This implementation adheres to the `loads.md` specification:

### Power Budget

| Mode | Power | Duration | Constraint |
|------|-------|----------|------------|
| Platform Base | 15 W | Continuous | Always on |
| Payload Imaging | +40 W | 10 min/orbit | Sunlight only |
| Downlink | +30 W | 8 min/orbit | 50% sun/50% eclipse |
| ADCS Momentum Dump | +10 W | 5 min/orbit | Sunlight only |

### Operational Power Modes

| Mode | Total Power |
|------|-------------|
| Base Only | 15 W |
| Base + Imaging | 55 W |
| Base + Downlink | 45 W |
| Base + ADCS Dump | 25 W |
| Peak (Imaging + ADCS) | 65 W |

### Data Budget

| Parameter | Value |
|-----------|-------|
| Data Generation | 2 Gbit per orbit |
| Imaging Duration | 10 minutes per orbit |
| Generation Rate | 0.025 GB/min |
| Downlink Rate | 50 Mbps |
| Downlink Duration | 8 minutes per orbit |
| Downlink Capacity | 3 GB per pass |

### Critical Constraint

**Battery State of Charge shall NEVER drop below 20% during nominal operations.**

## Installation

```bash
cd galaxeye2
pip install -e .
```

Or install dependencies directly:

```bash
pip install numpy pandas matplotlib plotly streamlit
```

## Usage

### Command Line Interface

```bash
# Run simulation (default: 5 orbits)
python main.py

# Run for specific duration
python main.py --orbits 10

# Use specific operations policy
python main.py --policy power_save

# Export telemetry data
python main.py --export ./output

# Display specification
python main.py --compliance

# Launch web interface
python main.py --dashboard
```

### Python API

```python
from satellite.state import SatelliteState, SatelliteConfig
from simulation.engine import Simulation
from simulation.policy import LoadsMDCompliantPolicy

# Configure spacecraft
config = SatelliteConfig(
    orbit_period_min=95.0,
    sunlight_duration_min=60.0,
    solar_panel_power_w=60.0,
    battery_capacity_wh=100.0,
    base_load_w=15.0,
    imaging_load_w=40.0,
    downlink_load_w=30.0,
    imaging_duration_min=10.0,
    downlink_duration_min=8.0,
    data_per_orbit_gbit=2.0,
    downlink_speed_mbps=50.0,
    timestep_min=1.0
)

# Initial state
initial_state = SatelliteState(
    battery_level_percent=80.0,
    battery_energy_wh=80.0
)

# Execute simulation
sim = Simulation(config, initial_state, LoadsMDCompliantPolicy())
history = sim.run(duration_orbits=10)

# Verify compliance
summary = sim.get_summary()
print(f"Min SoC: {summary['compliance']['min_soc_reached']:.1f}%")
print(f"Compliant: {summary['compliance']['compliant']}")
```

## Configuration Parameters

### Orbit Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `orbit_period_min` | 95.0 | Orbital period [minutes] |
| `sunlight_duration_min` | 60.0 | Sunlight duration per orbit [minutes] |
| `eclipse_duration_min` | 35.0 | Eclipse duration per orbit [minutes] |
| `orbit_altitude_km` | 500.0 | Orbit altitude [km] |

### Electrical Power System

| Parameter | Default | Description |
|-----------|---------|-------------|
| `solar_panel_power_w` | 60.0 | Solar array output [W] |
| `battery_capacity_wh` | 100.0 | Battery capacity [Wh] |
| `min_soc_percent` | 20.0 | Minimum SoC [%] (CONSTRAINT) |
| `charge_efficiency` | 0.95 | Battery charge efficiency |
| `discharge_efficiency` | 0.95 | Battery discharge efficiency |

### Power Budget (loads.md)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `base_load_w` | 15.0 | Platform base load [W] |
| `imaging_load_w` | 40.0 | Imaging payload load [W] |
| `downlink_load_w` | 30.0 | Downlink load [W] |
| `adcs_dump_load_w` | 10.0 | ADCS dump load [W] |

### Operations Timing (loads.md)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `imaging_duration_min` | 10.0 | Imaging time per orbit [min] |
| `downlink_duration_min` | 8.0 | Downlink time per orbit [min] |
| `adcs_dump_duration_min` | 5.0 | ADCS dump time per orbit [min] |

### Data Budget (loads.md)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `data_per_orbit_gbit` | 2.0 | Data generation [Gbit/orbit] |
| `downlink_speed_mbps` | 50.0 | Downlink rate [Mbps] |
| `max_data_storage_gb` | 100.0 | Onboard storage capacity [GB] |

## State Variables

### Electrical Power System

- `battery_level_percent` - Battery state of charge [%]
- `battery_voltage_v` - Bus voltage [V]
- `solar_generation_w` - Solar array output [W]
- `net_power_w` - Net power (generation - load) [W]
- `in_sunlight` - Illumination status

### Load State

- `total_load_w` - Total power consumption [W]
- `base_load_w` - Platform base load [W]
- `payload_load_w` - Imaging payload load [W]
- `comms_load_w` - Communication load [W]
- `adcs_dump_load_w` - ADCS dump load [W]

### Operations Mode

- `is_imaging` - Payload imaging active
- `is_downlinking` - Downlink active
- `is_adcs_dumping` - ADCS dump active

### Data System

- `onboard_data_volume_gb` - Stored data [GB]
- `data_generated_gb` - Total generated [GB]
- `data_downlinked_gb` - Total downlinked [GB]

## Operations Policies

### LoadsMDCompliantPolicy

Strict adherence to loads.md specification with automatic load shedding to maintain 20% SoC constraint.

### BasicPolicy

Threshold-based operations with configurable battery limits.

### PowerSavePolicy

Conservative power management prioritizing battery conservation.

### HighPerformancePolicy

Aggressive operations maximizing data collection while respecting constraints.

### CustomizablePolicy

User-configurable thresholds for all operational parameters.

## Project Structure

```
galaxeye2/
├── satellite/              # Spacecraft subsystem models
│   ├── state.py            # State and configuration
│   ├── eps.py              # Electrical Power System
│   ├── orbit.py            # Orbital mechanics
│   ├── data_system.py      # Data management
│   └── loads.py            # Load management
├── simulation/             # Simulation framework
│   ├── engine.py           # Simulation engine
│   └── policy.py           # Operations policies
├── output/                 # Output and visualization
│   ├── timeseries.py       # Data export
│   ├── visualization.py    # Plotting
│   └── dashboard.py        # Web interface
├── main.py                 # CLI entry point
├── test_compliance.py      # Compliance verification
├── loads.md                # Reference specification
└── pyproject.toml          # Dependencies
```

## Compliance Verification

```bash
python test_compliance.py
```

Verifies:
- Power budget adherence
- Data budget adherence
- 20% SoC constraint maintenance
- Eclipse survival capability

## Output Formats

### CSV Export

```python
from output.timeseries import TimeSeriesExporter

exporter = TimeSeriesExporter(history)
exporter.to_csv("telemetry.csv")
```

### JSON Export

```python
exporter.to_json("telemetry.json")
```

### Visualization

```python
from output.visualization import Visualizer

viz = Visualizer(history)
viz.plot_overview()
viz.plot_battery_detail()
viz.plot_power_breakdown()
```

## Requirements

- Python 3.12+
- numpy >= 1.26
- pandas >= 2.1
- matplotlib >= 3.8
- plotly >= 5.18
- streamlit >= 1.29

## License

MIT License
