# Satellite Digital Twin

A stateful digital twin simulation of a satellite in a 500km Sun-Synchronous Orbit (SSO).

## Features

- **Electrical Power System (EPS)**: 60W solar panels, 100Wh battery with charge/discharge management
- **Orbital Mechanics**: Accurate sun/eclipse cycle modeling for SSO
- **Data System**: Data generation, onboard storage, and manual downlink control
- **Policy Engine**: Customizable operation policies (basic, power-save, high-performance)
- **Visualization**: Static (matplotlib) and interactive (plotly) plots
- **Web Dashboard**: Streamlit-based interactive dashboard

## Quick Start

### Installation

```bash
# Clone the repository
cd galaxeye2

# Install dependencies
pip install -e .

# Or install dependencies directly
pip install numpy pandas matplotlib plotly streamlit
```

### Run Example Simulation

```bash
# Run with default parameters (5 orbits, basic policy)
python main.py

# Run for 10 orbits
python main.py --orbits 10

# Use power-save policy
python main.py --policy power_save

# Export results
python main.py --export ./results

# Launch web dashboard
python main.py --dashboard
```

### Python API

```python
from satellite.state import SatelliteState, SatelliteConfig
from simulation.engine import Simulation
from simulation.policy import BasicPolicy

# Create configuration
config = SatelliteConfig(
    orbit_period_min=95.0,
    sunlight_duration_min=60.0,
    solar_panel_power_w=60.0,
    battery_capacity_wh=100.0,
    min_soc_percent=20.0,
    max_soc_percent=80.0,
    imaging_windows_theta=[[23, 28], [45, 50]],
    timestep_min=1.0
)

# Initial state
initial_state = SatelliteState(
    battery_level_percent=82.0,
    battery_voltage_v=12.5,
    total_load_w=23.0
)

# Run simulation
sim = Simulation(config, initial_state, BasicPolicy())
history = sim.run(duration_orbits=5)

# Get results
summary = sim.get_summary()
print(f"Battery: {summary['battery']['min']:.1f}% - {summary['battery']['max']:.1f}%")
```

## Configuration Parameters

### Orbit Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `orbit_period_min` | 95.0 | Orbital period in minutes |
| `sunlight_duration_min` | 60.0 | Time in sunlight per orbit |
| `eclipse_duration_min` | 35.0 | Time in eclipse per orbit |
| `orbit_altitude_km` | 500.0 | Orbit altitude |

### EPS Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `solar_panel_power_w` | 60.0 | Solar panel output power |
| `battery_capacity_wh` | 100.0 | Battery capacity |
| `min_soc_percent` | 20.0 | Minimum state of charge |
| `max_soc_percent` | 80.0 | Maximum state of charge |
| `charge_efficiency` | 0.95 | Battery charge efficiency |
| `discharge_efficiency` | 0.95 | Battery discharge efficiency |

### Data System Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_data_storage_gb` | 100.0 | Maximum onboard storage |
| `downlink_speed_gbps` | 1.0 | Downlink data rate |
| `uplink_speed_gbps` | 0.1 | Uplink data rate |
| `imaging_windows_theta` | [[23,28],[45,50]] | Imaging window angles |

## State Variables

### Core State
- `simulation_time_s` - Total simulation time
- `orbit_number` - Current orbit count
- `orbit_angle_deg` - Position in orbit (0-360°)

### EPS State
- `battery_level_percent` - Battery state of charge (%)
- `battery_voltage_v` - Battery voltage
- `solar_generation_w` - Current solar power
- `net_power_w` - Net power (generation - load)
- `in_sunlight` - Sunlight/eclipse status

### Load State
- `total_load_w` - Total power consumption
- `base_load_w` - Essential system load
- `payload_load_w` - Payload power consumption
- `heater_load_w` - Thermal management load
- `comms_load_w` - Communication load

### Data State
- `onboard_data_volume_gb` - Stored data volume
- `is_imaging` - Imaging active status
- `is_downlinking` - Downlink active status

## Policies

### BasicPolicy
Simple threshold-based rules:
- Reduces load when battery below 30%
- Enables imaging in designated windows
- Triggers downlink when storage > 70%

### PowerSavePolicy
Conservative power management:
- Minimal operations during eclipse
- Prioritizes battery charging
- Higher battery thresholds for operations

### HighPerformancePolicy
Maximizes data collection:
- Aggressive imaging schedule
- Lower battery margins
- Continuous downlink when possible

### CustomizablePolicy
User-configurable thresholds:
```python
policy = CustomizablePolicy(
    min_battery_imaging=40.0,
    min_battery_downlink=30.0,
    storage_downlink_trigger=60.0,
    eclipse_load_reduction=0.5,
    safe_mode_threshold=25.0
)
```

## Output Formats

### CSV Export
```python
from output.timeseries import TimeSeriesExporter

exporter = TimeSeriesExporter(history)
exporter.to_csv("results.csv")
```

### JSON Export
```python
exporter.to_json("results.json", include_metadata=True)
```

### Plots
```python
from output.visualization import Visualizer

viz = Visualizer(history)
viz.plot_overview()
viz.plot_battery_detail()
viz.plot_power_breakdown()
```

### Interactive Dashboard
```bash
python main.py --dashboard
# Or directly:
streamlit run output/dashboard.py
```

## Project Structure

```
galaxeye2/
├── satellite/           # Satellite subsystem models
│   ├── state.py         # State and config dataclasses
│   ├── eps.py           # Electrical Power System
│   ├── orbit.py         # Orbital mechanics
│   ├── data_system.py   # Data management
│   └── loads.py         # Load definitions
├── simulation/          # Simulation engine
│   ├── engine.py        # Main simulation loop
│   └── policy.py        # Policy definitions
├── output/              # Output and visualization
│   ├── timeseries.py    # CSV/JSON export
│   ├── visualization.py # Matplotlib/Plotly plots
│   └── dashboard.py     # Streamlit dashboard
├── examples/            # Example scripts
│   └── basic_simulation.py
├── main.py              # CLI entry point
└── pyproject.toml       # Dependencies
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





